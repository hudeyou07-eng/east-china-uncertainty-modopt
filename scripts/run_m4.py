"""M4 分省情景与稳健性（R400–R409）。

## 这个脚本做什么、不做什么

M4 的预注册目标是「七地区 × 三情景的方向标签 + 三层敏感性」。
2026-10-28 的 `R-2026-10-28-c` 把地区改成 **6 个决策省**（上海只做可得性说明，见 R401）。

本脚本实现 **`provinces` 块**（R400 / R402–R406）：

* 逐 (省, 情景) 装配 `k6_price` 实例；
* 求 D1（后验均值确定性）与 D3（后验场景 + 联合营养机会约束）；
* 按 `DIRECTION_TOL = 1.0 g/day`（`src/b2_evaluate.py`）给出**方向标签**。

其余三块**故意未实现**，因为它们各自缺一条协议定义，编造会让结果不可审计：

| 块 | run | 缺什么 |
|---|---|---|
| `looro` | R407 | 「leave-one-region-out **fit**」拟合的是什么？当前管道里唯一的跨省拟合是 D0 的池化价与 B1 残差池；前者可以留一重算，后者没有留一机制。需先定：留一时重算池化价、残差池保持不变，还是两者都留一 |
| `delta` | R408 | 「δ 作用于残差 SD」需要 `posterior_scenarios` 暴露尺度参数；当前函数没有该参数，事后缩放 `(1+δ)·(s − 点估计)` 是**一个新的协议**，需先写进 Plan |
| `bounds` | R409 | 「low/mid/high/worst 端点」需要 `decision_bounds.csv` 的四套变体；当前只有一套冻结边界，变体如何生成（按分位数？按基线比例？）未定义 |

## 标签规则（写死在代码里，论文方法节须照抄）

对每个 (省, 情景, 组)：

```
d1 = sign(q_D1 − baseline)   # |Δ| < 1.0 g/day 记为 0
d3 = sign(q_D3 − baseline)
label = d1 == d3 == +1 → stable-up
        d1 == d3 == −1 → stable-down
        d1 == d3 ==  0 → stable-neutral
        d1 != d3       → data-sensitive
```

`direction_agreement` = 该 (省, 情景) 下 `d1 == d3` 的组占比。
这是 B4 结论门「direction agreement ≥ 90%」的**组级分母**。

## 用法

    # 冒烟：1 省 × 1 情景 × 20 场景
    python scripts/run_m4.py --block provinces --provinces 安徽 --scenario CDG --n-scenarios 20

    # 正式：6 省 × 3 情景 × 200 场景（约 5–15 分钟）
    python scripts/run_m4.py --block provinces

    # 只装配不求解
    python scripts/run_m4.py --block provinces --dry-run
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.b2_evaluate import DIRECTION_TOL, direction, joint_feasible, objective_totals  # noqa: E402
from src.b2_problem import OBJECTIVES, Contract  # noqa: E402
from src.b2_scenarios import (  # noqa: E402
    B1_METHOD_DEFAULT,
    B1_RUN_DEFAULT,
    deterministic,
    load_residual_pool,
    posterior_scenarios,
)
from src.io_utils import create_run_dir, fail_run, finalize_run  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402

OUTPUT_ROOT = ROOT / "outputs"
PROVINCES_DEFAULT = ["安徽", "山东", "江苏", "江西", "浙江", "福建"]
SCENARIOS_DEFAULT = ["HEAL_base", "CDG", "EAT"]
BLOCKS = {
    "provinces": "R400/R402–R406：逐省逐情景的方向标签",
    "looro": "R407：leave-one-province-out 重算 D0 池化价",
    "delta": "R408：δ 残差尺度敏感性（对数域乘性缩放）",
    "bounds": "R409：边界网格 low/mid/high/worst",
}

# 三个敏感性块的协议定义（2026-10-28 作者确认，写死在代码里，论文方法节须照抄）
PROTOCOLS = {
    "looro": (
        "R407：逐省留一，**只重算 D0 的池化价**（去掉该省后对剩余省取均值），"
        "B1 残差池保持不变（残差池没有省份留一机制，硬造会引入新假设）。"
        "对每个 fold 与每个**未被移除**的省，求 D0 解，与全样本 D0 比较位移与方向。"
    ),
    "delta": (
        "R408：δ 作用于**乘性残差的对数域**，即 mult' = exp((1+δ)·log(mult))，"
        "δ ∈ {−0.5, 0, +0.5}。与 B1 残差的定义同域，避免线性域缩放产生负价格。"
        "对每个 δ 求 D3，与 δ=0 的解比较逐组位移。"
    ),
    "bounds": (
        "R409：low = 三情景下界/上界的逐元素最小值；high = 逐元素最大值；"
        "mid = HEAL_base 的冻结边界；worst = 三情景边界**交集**（max 下界、min 上界，"
        "可能为空 → 记为 infeasible）。对每个变体求 D1，与 mid 比较位移。"
    ),
}


def _solve(inst, objective_coeff: np.ndarray, nutrient_coeff: np.ndarray, use_chance: bool,
           epsilon: float, time_limit: float, gap: float):
    """与 scripts/run_b2.py 的 _solve 保持同一语义（只用 active_mask 内的营养行）。"""
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


def label_for(d1: float, d3: float) -> str:
    """方向标签。规则见模块 docstring，论文方法节须照抄。"""
    if d1 != d3:
        return "data-sensitive"
    if d1 > 0:
        return "stable-up"
    if d1 < 0:
        return "stable-down"
    return "stable-neutral"


LABELS = ("stable-up", "stable-down", "stable-neutral", "data-sensitive")


def run_provinces_block(contract: Contract, args, pool, run_dir: Path) -> dict:
    """R400/R402–R406：逐 (省, 情景) 求 D1/D3 并给方向标签。"""
    ok_prov, excluded = contract.complete_provinces()
    provinces = [p for p in (args.provinces or PROVINCES_DEFAULT) if p in ok_prov]
    skipped = {p: excluded[p] for p in (args.provinces or []) if p not in ok_prov}

    label_rows, cell_rows = [], []
    for province in provinces:
        for scenario in args.scenario:
            try:
                inst = contract.instance(
                    province, scenario, epsilon=args.epsilon, bounds_basis=args.bounds_basis
                )
            except ValueError as exc:  # 价格缺失等装配错误：必须显式记录，不得静默跳过
                cell_rows.append({
                    "province": province, "scenario": scenario, "status": "assemble_failed",
                    "detail": str(exc), "n_groups": 0, "direction_agreement": float("nan"),
                    **{f"n_{lb}": 0 for lb in LABELS},
                })
                continue

            if not inst.hard_feasible:
                cell_rows.append({
                    "province": province, "scenario": scenario, "status": "hard_infeasible",
                    "detail": "+".join(inst.conflict_set), "n_groups": inst.k_count,
                    "direction_agreement": float("nan"),
                    **{f"n_{lb}": 0 for lb in LABELS},
                })
                continue

            if args.dry_run:
                cell_rows.append({
                    "province": province, "scenario": scenario, "status": "dry_run",
                    "detail": "", "n_groups": inst.k_count, "direction_agreement": float("nan"),
                    **{f"n_{lb}": 0 for lb in LABELS},
                })
                continue

            obj_p, nut_p = deterministic(inst)
            obj_s, nut_s = posterior_scenarios(inst, args.n_scenarios, args.seed, pool=pool)
            # D1 = 后验均值 + 硬营养约束 → use_chance=True, epsilon=0（见 _d0 的注释）
            res1 = _solve(inst, obj_p, nut_p, True, 0.0, args.time_limit, args.gap)
            res3 = _solve(inst, obj_s, nut_s, True, args.epsilon, args.time_limit, args.gap)

            ok1 = bool(res1.success) and np.isfinite(res1.q).all()
            ok3 = bool(res3.success) and np.isfinite(res3.q).all()
            q1 = res1.q if ok1 else np.full(inst.k_count, np.nan)
            q3 = res3.q if ok3 else np.full(inst.k_count, np.nan)
            d1 = direction(q1, inst.baseline) if ok1 else np.full(inst.k_count, np.nan)
            d3 = direction(q3, inst.baseline) if ok3 else np.full(inst.k_count, np.nan)

            counts = {lb: 0 for lb in LABELS}
            for k, group in enumerate(inst.groups):
                label = label_for(d1[k], d3[k]) if (ok1 and ok3) else "solver_failed"
                if label in counts:
                    counts[label] += 1
                label_rows.append({
                    "province": province, "scenario": scenario, "group_id": group,
                    "baseline_g": float(inst.baseline[k]),
                    "q_d1": float(q1[k]), "q_d3": float(q3[k]),
                    "delta_d1": float(q1[k] - inst.baseline[k]),
                    "delta_d3": float(q3[k] - inst.baseline[k]),
                    "dir_d1": float(d1[k]), "dir_d3": float(d3[k]),
                    "dq_d1_d3": float(abs(q1[k] - q3[k])),
                    "label": label,
                })

            agreement = float(np.mean(d1 == d3)) if (ok1 and ok3) else float("nan")
            feas3 = bool(
                ok3 and joint_feasible(
                    q3, nut_p[0], inst.nutrient_offset,
                    inst.nutrient_lower_raw, inst.nutrient_upper_raw,
                )
            )
            totals = objective_totals(q3, inst) if ok3 else {k: float("nan") for k in OBJECTIVES}
            cell_rows.append({
                "province": province, "scenario": scenario, "status": "ok",
                "detail": "", "n_groups": inst.k_count,
                "solver_success_d1": ok1, "solver_success_d3": ok3,
                "direction_agreement": agreement,
                "feasible_all_d3": feas3,
                "objective_gap_d1_d3_max_abs": float(np.max(np.abs(q1 - q3))) if (ok1 and ok3) else float("nan"),
                **{f"n_{lb}": counts[lb] for lb in LABELS},
                **{f"total_{k}": float(v) for k, v in totals.items()},
            })

    pd.DataFrame(label_rows).to_csv(run_dir / "m4_direction_labels.csv", index=False, encoding="utf-8-sig")
    cells = pd.DataFrame(cell_rows)
    cells.to_csv(run_dir / "m4_province_scenario.csv", index=False, encoding="utf-8-sig")

    ok_cells = cells[cells["status"] == "ok"] if len(cells) else cells
    label_counts = {lb: int(cells[f"n_{lb}"].sum()) if f"n_{lb}" in cells else 0 for lb in LABELS}
    return {
        "block": "provinces",
        "provinces": provinces,
        "skipped_provinces": skipped,
        "scenarios": list(args.scenario),
        "n_cells": int(len(cells)),
        "n_cells_ok": int(len(ok_cells)),
        "n_cells_hard_infeasible": int((cells["status"] == "hard_infeasible").sum()) if len(cells) else 0,
        "label_counts": label_counts,
        "label_share": {
            lb: (round(v / max(1, sum(label_counts.values())), 4)) for lb, v in label_counts.items()
        },
        "direction_agreement_mean": float(ok_cells["direction_agreement"].mean())
        if len(ok_cells) and ok_cells["direction_agreement"].notna().any() else None,
        "direction_agreement_min": float(ok_cells["direction_agreement"].min())
        if len(ok_cells) and ok_cells["direction_agreement"].notna().any() else None,
        "feasible_all_rate_d3": float(ok_cells["feasible_all_d3"].mean()) if len(ok_cells) else None,
        "gate_90pct_cells": int((ok_cells["direction_agreement"] >= 0.90).sum()) if len(ok_cells) else 0,
    }


def _provinces_for_run(contract: Contract, args) -> tuple[list[str], dict]:
    ok, excluded = contract.complete_provinces()
    wanted = args.provinces or PROVINCES_DEFAULT
    return [p for p in wanted if p in ok], {p: excluded[p] for p in wanted if p not in ok}


def _d0(contract: Contract, province: str, scenario: str, args, pooled: np.ndarray | None = None):
    """D0：跨省合并价 + 后验均值 + 硬营养约束。``pooled`` 给定时用它替代全样本池化价。

    ⚠ 营养约束在求解器里是**经由机会约束的 z 机制**实现的：``use_chance_constraint=False``
    不是「关掉机会约束、保留硬营养」，而是**连营养约束一起去掉**（那正是 D2 的定义）。
    所以确定性解（D0/D1）必须传 ``use_chance=True, epsilon=0.0``——与 ``run_b2.py`` 一致。
    """
    inst = contract.instance(
        province, scenario, epsilon=args.epsilon, bounds_basis=args.bounds_basis,
        price_mode=None if pooled is not None else "pooled",
        price_override=pooled,
    )
    if not inst.hard_feasible:
        return inst, None
    obj, nut = deterministic(inst)
    res = _solve(inst, obj, nut, True, 0.0, args.time_limit, args.gap)
    ok = bool(res.success) and np.isfinite(res.q).all()
    return inst, (res.q if ok else None)


def run_looro_block(contract: Contract, args, run_dir: Path) -> dict:
    """R407：逐省留一，只重算 D0 的池化价（协议见 ``PROTOCOLS['looro']``）。"""
    provinces, skipped = _provinces_for_run(contract, args)
    panel = contract.price_panel().reindex(provinces)
    rows = []
    for scenario in args.scenario:
        base: dict[str, np.ndarray | None] = {}
        groups: tuple[str, ...] = ()
        for province in provinces:
            inst, q = _d0(contract, province, scenario, args)
            groups = inst.groups
            base[province] = q
        for fold in provinces:
            keep = [p for p in provinces if p != fold]
            pooled = panel.loc[keep].mean(axis=0, skipna=True).to_numpy(dtype=float)
            for province in keep:
                ref = base.get(province)
                if ref is None:
                    continue
                _, q = _d0(contract, province, scenario, args, pooled=pooled)
                if q is None:
                    rows.append({
                        "fold_removed": fold, "province": province, "scenario": scenario,
                        "solver_success": False, "dq_max": float("nan"),
                        "n_direction_changed": None, "changed_groups": "",
                    })
                    continue
                dq = np.abs(q - ref)
                changed = np.flatnonzero(dq >= DIRECTION_TOL)
                rows.append({
                    "fold_removed": fold, "province": province, "scenario": scenario,
                    "solver_success": True, "dq_max": float(dq.max()),
                    "n_direction_changed": int(len(changed)),
                    "changed_groups": "|".join(groups[i] for i in changed),
                })
    frame = pd.DataFrame(rows)
    frame.to_csv(run_dir / "m4_looro.csv", index=False, encoding="utf-8-sig")
    ok = frame[frame["solver_success"]] if len(frame) else frame
    return {
        "block": "looro",
        "protocol": PROTOCOLS["looro"],
        "provinces": provinces,
        "skipped_provinces": skipped,
        "scenarios": list(args.scenario),
        "n_folds": len(provinces),
        "n_cells": int(len(frame)),
        "n_cells_solved": int(len(ok)),
        "n_cells_with_change": int((ok["n_direction_changed"] > 0).sum()) if len(ok) else 0,
        "dq_max_median": float(ok["dq_max"].median()) if len(ok) else None,
        "dq_max_p95": float(ok["dq_max"].quantile(0.95)) if len(ok) else None,
        "dq_max_abs": float(ok["dq_max"].max()) if len(ok) else None,
    }


def run_delta_block(contract: Contract, args, pool, run_dir: Path) -> dict:
    """R408：δ 作用于乘性残差的对数域（协议见 ``PROTOCOLS['delta']``）。"""
    provinces, skipped = _provinces_for_run(contract, args)
    deltas = (-0.5, 0.0, 0.5)
    rows = []
    for province in provinces:
        for scenario in args.scenario:
            inst = contract.instance(
                province, scenario, epsilon=args.epsilon, bounds_basis=args.bounds_basis
            )
            if not inst.hard_feasible:
                rows.append({
                    "province": province, "scenario": scenario, "delta": None,
                    "solver_success": False, "detail": "+".join(inst.conflict_set),
                    "dq_max_vs_delta0": float("nan"), "n_direction_changed": None,
                })
                continue
            obj_p, _nut_p = deterministic(inst)
            obj_s, nut_s = posterior_scenarios(inst, args.n_scenarios, args.seed, pool=pool)
            point = obj_p[0, 0, :]
            mult = obj_s[:, 0, :] / point
            solved: dict[float, np.ndarray | None] = {}
            for delta in deltas:
                obj_scaled = np.array(obj_s, dtype=float, copy=True)
                obj_scaled[:, 0, :] = (mult ** (1.0 + delta)) * point
                res = _solve(inst, obj_scaled, nut_s, True, args.epsilon, args.time_limit, args.gap)
                solved[delta] = res.q if (res.success and np.isfinite(res.q).all()) else None
            ref = solved.get(0.0)
            for delta in deltas:
                q = solved[delta]
                ok = q is not None and ref is not None
                dq = np.abs(q - ref) if ok else np.full(inst.k_count, np.nan)
                changed = int((dq >= DIRECTION_TOL).sum()) if ok else None
                rows.append({
                    "province": province, "scenario": scenario, "delta": delta,
                    "solver_success": bool(ok), "detail": "",
                    "dq_max_vs_delta0": float(np.nanmax(dq)) if ok else float("nan"),
                    "n_direction_changed": changed,
                })
    frame = pd.DataFrame(rows)
    frame.to_csv(run_dir / "m4_delta.csv", index=False, encoding="utf-8-sig")
    ok = frame[frame["solver_success"] & (frame["delta"] != 0.0)] if len(frame) else frame
    return {
        "block": "delta",
        "protocol": PROTOCOLS["delta"],
        "provinces": provinces,
        "skipped_provinces": skipped,
        "scenarios": list(args.scenario),
        "deltas": list(deltas),
        "n_cells": int(len(frame)),
        "n_cells_solved": int(frame["solver_success"].sum()) if len(frame) else 0,
        "dq_max_median_off0": float(ok["dq_max_vs_delta0"].median()) if len(ok) else None,
        "dq_max_abs_off0": float(ok["dq_max_vs_delta0"].max()) if len(ok) else None,
        "n_cells_with_change_off0": int((ok["n_direction_changed"] > 0).sum()) if len(ok) else 0,
    }


def run_bounds_block(contract: Contract, args, run_dir: Path) -> dict:
    """R409：边界网格 low/mid/high/worst（协议见 ``PROTOCOLS['bounds']``）。

    注意：low/high/worst 由**三个情景的边界**构造，因此无论 ``--scenario`` 传什么，
    都用 ``SCENARIOS_DEFAULT`` 三套边界来定义网格；求解统一在 ``HEAL_base`` 上做参照。
    """
    provinces, skipped = _provinces_for_run(contract, args)
    rows = []
    for province in provinces:
        lowers, uppers = [], []
        for scenario in SCENARIOS_DEFAULT:
            lo, up, _extra = contract.intake_bounds(province, scenario)
            lowers.append(np.asarray(lo, dtype=float))
            uppers.append(np.asarray(up, dtype=float))
        lo_stack = np.vstack(lowers)
        up_stack = np.vstack(uppers)
        boxes = {
            "low": (lo_stack.min(axis=0), up_stack.min(axis=0)),
            "mid": (lowers[SCENARIOS_DEFAULT.index("HEAL_base")], uppers[SCENARIOS_DEFAULT.index("HEAL_base")]),
            "high": (lo_stack.max(axis=0), up_stack.max(axis=0)),
            "worst": (lo_stack.max(axis=0), up_stack.min(axis=0)),
        }
        solved: dict[str, np.ndarray | None] = {}
        messages: dict[str, str] = {}
        for variant, (lo, up) in boxes.items():
            empty = bool(np.any(lo > up))
            inst = contract.instance(
                province, "HEAL_base", epsilon=args.epsilon, bounds_basis=args.bounds_basis
            )
            if empty or not inst.hard_feasible:
                rows.append({
                    "province": province, "variant": variant, "solver_success": False,
                    "detail": "empty_box" if empty else "+".join(inst.conflict_set),
                    "dq_max_vs_mid": float("nan"), "n_direction_changed": None,
                    "q_lower": "", "q_upper": "",
                })
                solved[variant] = None
                continue
            inst_v = replace(inst, q_lower=lo, q_upper=up)
            obj, nut = deterministic(inst_v)
            # D1 = 后验均值 + 硬营养约束 → use_chance=True, epsilon=0（见 _d0 的注释）
            res = _solve(inst_v, obj, nut, True, 0.0, args.time_limit, args.gap)
            q = res.q if (res.success and np.isfinite(res.q).all()) else None
            solved[variant] = q
            if q is None:
                # 把求解器自己的话记下来：不可行 / 超时 / 其他，必须在结果表里可区分
                messages[variant] = f"solver: {getattr(res, 'message', 'unknown')}"
        ref = solved.get("mid")
        for variant in boxes:
            q = solved[variant]
            ok = q is not None and ref is not None
            dq = np.abs(q - ref) if ok else np.full(contract.groups.__len__(), np.nan)
            changed = int((dq >= DIRECTION_TOL).sum()) if ok else None
            for i, row in enumerate(rows):
                if row["province"] == province and row["variant"] == variant:
                    rows[i].update({
                        "dq_max_vs_mid": float(np.nanmax(dq)) if ok else float("nan"),
                        "n_direction_changed": changed,
                    })
                    break
            else:
                rows.append({
                    "province": province, "variant": variant, "solver_success": bool(ok),
                    "detail": messages.get(variant, ""),
                    "dq_max_vs_mid": float(np.nanmax(dq)) if ok else float("nan"),
                    "n_direction_changed": changed, "q_lower": "", "q_upper": "",
                })
    frame = pd.DataFrame(rows)
    frame.to_csv(run_dir / "m4_bounds.csv", index=False, encoding="utf-8-sig")
    ok = frame[frame["solver_success"] & (frame["variant"] != "mid")] if len(frame) else frame
    return {
        "block": "bounds",
        "protocol": PROTOCOLS["bounds"],
        "provinces": provinces,
        "skipped_provinces": skipped,
        "variants": ["low", "mid", "high", "worst"],
        "n_cells": int(len(frame)),
        "n_cells_solved": int(frame["solver_success"].sum()) if len(frame) else 0,
        "n_infeasible": int((~frame["solver_success"]).sum()) if len(frame) else 0,
        "dq_max_median_off_mid": float(ok["dq_max_vs_mid"].median()) if len(ok) else None,
        "dq_max_abs_off_mid": float(ok["dq_max_vs_mid"].max()) if len(ok) else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="M4 分省情景与稳健性（R400–R409）")
    parser.add_argument("--block", choices=sorted(BLOCKS), required=True)
    parser.add_argument("--scope", default="k6_price", choices=["k4_official", "k6_price", "k3_prereg", "k5_notrace"])
    parser.add_argument("--bounds-basis", default="ear", choices=["ear", "rni"])
    parser.add_argument("--provinces", nargs="*", default=None, help="默认 6 个决策省")
    parser.add_argument("--scenario", nargs="*", default=SCENARIOS_DEFAULT)
    parser.add_argument("--n-scenarios", type=int, default=200, help="训练场景数（M3 结论：200 在稳定平台）")
    parser.add_argument("--epsilon", type=float, default=0.05)
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--gap", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--b1-run", default=B1_RUN_DEFAULT)
    parser.add_argument("--b1-method", default=B1_METHOD_DEFAULT)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_id = args.run_id or f"M4_{args.block}"
    run_dir = create_run_dir(OUTPUT_ROOT, run_id)
    config = {
        "command": "m4",
        "block": args.block,
        "block_definition": BLOCKS[args.block],
        "scope": args.scope,
        "bounds_basis": args.bounds_basis,
        "scenario": list(args.scenario),
        "n_scenarios": args.n_scenarios,
        "epsilon": args.epsilon,
        "time_limit": args.time_limit,
        "gap": args.gap,
        "seed": args.seed,
        "b1_run": args.b1_run,
        "b1_method": args.b1_method,
        "dry_run": bool(args.dry_run),
        "direction_tol": DIRECTION_TOL,
        "label_rule": "d1==d3==+1 stable-up / ==-1 stable-down / ==0 stable-neutral / d1!=d3 data-sensitive",
    }
    try:
        contract = Contract.load_scope(args.scope)
        pool = None
        if args.block in {"provinces", "delta"} and not args.dry_run:
            pool = load_residual_pool(OUTPUT_ROOT / args.b1_run, method=args.b1_method,
                                      mask_type="single_cell", groups=contract.groups)

        if args.block == "provinces":
            metrics = run_provinces_block(contract, args, pool, run_dir)
        elif args.block == "looro":
            metrics = run_looro_block(contract, args, run_dir)
        elif args.block == "delta":
            metrics = run_delta_block(contract, args, pool, run_dir)
        else:
            metrics = run_bounds_block(contract, args, run_dir)

        metrics.update({
            "run_id": args.block,
            "evidence_status": "formal" if not args.dry_run and args.n_scenarios >= 200 else "smoke",
            "note": (
                "provinces 块产出 R400/R402–R406 的方向标签；"
                "looro/delta/bounds 分别产出 R407/R408/R409。"
                "四个块合起来才构成完整的 B4 证据，单块不可单独引用。"
            ),
        })
        finalize_run(run_dir, metrics, config)
        print(f"[M4:{args.block}] {run_dir}")
        for key in ("n_cells", "n_cells_solved", "n_cells_ok", "n_cells_with_change",
                    "direction_agreement_mean", "dq_max_median", "dq_max_abs",
                    "dq_max_median_off0", "dq_max_abs_off0", "dq_max_median_off_mid",
                    "dq_max_abs_off_mid", "n_infeasible", "label_counts"):
            if metrics.get(key) is not None:
                print(f"  {key} = {metrics[key]}")
        return 0
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - 必须留下 FAILED.json，不得静默
        fail_run(run_dir, exc, config)
        raise


if __name__ == "__main__":
    sys.exit(main())
