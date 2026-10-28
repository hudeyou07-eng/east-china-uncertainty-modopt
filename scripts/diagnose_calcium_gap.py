"""钙的结构性缺口：最优解到底提供了多少钙，把它顶到上限要付多少代价？

## 为什么单独查钙

K=6 决策口径下，11 个硬营养素里**只有钙**被排除出机会约束——它在
`box ∩ 联合约束` 内根本到不了下界，放进去会让 `Σz_s ≤ floor(εS)` 直接不可行。
排除是对的，但「排除」这个动作本身需要向读者交代：

1. 模型推荐膳食的钙**是否低于现状**？（若是，说明优化在拿营养换成本，问题严重）
2. 缺口是**模型缺陷**还是**膳食结构事实**？
3. 若强行把钙顶上去，代价多大？值不值得改成软约束？

本脚本回答这三问，不预设结论。

## 指标

* ``baseline_ca``：观测基线的全膳食钙（决策组 + 非决策组 offset），mg/day；
* ``optimal_ca``：确定性最优解的全膳食钙；
* ``ear_ca``：EAR 口径的钙需求（650 mg/day，18–49 岁成人）；
* ``max_reachable_ca``：在决策域内把钙顶到最大时的全膳食钙；
* ``marginal_cost_per_mg``：把钙下界从当前水平逐步上抬时，每多 1 mg 钙
  要多花多少钱（CNY/day）。用目标值差除以钙增量。

## 口径

* 决策口径 `k6_price`，营养下界 `ear`（2026-10-27 作者裁定）。
* 求解用确定性单场景、硬约束（与 D1 同口径），不含机会约束——
  这里问的是「膳食结构能不能供出钙」，与场景不确定性无关。
* 把钙加进约束时，**其余营养素仍按 active_mask 处理**，即不改变原模型，
  只额外加一条钙下界。

## 证据等级

``structural``：求解是精确 LP/MILP，但只针对点估计，不含场景不确定性。

用法：
    python scripts/diagnose_calcium_gap.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.b2_problem import Contract, reachable_bounds  # noqa: E402
from src.b2_evaluate import objective_totals  # noqa: E402
from src.b2_scenarios import deterministic  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402
from src.io_utils import create_run_dir, finalize_run  # noqa: E402

SCOPE = "k6_price"
BASIS = "ear"
SCENARIOS = ("CDG", "EAT", "HEAL_base")
NUTRIENT = "钙"


def _solve(inst, extra_lower: float | None = None):
    """确定性硬约束求解。``extra_lower`` 给定时额外加一条「钙 ≥ 该值」。"""
    obj, nut = deterministic(inst)
    mask = inst.active_mask
    lower = inst.nutrient_lower[mask]
    extra = list(inst.extra_constraints)
    if extra_lower is not None:
        j = inst.nutrients.index(NUTRIENT)
        if mask[j]:
            lower = lower.copy()
            lower[list(np.nonzero(mask)[0]).index(j)] = extra_lower
        else:
            coeff = np.zeros(len(inst.groups))
            coeff[:] = inst.nutrient_coeff[0][j]
            extra.append((coeff, extra_lower, np.inf))
    return solve_chance_modopt(
        obj,
        nut[:, mask, :],
        lower,
        inst.nutrient_upper[mask],
        inst.q_lower,
        inst.q_upper,
        inst.objective_weights,
        epsilon=0.0,
        extra_constraints=extra,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_calcium_gap")
    args = ap.parse_args()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    contract = Contract.load_scope(SCOPE)
    usable, _ = contract.complete_provinces()

    rows: list[dict] = []
    margin: list[dict] = []

    for scenario in SCENARIOS:
        for province in usable:
            inst = contract.instance(province, scenario, bounds_basis=BASIS)
            j = inst.nutrients.index(NUTRIENT)
            n_ca = inst.nutrient_coeff[0][j]
            offset_ca = float(inst.nutrient_offset[j])
            ear_ca = float(inst.nutrient_lower_raw[j])

            # 决策组在基线下的钙 + 非决策组 offset = 观测基线全膳食钙
            baseline_ca = float(n_ca @ inst.baseline) + offset_ca
            # 决策域内决策组能提供的钙上限
            _, hi = reachable_bounds(
                inst.nutrient_coeff[0], inst.q_lower, inst.q_upper, inst.extra_constraints
            )
            max_reachable_ca = float(hi[j]) + offset_ca

            res = _solve(inst)
            if not res.success:
                rows.append({
                    "scenario": scenario, "province": province,
                    "baseline_ca": baseline_ca, "optimal_ca": float("nan"),
                    "ear_ca": ear_ca, "max_reachable_ca": max_reachable_ca,
                    "optimal_over_ear": float("nan"),
                    "baseline_over_ear": baseline_ca / ear_ca,
                    "solver_success": False,
                })
                continue
            q = np.asarray(res.q, dtype=float)
            optimal_ca = float(n_ca @ q) + offset_ca
            base_obj = float(res.objective)

            rows.append({
                "scenario": scenario, "province": province,
                "baseline_ca": baseline_ca,
                "optimal_ca": optimal_ca,
                "ear_ca": ear_ca,
                "max_reachable_ca": max_reachable_ca,
                "optimal_over_ear": optimal_ca / ear_ca,
                "baseline_over_ear": baseline_ca / ear_ca,
                "max_over_ear": max_reachable_ca / ear_ca,
                "optimal_vs_baseline": optimal_ca / baseline_ca,
                "solver_success": True,
            })

            # 边际代价：把钙下界从「当前最优」逐步抬到「可达上限」
            # 注意求解器里的下界是**扣掉 offset 的净额**，故要减去 offset。
            #
            # 目标值差换成「元/人/天」：``objective_totals`` 给出实际成本，
            # 归一化目标值本身无量纲，直接报 0.0006/mg 读者无法判断大小。
            base_totals = objective_totals(q, inst)
            span = max_reachable_ca - optimal_ca
            if span <= 1.0:
                continue
            for frac in (0.25, 0.5, 0.75, 0.95):
                target_total = optimal_ca + frac * span
                target_net = target_total - offset_ca
                r2 = _solve(inst, extra_lower=target_net)
                if r2.success:
                    t2 = objective_totals(np.asarray(r2.q, dtype=float), inst)
                    delta_ca = target_total - optimal_ca
                    delta_cost = t2["cost"] - base_totals["cost"]
                    margin.append({
                        "scenario": scenario, "province": province,
                        "frac": frac,
                        "target_total_ca": target_total,
                        "success": True,
                        "delta_objective": float(r2.objective) - base_obj,
                        "delta_objective_pct": (
                            (float(r2.objective) - base_obj) / base_obj * 100
                            if base_obj != 0 else float("nan")
                        ),
                        "delta_ca": delta_ca,
                        "delta_cost_cny_day": delta_cost,
                        "cny_per_100mg": delta_cost / delta_ca * 100 if delta_ca > 0 else float("nan"),
                    })
                else:
                    # 单营养素可达上限不等于**联合**可达：抬到高位时会被其它约束顶住
                    margin.append({
                        "scenario": scenario, "province": province,
                        "frac": frac, "target_total_ca": target_total,
                        "success": False,
                        "delta_objective": float("nan"),
                        "delta_objective_pct": float("nan"),
                        "delta_ca": target_total - optimal_ca,
                        "delta_cost_cny_day": float("nan"),
                        "cny_per_100mg": float("nan"),
                    })

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "calcium_gap.csv", index=False, encoding="utf-8-sig")
    mdf = pd.DataFrame(margin)
    if not mdf.empty:
        mdf.to_csv(run_dir / "calcium_marginal_cost.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 200)
    print("=== 钙：基线 / 最优 / EAR / 可达上限（mg/day） ===")
    show = df[df["solver_success"]].copy()
    print(
        show[["scenario", "province", "baseline_ca", "optimal_ca", "ear_ca",
              "max_reachable_ca", "optimal_over_ear", "baseline_over_ear"]]
        .round(3).to_string(index=False)
    )

    print("\n=== 汇总（按情景） ===")
    agg = show.groupby("scenario").agg(
        optimal_over_ear_min=("optimal_over_ear", "min"),
        optimal_over_ear_max=("optimal_over_ear", "max"),
        baseline_over_ear_min=("baseline_over_ear", "min"),
        baseline_over_ear_max=("baseline_over_ear", "max"),
        max_over_ear_min=("max_over_ear", "min"),
        max_over_ear_max=("max_over_ear", "max"),
        optimal_vs_baseline_min=("optimal_vs_baseline", "min"),
        optimal_vs_baseline_max=("optimal_vs_baseline", "max"),
    ).round(3)
    print(agg.to_string())

    if not mdf.empty:
        ok = mdf[mdf["success"]]
        print("\n=== 把钙顶上去的代价（元/人/天，每 +100 mg 钙） ===")
        if not ok.empty:
            print(
                ok.pivot_table(index=["scenario", "province"], columns="frac",
                               values="cny_per_100mg").round(3).to_string()
            )
            print("\n=== 同一操作的归一化目标变化（%） ===")
            print(
                ok.pivot_table(index=["scenario", "province"], columns="frac",
                               values="delta_objective_pct").round(2).to_string()
            )
        fail = mdf[~mdf["success"]]
        if not fail.empty:
            print(f"\n抬到高位后不可行的格子：{len(fail)} 个"
                  "（单营养素可达上限不等于联合可达，属预期）")

    finalize_run(
        run_dir,
        {
            "command": "diagnose-calcium-gap",
            "evidence_status": "structural",
            "scope": SCOPE,
            "bounds_basis": BASIS,
            "scenarios": list(SCENARIOS),
            "question": (
                "最优膳食的钙是否低于观测基线；缺口是模型缺陷还是膳食结构事实；"
                "强行顶高钙的边际代价"
            ),
            "gap_rows": df.to_dict("records"),
            "marginal_rows": mdf.to_dict("records") if not mdf.empty else [],
            "summary_by_scenario": agg.reset_index().to_dict("records"),
        },
        {"command": "diagnose-calcium-gap", "scope": SCOPE, "bounds_basis": BASIS},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
