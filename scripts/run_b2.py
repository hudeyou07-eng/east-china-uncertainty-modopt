"""B2 主决策可靠性实验驱动（R200–R203）。

跑四个系统 × 省份 × 协议单元，在真值上评估：

======  ==========================================================
D0      均值填充确定性 MODOpt：价格用**跨省合并均值**（模拟遮蔽后
        缺失格被总体均值替换），单场景，硬营养约束
D1      后验均值确定性 MODOpt：价格用**该协议单元的插补价格**，单场景，硬营养约束
D2      场景期望 MODOpt：多场景期望目标，**无**营养机会约束
D3      场景 MODOpt + 联合营养机会约束（主方法）
======  ==========================================================

## 三处占位的状态（2026-10-27 第九轮后）

| # | 占位 | 状态 |
|---|---|---|
| 1 | 真值 = 冻结合同点估计，非遮蔽前伪完整面板 | **仍是占位** |
| 2 | 场景 = 点估计上的对数正态扰动，非 B1 后验 | **已替换**（`--scenario-source posterior`） |
| 3 | 重复 = 换种子重抽，非 5×20 遮蔽协议 | **已替换**（`--protocol masking`） |

第 2、3 项现在走 B1 正式批次（`B1_formal_withmice_20261023_124906`）：

* 场景 = 从 `cell_predictions.csv` 抽**中心化经验残差**（`src/b2_scenarios.py`）；
* 重复 = 5 折 × 20 重复 × 3 遮蔽几何的**协议单元**（`src/b2_protocol.py`），
  每个单元给出「若这次遮蔽后插补，价格会是多少」，D1 就在那个价格上决策。

因为第 1 项仍未解决，`evidence_status` 保持 `plumbing_only`，
但 `resolved_components` 会列出已替换的两项，`placeholder_components` 只剩一项。

## 实验设计的一个关键选择

遮蔽协议下**场景种子固定**（不随协议单元变化）。这样单元之间唯一的差别是
「插补后的价格」，而不是「噪声实现」。若种子也变，就无法区分
「决策因价格变化而变」与「决策因抽样波动而变」。

旧的 `--protocol reseed` 保留作对照：它正是「只变噪声、不变数据」，
用于说明「换种子重抽不构成统计重复」。

用法：
    python scripts/run_b2.py --profile smoke
    python scripts/run_b2.py --profile formal --scenario CDG
    python scripts/run_b2.py --profile smoke --protocol reseed --scenario-source placeholder
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.b2_evaluate import (  # noqa: E402
    flip_flags,
    joint_feasible,
    objective_totals,
    objective_gap,
    summarize,
)
from src.b2_problem import SCOPE_AUDITS, Contract, Instance, OBJECTIVES  # noqa: E402
from src.b2_protocol import (  # noqa: E402
    MASK_TYPES,
    apply_shift,
    protocol_cells,
    protocol_shift_summary,
)
from src.b2_scenarios import (  # noqa: E402
    B1_METHOD_DEFAULT,
    B1_RUN_DEFAULT,
    deterministic,
    load_residual_pool,
    placeholder_scenarios,
    posterior_scenarios,
)
from src.io_utils import create_run_dir, fail_run, finalize_run, sha256_file, write_json  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402

OUTPUT_ROOT = ROOT / "outputs"
PROCESSED = ROOT / "data" / "processed"

METHODS = ("D0", "D1", "D2", "D3")
PROFILES = {
    "smoke": {"repeats": 2, "scenarios": 20},
    "formal": {"repeats": 20, "scenarios": 200},
}


def _solve(
    inst: Instance,
    objective_coeff: np.ndarray,
    nutrient_coeff: np.ndarray,
    use_chance: bool,
    epsilon: float,
    time_limit: float,
    gap: float,
):
    mask = inst.active_mask
    if mask is None:
        mask = np.ones(len(inst.nutrients), dtype=bool)
    return solve_chance_modopt(
        objective_coeff=objective_coeff,
        nutrient_coeff=nutrient_coeff[:, mask, :],
        nutrient_lower=inst.nutrient_lower[mask],
        nutrient_upper=inst.nutrient_upper[mask],
        q_lower=inst.q_lower,
        q_upper=inst.q_upper,
        objective_weights=inst.objective_weights,
        epsilon=epsilon,
        time_limit=time_limit,
        mip_rel_gap=gap,
        extra_constraints=inst.extra_constraints,
        use_chance_constraint=use_chance,
    )


def _clean(obj):
    """把 NaN / inf 转成 None，保证 metrics.json 可序列化。"""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return [_clean(v) for v in obj.tolist()]
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description="B2 决策可靠性实验")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="smoke")
    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "输出目录前缀（默认 R200_203_b2_<profile>）。用于附录/单点等非正式批次，"
            "避免生成会被误当成正式批次的目录名。见 AUDIT P2-4"
        ),
    )
    parser.add_argument("--scenario", default="CDG", help="决策情景：CDG / EAT / HEAL_base")
    parser.add_argument("--repeats", type=int, default=None, help="每折的重复数")
    parser.add_argument("--folds", type=int, default=None, help="用前几折（默认全部 5 折）")
    parser.add_argument("--scenarios", type=int, default=None, help="训练场景数")
    parser.add_argument("--epsilon", type=float, default=0.05)
    parser.add_argument(
        "--scenario-source",
        choices=("posterior", "placeholder"),
        default="posterior",
        help=(
            "posterior=B1 经验残差（正式）；placeholder=对数正态占位噪声（仅对照）。"
            "占位噪声逐组独立，会把 CVaR 的旋转角压到 1° 量级，见 CHANGELOG §24.3"
        ),
    )
    parser.add_argument(
        "--protocol",
        choices=("masking", "reseed"),
        default="masking",
        help=(
            "masking=B1 的 5×20×3 遮蔽协议（正式，每个单元换一次插补结果）；"
            "reseed=换随机种子重抽场景（旧行为，不构成统计重复，仅作对照）"
        ),
    )
    parser.add_argument("--mask-type", choices=MASK_TYPES, default="single_cell")
    parser.add_argument("--b1-run", default=B1_RUN_DEFAULT)
    parser.add_argument("--b1-method", default=B1_METHOD_DEFAULT)
    parser.add_argument("--cv-price", type=float, default=0.05, help="仅 placeholder 源使用")
    parser.add_argument(
        "--cv-nutrient", type=float, default=0.0,
        help=(
            "营养系数的场景扰动幅度。默认 0（不扰动）：食物成分表是固定物理常数，"
            "扰动它会掩盖真正的价格不确定性，见 CHANGELOG §21.6。"
        ),
    )
    parser.add_argument("--time-limit", type=float, default=120.0)
    parser.add_argument("--gap", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=20261026)
    parser.add_argument("--provinces", nargs="*", default=None)
    parser.add_argument(
        "--scope",
        default="k6_price",
        choices=["k4_official", "k6_price", "k3_prereg", "k5_notrace"],
        help="决策口径（边界门）。默认 k6_price = 2026-10-27 修订后的主口径",
    )
    parser.add_argument("--dry-run", action="store_true", help="只做装配与诊断，不求解")
    parser.add_argument(
        "--bounds-basis",
        choices=("rni", "ear"),
        default="ear",
        help=(
            "营养下界口径：ear=2026-10-27 作者裁定的主口径；rni=预注册原口径（对照）"
        ),
    )
    args = parser.parse_args()

    profile = PROFILES[args.profile]
    repeats = args.repeats or profile["repeats"]
    n_scen = args.scenarios or profile["scenarios"]

    contract = Contract.load_scope(args.scope)
    ok_prov, excluded = contract.complete_provinces()
    provinces = args.provinces or ok_prov
    missing = [p for p in provinces if p not in ok_prov]
    if missing:
        raise SystemExit(f"以下省份价格不完整，无法装配：{ {p: excluded[p] for p in missing} }")

    run_dir = create_run_dir(OUTPUT_ROOT, args.run_id or f"R200_203_b2_{args.profile}")
    # 审计表随口径变化，必须记录**实际使用的**那一张。
    audit_file = SCOPE_AUDITS[args.scope]

    b1_dir = OUTPUT_ROOT / args.b1_run
    base_panel = contract.price_panel().reindex(provinces)

    # ---- 场景源：残差池（一次加载，循环内复用） ----
    pool = None
    if args.scenario_source == "posterior":
        pool = load_residual_pool(
            b1_dir, method=args.b1_method, mask_type=args.mask_type, groups=contract.groups
        )

    # ---- 重复结构：协议单元 ----
    if args.protocol == "masking":
        cells = protocol_cells(
            b1_dir,
            method=args.b1_method,
            mask_type=args.mask_type,
            folds=args.folds,
            repeats=repeats,
            provinces=provinces,
            groups=list(contract.groups),
        )
    else:
        cells = [None] * repeats  # 旧行为：每重复换种子，数据不变

    config = {
        "command": " ".join(sys.argv),
        "scope": args.scope,
        "audit_file": audit_file,
        "profile": args.profile,
        "scenario": args.scenario,
        "scenario_source": args.scenario_source,
        "protocol": args.protocol,
        "mask_type": args.mask_type if args.protocol == "masking" else None,
        "b1_run": args.b1_run if args.scenario_source == "posterior" or args.protocol == "masking" else None,
        "b1_method": args.b1_method,
        "repeats": repeats,
        "folds": args.folds,
        "n_cells": len(cells),
        "train_scenarios": n_scen,
        "epsilon": args.epsilon,
        "cv_price": args.cv_price if args.scenario_source == "placeholder" else None,
        "cv_nutrient": args.cv_nutrient,
        "bounds_basis": args.bounds_basis,
        "objective_weights": dict(zip(OBJECTIVES, [0.5, 0.25, 0.25])),
        "groups": list(contract.groups),
        "nutrients": list(contract.nutrients),
        "provinces": provinces,
        "provinces_excluded": excluded,
        "contract_hashes": {
            name: sha256_file(PROCESSED / name)
            for name in (
                audit_file,
                "group_prices.csv",
                "nutrients.csv",
                "environment.csv",
                "baseline_consumption.csv",
                "decision_bounds.csv",
            )
        },
        "nutrient_bounds_sha256": sha256_file(
            ROOT / "data" / "input" / "external" / "nutrient_bounds.csv"
        ),
        "b1_prediction_sha256": (
            sha256_file(b1_dir / "cell_predictions.csv")
            if (b1_dir / "cell_predictions.csv").exists()
            else None
        ),
    }

    try:
        rows: list[dict] = []
        diag: dict[str, dict] = {}

        for province in provinces:
            # 真值实例：观测面板。所有评估都对着它，与协议单元无关。
            inst_true = contract.instance(
                province, args.scenario, epsilon=args.epsilon, bounds_basis=args.bounds_basis
            )
            truth_obj, truth_nut = deterministic(inst_true)
            diag[province] = {
                "active_nutrients": [
                    n for n, m in zip(inst_true.nutrients, inst_true.active_mask) if m
                ],
                "non_actionable": dict(inst_true.non_actionable),
                "offset_missing_pairs": len(inst_true.offset_missing),
                "joint_constraints": len(inst_true.extra_constraints),
                "skipped_joint": contract.skipped_joint(province, args.scenario),
                "baseline": dict(zip(inst_true.groups, inst_true.baseline.round(3).tolist())),
                "baseline_adequacy": contract.baseline_adequacy(province),
                "hard_feasible": bool(inst_true.hard_feasible),
                "conflict_set": list(inst_true.conflict_set),
                "observed_prices": dict(
                    zip(inst_true.groups, base_panel.loc[province].round(2).tolist())
                ),
            }
            if args.dry_run:
                continue

            # 真值参考解 q*：单场景、硬营养约束、观测价格
            ref = _solve(inst_true, truth_obj, truth_nut, True, 0.0, args.time_limit, args.gap)
            ref_ok = bool(ref.success) and np.isfinite(ref.q).all()
            if not ref_ok:
                ref = _solve(inst_true, truth_obj, truth_nut, False, 0.0, args.time_limit, args.gap)
            q_ref = ref.q if np.isfinite(ref.q).all() else inst_true.baseline

            inst_status = "ok" if inst_true.hard_feasible else "hard_infeasible"

            for cell_idx, cell in enumerate(cells):
                # ---- 决策实例：价格来自该协议单元 ----
                if cell is None:
                    fold, rep = -1, cell_idx
                    inst_dec = inst_true
                    inst_pool = contract.instance(
                        province, args.scenario, epsilon=args.epsilon,
                        price_mode="pooled", bounds_basis=args.bounds_basis,
                    )
                else:
                    fold, rep = cell.fold, cell.repeat
                    imputed_panel = base_panel * (1.0 + cell.shift.reindex(index=provinces))
                    pv = imputed_panel.loc[province].to_numpy(dtype=float)
                    inst_dec = contract.instance(
                        province, args.scenario, epsilon=args.epsilon,
                        bounds_basis=args.bounds_basis, price_override=pv,
                    )
                    pooled = imputed_panel.mean(axis=0, skipna=True).to_numpy(dtype=float)
                    inst_pool = contract.instance(
                        province, args.scenario, epsilon=args.epsilon,
                        bounds_basis=args.bounds_basis, price_override=pooled,
                    )

                # ---- 场景：种子固定，保证单元间只差价格、不差噪声 ----
                if args.scenario_source == "posterior":
                    obj_s, nut_s = posterior_scenarios(
                        inst_dec, n_scen, args.seed, pool=pool
                    )
                else:
                    obj_s, nut_s = placeholder_scenarios(
                        inst_dec, n_scen, args.seed + rep, args.cv_price, args.cv_nutrient
                    )

                if not inst_true.hard_feasible:
                    for method in METHODS:
                        rows.append(
                            {
                                "province": province,
                                "scenario": args.scenario,
                                "fold": fold,
                                "repeat": rep,
                                "cell": cell_idx,
                                "method": method,
                                "instance_status": inst_status,
                                "solver_success": False,
                                "solver_message": "hard_infeasible: "
                                + "+".join(inst_true.conflict_set),
                                "mip_gap": float("nan"),
                                "feasible_all": False,
                                "feasible_active": False,
                                "flips": len(inst_true.groups),
                                "n_groups": len(inst_true.groups),
                                "objective_gap": float("nan"),
                                "max_abs_dq_ref": float("nan"),
                                "reference_feasible": False,
                                **{f"total_{k}": float("nan") for k in OBJECTIVES},
                                **{f"q_{g}": float("nan") for g in inst_true.groups},
                            }
                        )
                    continue

                dec_obj, dec_nut = deterministic(inst_dec)
                pool_obj, pool_nut = deterministic(inst_pool)

                solutions = {
                    "D0": _solve(inst_pool, pool_obj, pool_nut, True, 0.0, args.time_limit, args.gap),
                    "D1": _solve(inst_dec, dec_obj, dec_nut, True, 0.0, args.time_limit, args.gap),
                    "D2": _solve(inst_dec, obj_s, nut_s, False, 0.0, args.time_limit, args.gap),
                    "D3": _solve(inst_dec, obj_s, nut_s, True, args.epsilon, args.time_limit, args.gap),
                }

                for method in METHODS:
                    res = solutions[method]
                    q = res.q
                    ok_q = bool(res.success) and np.isfinite(q).all()
                    if ok_q:
                        feas_all = joint_feasible(
                            q, truth_nut[0], inst_true.nutrient_offset,
                            inst_true.nutrient_lower_raw, inst_true.nutrient_upper_raw,
                        )
                        feas_act = joint_feasible(
                            q, truth_nut[0], inst_true.nutrient_offset,
                            inst_true.nutrient_lower_raw, inst_true.nutrient_upper_raw,
                            active_mask=inst_true.active_mask,
                        )
                        flips = int(flip_flags(q, q_ref, inst_true.baseline).sum())
                        reg = objective_gap(
                            q, q_ref, truth_obj[0], inst_true.objective_weights,
                            inst_true.q_lower, inst_true.q_upper,
                        )
                        totals = objective_totals(q, inst_true)
                        dq_ref = float(np.abs(q - q_ref).max())
                    else:
                        feas_all = feas_act = False
                        flips = len(inst_true.groups)
                        reg = float("nan")
                        totals = {k: float("nan") for k in OBJECTIVES}
                        dq_ref = float("nan")

                    rows.append(
                        {
                            "province": province,
                            "scenario": args.scenario,
                            "fold": fold,
                            "repeat": rep,
                            "cell": cell_idx,
                            "method": method,
                            "instance_status": inst_status,
                            "solver_success": bool(res.success),
                            "solver_message": str(res.message)[:120],
                            "mip_gap": res.mip_gap,
                            "feasible_all": bool(feas_all),
                            "feasible_active": bool(feas_act),
                            "flips": flips,
                            "n_groups": len(inst_true.groups),
                            "objective_gap": reg,
                            "max_abs_dq_ref": dq_ref,
                            "reference_feasible": ref_ok,
                            **{f"total_{k}": v for k, v in totals.items()},
                            **{f"q_{g}": float(q[i]) if ok_q else float("nan") for i, g in enumerate(inst_true.groups)},
                        }
                    )

        if args.dry_run:
            payload = _clean({"provinces": diag, "excluded": excluded})
            write_json(run_dir / "diagnostics.json", payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            (run_dir / "DRY_RUN").write_text("diagnostics only\n", encoding="utf-8")
            write_json(run_dir / "config.json", config)
            print(f"[dry-run] {run_dir}")
            return

        results = pd.DataFrame(rows)
        results.to_csv(run_dir / "b2_results.csv", index=False, encoding="utf-8-sig")

        per_method = {}
        for method in METHODS:
            sub = results[results["method"].eq(method)]
            per_method[method] = summarize(
                sub["feasible_all"].tolist(),
                sub["feasible_active"].tolist(),
                sub["flips"].tolist(),
                sub["n_groups"].tolist(),
                sub["objective_gap"].tolist(),
                sub["max_abs_dq_ref"].tolist(),
            )
            per_method[method]["solver_failures"] = int((~sub["solver_success"]).sum())

        resolved = []
        if args.scenario_source == "posterior":
            resolved.append("scenarios = B1 经验残差后验（已替换占位对数正态）")
        if args.protocol == "masking":
            resolved.append("repeats = B1 5×20×3 遮蔽协议单元（已替换换种子重抽）")
        remaining = ["truth = 冻结合同点估计，非遮蔽前伪完整面板"]
        if args.scenario_source != "posterior":
            remaining.append("scenarios = 对数正态占位噪声")
        if args.protocol != "masking":
            remaining.append("repeats = 换种子重抽，非遮蔽协议")

        metrics = {
            "command": "b2-main",
            "evidence_status": "plumbing_only",
            "resolved_components": resolved,
            "placeholder_components": remaining,
            "scenario": args.scenario,
            "decision_scope": args.scope,
            "audit_file": audit_file,
            "bounds_basis": args.bounds_basis,
            "k_count": len(contract.groups),
            "scenario_source": args.scenario_source,
            "protocol": args.protocol,
            "mask_type": args.mask_type if args.protocol == "masking" else None,
            "n_cells": len(cells),
            "n_rows": int(len(results)),
            "provinces_used": provinces,
            "provinces_excluded": excluded,
            "active_nutrients": diag[provinces[0]]["active_nutrients"] if provinces else [],
            "non_actionable_by_province": {p: d["non_actionable"] for p, d in diag.items()},
            "per_method": per_method,
            "solver_success_by_province": {
                f"{prov}/{method}": {
                    "success": int(sub["solver_success"].sum()),
                    "total": int(len(sub)),
                }
                for (prov, method), sub in results.groupby(["province", "method"])
            },
        }
        if pool is not None:
            metrics["residual_pool"] = _clean(pool.coverage().to_dict("records"))
            metrics["residual_pool_meta"] = pool.meta
        if args.protocol == "masking":
            psum = protocol_shift_summary(cells)
            psum.to_csv(run_dir / "protocol_shift.csv", index=False, encoding="utf-8-sig")
            metrics["protocol_shift"] = {
                "n_cells": int(len(psum)),
                "abs_shift_mean": float(psum["abs_shift_mean"].mean()),
                "abs_shift_max": float(psum["abs_shift_max"].max()),
                "n_nonzero_mean": float(psum["n_nonzero"].mean()),
                "n_cells_per_unit": float(psum["n_cells"].iloc[0]),
            }

        write_json(run_dir / "diagnostics.json", _clean({"provinces": diag}))
        finalize_run(run_dir, _clean(metrics), config)

        print(f"[b2] {len(results)} 行 | 省 {len(provinces)} | 单元 {len(cells)} | 场景 {n_scen}")
        print(f"  场景源 {args.scenario_source} | 重复结构 {args.protocol} | 下界 {args.bounds_basis}")
        print(f"  排除省份: {excluded}")
        print()
        header = (
            f"{'方法':<5}{'|Δq|中位':>11}{'|Δq|p95':>10}{'变化率':>9}"
            f"{'gap均值':>10}{'p95':>8}{'可行(活跃)':>11}{'翻转率*':>9}{'失败':>6}"
        )
        print(header)
        for method in METHODS:
            m = per_method[method]

            def fmt(v):
                return "  n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:6.3f}"

            def fmt_dq(v):
                return "   n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:9.2f}"

            print(
                f"{method:<5}{fmt_dq(m.get('dq_ref_median')):>11}{fmt_dq(m.get('dq_ref_p95')):>10}"
                f"{fmt(m.get('dq_ref_change_rate')):>9}"
                f"{fmt(m['gap_mean']):>10}{fmt(m['gap_p95']):>8}"
                f"{fmt(m['feasible_active_rate']):>11}"
                f"{fmt(m['flip_rate']):>9}{m['solver_failures']:>6}"
            )
        print("  * 翻转率只看方向、对幅度盲，已降为辅助指标；主指标是 |Δq|（CHANGELOG §26.8）")
        print(f"\n[run] {run_dir}")

    except BaseException as exc:  # noqa: BLE001 - 失败必须留痕
        fail_run(run_dir, exc, config)
        raise


if __name__ == "__main__":
    main()
