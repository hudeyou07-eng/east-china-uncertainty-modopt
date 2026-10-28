"""M3 敏感性网格（R300–R303）统一驱动。

一次装配、四个网格共用同一套实例与场景，避免重复调用 ``Contract.instance``
（每次装配含 22 个 LP，7 省 × 多网格会明显拖慢）。

======  ================================================================
R300    机会约束删除：D3（含联合机会约束）vs D2（无营养约束）
        —— 隔离「机会约束」本身贡献了多少可行性/遗憾
R301    场景数 S ∈ {25, 50, 100, 200, 400}
        —— 找平台期，避免 S 太少导致 ε·S 取整过粗
R302    ε ∈ {0, 0.02, 0.05, 0.10}
        —— 预注册网格，看可行性对风险预算的响应
R303    目标权重 original(0.5/.25/.25) vs equal(1/3 each)
        —— 方向稳定性，禁止按结果挑权重
======  ================================================================

**证据等级：plumbing_only。** 场景仍是占位对数正态噪声（见 ``src/b2_scenarios.py``），
真值仍是冻结点估计。本脚本的用途是：

1. 把 M3 的代码路径打通，使真实后验到位后一条命令即可重跑；
2. 回答**与噪声结构无关**的问题——例如「ε 越小是否越难解」「S 越大可行率是否收敛」，
   这类单调性结论对场景生成器的具体形式不敏感；
3. 暴露结构性缺陷（如某省硬不可行），这类结论与场景无关、可直接采信。

**不用于**：报告任何绝对水平的可行率/遗憾值，或据此宣称主方法更优。

用法：
    python scripts/run_m3_sensitivity.py --profile smoke
    python scripts/run_m3_sensitivity.py --profile formal --grids R302
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.b2_evaluate import (  # noqa: E402
    flip_flags,
    joint_feasible,
    objective_gap,
    objective_totals,
)
from src.b2_problem import Contract, Instance  # noqa: E402
from src.b2_scenarios import deterministic, placeholder_scenarios  # noqa: E402
from src.io_utils import create_run_dir, fail_run, finalize_run, sha256_file, write_json  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402

PROFILES = {
    "smoke": {"repeats": 3},
    "formal": {"repeats": 20},
}

# 预注册网格。改这里等于改预注册，必须同步改 docs/EXPERIMENT_PLAN.md。
SCENARIO_GRID = (25, 50, 100, 200, 400)
EPSILON_GRID = (0.0, 0.02, 0.05, 0.10)
WEIGHT_SETS = {
    "original": {"cost": 0.5, "ghg": 0.25, "land": 0.25},
    "equal": {"cost": 1 / 3, "ghg": 1 / 3, "land": 1 / 3},
}
BASE_EPSILON = 0.05
BASE_SCENARIOS = 200

GRIDS = ("R300", "R301", "R302", "R303")


def solve(
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


def evaluate_point(
    inst: Instance,
    q: np.ndarray,
    q_ref: np.ndarray,
    truth_obj: np.ndarray,
    truth_nut: np.ndarray,
) -> dict:
    return {
        "feasible_all": bool(
            joint_feasible(
                q,
                truth_nut[0],
                inst.nutrient_offset,
                inst.nutrient_lower_raw,
                inst.nutrient_upper_raw,
            )
        ),
        "feasible_active": bool(
            joint_feasible(
                q,
                truth_nut[0],
                inst.nutrient_offset,
                inst.nutrient_lower_raw,
                inst.nutrient_upper_raw,
                active_mask=inst.active_mask,
            )
        ),
        "flips": int(flip_flags(q, q_ref, inst.baseline).sum()),
        "objective_gap": objective_gap(
            q, q_ref, truth_obj[0], inst.objective_weights, inst.q_lower, inst.q_upper
        ),
        **{f"total_{k}": v for k, v in objective_totals(q, inst).items()},
        **{f"q_{g}": float(q[i]) for i, g in enumerate(inst.groups)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="M3 sensitivity grids (R300-R303)")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="smoke")
    parser.add_argument("--grids", nargs="+", choices=GRIDS, default=list(GRIDS))
    parser.add_argument("--scenario", default="CDG")
    parser.add_argument("--seed", type=int, default=20261026)
    parser.add_argument("--cv-price", type=float, default=0.05)
    parser.add_argument("--cv-nutrient", type=float, default=0.05)
    parser.add_argument("--time-limit", type=float, default=120.0)
    parser.add_argument("--gap", type=float, default=1e-3)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    repeats = PROFILES[args.profile]["repeats"]
    run_id = args.run_id or f"M3_sensitivity_{args.profile}"
    run_dir = create_run_dir(ROOT / "outputs", run_id)

    contract = Contract.load()
    provinces, excluded = contract.complete_provinces()

    rows: list[dict] = []
    skipped: dict[str, str] = {}
    start = time.time()

    try:
        for province in provinces:
            inst = contract.instance(province, args.scenario)
            if not inst.hard_feasible:
                # 约束自相矛盾：任何网格点都解不出来，记录原因后跳过，
                # 不把它的失败计入「网格响应」——那会把结构缺陷误读成参数效应。
                skipped[province] = "+".join(inst.conflict_set)
                continue

            truth_obj, truth_nut = deterministic(inst)
            ref = solve(inst, truth_obj, truth_nut, True, 0.0, args.time_limit, args.gap)
            ref_ok = bool(ref.success) and np.isfinite(ref.q).all()
            if not ref_ok:
                ref = solve(inst, truth_obj, truth_nut, False, 0.0, args.time_limit, args.gap)
            q_ref = ref.q if np.isfinite(ref.q).all() else inst.baseline

            # 每个 (S, seed) 的场景只生成一次，四个网格复用，保证可比。
            max_s = max(SCENARIO_GRID) if "R301" in args.grids else BASE_SCENARIOS
            scenario_cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}

            def get_scenarios(n_scen: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
                key = (n_scen, seed)
                if key not in scenario_cache:
                    obj_s, nut_s = placeholder_scenarios(
                        inst, n_scen, seed, args.cv_price, args.cv_nutrient
                    )
                    scenario_cache[key] = (obj_s, nut_s)
                return scenario_cache[key]

            # ---- R300 / R303 / R302 共用 BASE_SCENARIOS ----
            for rep in range(repeats):
                seed = args.seed + rep
                obj_s, nut_s = get_scenarios(max_s if "R301" in args.grids else BASE_SCENARIOS, seed)

                # R300：D3 vs D2，同一场景集，唯一差别是机会约束
                if "R300" in args.grids:
                    for label, use_chance in (("D3_joint", True), ("D2_none", False)):
                        t0 = time.time()
                        res = solve(
                            inst, obj_s[:BASE_SCENARIOS], nut_s[:BASE_SCENARIOS],
                            use_chance, BASE_EPSILON if use_chance else 0.0,
                            args.time_limit, args.gap,
                        )
                        ok = bool(res.success) and np.isfinite(res.q).all()
                        rows.append(
                            {
                                "grid": "R300",
                                "setting": label,
                                "province": province,
                                "repeat": rep,
                                "n_scenarios": BASE_SCENARIOS,
                                "epsilon": BASE_EPSILON if use_chance else 0.0,
                                "objective_weights": "original",
                                "solver_success": ok,
                                "runtime": time.time() - t0,
                                **(evaluate_point(inst, res.q, q_ref, truth_obj, truth_nut) if ok else {}),
                            }
                        )

                # R303：目标权重 original vs equal
                if "R303" in args.grids:
                    for wname, weights in WEIGHT_SETS.items():
                        inst_w = contract.instance(province, args.scenario, objective_weights=weights)
                        t0 = time.time()
                        res = solve(
                            inst_w, obj_s[:BASE_SCENARIOS], nut_s[:BASE_SCENARIOS],
                            True, BASE_EPSILON, args.time_limit, args.gap,
                        )
                        ok = bool(res.success) and np.isfinite(res.q).all()
                        rows.append(
                            {
                                "grid": "R303",
                                "setting": wname,
                                "province": province,
                                "repeat": rep,
                                "n_scenarios": BASE_SCENARIOS,
                                "epsilon": BASE_EPSILON,
                                "objective_weights": wname,
                                "solver_success": ok,
                                "runtime": time.time() - t0,
                                **(evaluate_point(inst_w, res.q, q_ref, truth_obj, truth_nut) if ok else {}),
                            }
                        )

                # R302：ε 网格
                if "R302" in args.grids:
                    for eps in EPSILON_GRID:
                        t0 = time.time()
                        res = solve(
                            inst, obj_s[:BASE_SCENARIOS], nut_s[:BASE_SCENARIOS],
                            True, eps, args.time_limit, args.gap,
                        )
                        ok = bool(res.success) and np.isfinite(res.q).all()
                        rows.append(
                            {
                                "grid": "R302",
                                "setting": f"eps={eps}",
                                "province": province,
                                "repeat": rep,
                                "n_scenarios": BASE_SCENARIOS,
                                "epsilon": eps,
                                "objective_weights": "original",
                                "solver_success": ok,
                                "runtime": time.time() - t0,
                                **(evaluate_point(inst, res.q, q_ref, truth_obj, truth_nut) if ok else {}),
                            }
                        )

            # ---- R301：场景数网格（独立重复，避免与上面共用 S 造成混淆）----
            if "R301" in args.grids:
                for n_scen in SCENARIO_GRID:
                    for rep in range(repeats):
                        seed = args.seed + rep
                        obj_s, nut_s = get_scenarios(n_scen, seed)
                        t0 = time.time()
                        res = solve(
                            inst, obj_s, nut_s, True, BASE_EPSILON, args.time_limit, args.gap
                        )
                        ok = bool(res.success) and np.isfinite(res.q).all()
                        rows.append(
                            {
                                "grid": "R301",
                                "setting": f"S={n_scen}",
                                "province": province,
                                "repeat": rep,
                                "n_scenarios": n_scen,
                                "epsilon": BASE_EPSILON,
                                "objective_weights": "original",
                                "solver_success": ok,
                                "runtime": time.time() - t0,
                                **(evaluate_point(inst, res.q, q_ref, truth_obj, truth_nut) if ok else {}),
                            }
                        )
    except Exception as exc:  # pragma: no cover - 运行期兜底
        fail_run(run_dir, exc)
        raise

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "m3_grid_results.csv", index=False, encoding="utf-8-sig")

    # ---- 汇总 ----
    summary = (
        df.groupby(["grid", "setting"], as_index=False)
        .agg(
            n=("province", "size"),
            solve_rate=("solver_success", "mean"),
            feasible_active=("feasible_active", "mean"),
            flips=("flips", "mean"),
            gap_mean=("objective_gap", "mean"),
            runtime_mean=("runtime", "mean"),
        )
        .sort_values(["grid", "setting"])
    )
    summary.to_csv(run_dir / "m3_grid_summary.csv", index=False, encoding="utf-8-sig")

    # R303 的方向稳定性：两种权重下 q 的逐省最大差异
    weight_stability = []
    if "R303" in args.grids:
        sub = df[df["grid"].eq("R303") & df["solver_success"]]
        qcols = [c for c in sub.columns if c.startswith("q_")]
        if qcols:
            wide = sub.pivot_table(
                index=["province", "repeat"], columns="setting", values=qcols
            )
            for province in sorted(sub["province"].unique()):
                for rep in sorted(sub["repeat"].unique()):
                    a = sub[(sub.province.eq(province)) & (sub.repeat.eq(rep)) & (sub.setting.eq("original"))]
                    b = sub[(sub.province.eq(province)) & (sub.repeat.eq(rep)) & (sub.setting.eq("equal"))]
                    if a.empty or b.empty:
                        continue
                    delta = np.abs(a[qcols].to_numpy() - b[qcols].to_numpy()).max()
                    weight_stability.append(
                        {"province": province, "repeat": int(rep), "max_abs_delta_g": float(delta)}
                    )
    if weight_stability:
        pd.DataFrame(weight_stability).to_csv(
            run_dir / "r303_weight_stability.csv", index=False, encoding="utf-8-sig"
        )

    metrics = {
        "command": "m3-sensitivity",
        "profile": args.profile,
        "grids": args.grids,
        "scenario": args.scenario,
        "repeats": repeats,
        "provinces_used": provinces,
        "provinces_excluded": excluded,
        "provinces_skipped_hard_infeasible": skipped,
        "wall_seconds": round(time.time() - start, 1),
        "evidence_status": "plumbing_only",
        "placeholder_components": [
            "truth: 冻结点估计，非遮蔽前伪完整面板",
            "scenarios: 对数正态占位噪声，非 B1 后验",
            "repeats: 换种子重抽，非 5 折 × 20 遮蔽协议",
        ],
        "scenario_grid": list(SCENARIO_GRID),
        "epsilon_grid": list(EPSILON_GRID),
        "weight_sets": list(WEIGHT_SETS),
        "inputs": {
            name: sha256_file(ROOT / "data" / "processed" / name)
            for name in (
                "group_audit.csv",
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
        "summary": summary.to_dict("records"),
    }
    finalize_run(
        run_dir,
        metrics,
        {
            "command": "m3-sensitivity",
            "profile": args.profile,
            "grids": args.grids,
            "scenario": args.scenario,
            "repeats": repeats,
            "scenario_grid": list(SCENARIO_GRID),
            "epsilon_grid": list(EPSILON_GRID),
            "weight_sets": list(WEIGHT_SETS),
            "cv_price": args.cv_price,
            "cv_nutrient": args.cv_nutrient,
        },
    )

    print(f"[m3] {len(df)} 行 | 省 {len(provinces) - len(skipped)} 可用 | 跳过 {skipped}")
    print()
    print(
        summary.assign(
            solve_rate=lambda d: (d.solve_rate * 100).round(0),
            feasible_active=lambda d: (d.feasible_active * 100).round(0),
            flips=lambda d: d.flips.round(2),
            gap_mean=lambda d: d.gap_mean.round(3),
            runtime_mean=lambda d: d.runtime_mean.round(2),
        ).to_string(index=False)
    )
    print()
    print(f"[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
