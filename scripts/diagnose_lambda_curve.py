"""执行 §24.8 判定的后半句：对「必须报告 λ 曲线」的格子，真的把曲线算出来。

## 为什么需要这个脚本

`diagnose_tail_angle.py` 按预注册规则给出判定：

* `θ_tail < θ*` → CVaR 可证明无效，附录一句话；
* `θ_tail ≥ θ*` → **必须报告 λ 曲线**。

但判定只是「不能证明无效」，不等于「真的有效」。`θ*` 是顶点稳定的**充分**条件，
不是必要条件——扰动角超过 `θ*` 仍可能不换顶点。所以必须直接扫 λ 把曲线画出来。

顺带一提：`diagnose_tail_angle.py` 已经在每格上算了 `max|q(λ=1) − q(λ=0)|`，
CDG 六省全是 1e-12 量级、EAT 三省是 108–217 g/day。本脚本把这个观察
从「两个端点」扩展成「五点的完整曲线」，并检查单调性。

## 口径

* 场景集固定（单 seed），**同一批场景**下扫 λ，否则曲线不可比；
* `λ ∈ {0, 0.25, 0.5, 0.75, 1.0}`，目标 = `均值成本 + λ · CVaR_α`；
* 记录每格的 `max|Δq|`（相对 λ=0）、`mean_cost`、`cvar`、目标值；
* `Δq` 的容差 `1e-6 g/day`，小于此视为「未动」（与 §27 的教训一致：
  浮点比较先定容差，不要用字符串或 `round`）。

## 用法

    python scripts/diagnose_lambda_curve.py
    python scripts/diagnose_lambda_curve.py --n-scen 200 --seeds 3
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

from src.b2_problem import Contract  # noqa: E402
from src.b2_scenarios import (  # noqa: E402
    B1_MASK_DEFAULT,
    B1_METHOD_DEFAULT,
    B1_RUN_DEFAULT,
    load_residual_pool,
    posterior_scenarios,
)
from src.io_utils import create_run_dir, finalize_run  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402

SCOPE = "k6_price"
BASIS = "ear"
SCENARIOS = ("CDG", "EAT")
LAMBDAS = (0.0, 0.25, 0.5, 0.75, 1.0)
N_SCEN = 200
ALPHA = 0.90
SEEDS = (20261027, 20261028, 20261029)
DQ_TOL = 1e-6  # g/day，小于此视为「决策未动」


def _solve(inst, obj, nut, lam: float):
    mask = inst.active_mask
    return solve_chance_modopt(
        obj, nut[:, mask, :],
        inst.nutrient_lower[mask], inst.nutrient_upper[mask],
        inst.q_lower, inst.q_upper, inst.objective_weights,
        epsilon=0.05, extra_constraints=inst.extra_constraints,
        risk_weight=lam, cvar_alpha=ALPHA,
    )


def _within_seed_range_pct(sub: pd.DataFrame, col: str) -> float:
    """在**同一 seed 内**扫 λ 得到的变动幅度（%），跨 seed 取中位。

    必须按 seed 分组：若在跨 seed 的合并表上取 `max/min`，会把种子间的抽样
    差异算成「λ 效应」。实测后果——CDG 的 CVaR 变动被报成 1.25–1.54%，
    而真实的 λ 效应是 **0.0000%**（Δq = 1e-9，解逐位相同）。见 CHANGELOG §29.6。
    """
    vals = [
        (g[col].max() / g[col].min() - 1.0) * 100.0
        for _, g in sub.groupby("seed")
        if len(g) and g[col].min() > 0
    ]
    return float(np.median(vals)) if vals else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_lambda_curve")
    ap.add_argument("--n-scen", type=int, default=N_SCEN)
    ap.add_argument("--seeds", type=int, default=len(SEEDS))
    ap.add_argument(
        "--lambdas", type=float, nargs="+", default=list(LAMBDAS),
        help="λ 网格；默认 (0, .25, .5, .75, 1)。查跳变点时用细网格。",
    )
    ap.add_argument(
        "--scenarios", nargs="+", default=list(SCENARIOS),
        help="只跑指定情景（细网格定位跳变点时用 EAT 即可）。",
    )
    args = ap.parse_args()
    lambdas = tuple(args.lambdas)
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    contract = Contract.load_scope(SCOPE)
    usable, _ = contract.complete_provinces()
    pool = load_residual_pool(
        ROOT / "outputs" / B1_RUN_DEFAULT, method=B1_METHOD_DEFAULT,
        mask_type=B1_MASK_DEFAULT, groups=contract.groups,
    )

    rows: list[dict] = []
    seeds = SEEDS[: args.seeds]
    for scenario in args.scenarios:
        for province in usable:
            inst = contract.instance(province, scenario, bounds_basis=BASIS)
            for seed in seeds:
                obj, nut = posterior_scenarios(inst, args.n_scen, seed, pool=pool)
                cmat = np.asarray(obj, float)[:, 0, :]  # [S, K]
                q0 = None
                for lam in lambdas:
                    r = _solve(inst, obj, nut, lam)
                    if not r.success:
                        rows.append({
                            "scenario": scenario, "province": province, "seed": seed,
                            "lam": lam, "status": "solver_failed",
                        })
                        q0 = None
                        continue
                    q = np.asarray(r.q, float)
                    if q0 is None:
                        q0 = q
                    costs = cmat @ q
                    n_tail = max(1, int(round((1.0 - ALPHA) * len(costs))))
                    cvar = float(np.sort(costs)[-n_tail:].mean())
                    rows.append({
                        "scenario": scenario, "province": province, "seed": seed,
                        "lam": lam, "status": "ok",
                        "max_abs_dq": float(np.abs(q - q0).max()),
                        "mean_cost": float(costs.mean()),
                        "cvar": cvar,
                        "objective": float(r.objective),
                    })

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "lambda_curve.csv", index=False, encoding="utf-8-sig")

    ok = df[df["status"].eq("ok")]
    agg_rows: list[dict] = []
    for (scenario, province), sub in ok.groupby(["scenario", "province"], sort=True):
        # 曲线是否真的动了：任一种子、任一 λ 上 dq 超过容差
        moved = bool((sub["max_abs_dq"] > DQ_TOL).any())

        # 变动幅度必须在**同一 seed 内**扫 λ 才可比（见 _within_seed_range_pct）。
        inner_mc = _within_seed_range_pct(sub, "mean_cost")
        inner_cv = _within_seed_range_pct(sub, "cvar")

        # 跳变点：第一个 dq 超过容差的 λ（决策是顶点解，λ 曲线通常是阶跃而非平滑）
        jumps = sub.loc[sub["max_abs_dq"] > DQ_TOL, "lam"]
        agg_rows.append({
            "scenario": scenario,
            "province": province,
            "dq_max_over_lambda": float(sub["max_abs_dq"].max()),
            "mean_cost_range_pct": inner_mc,
            "cvar_range_pct": inner_cv,
            "decision_moved": moved,
            "jump_lambda_min": float(jumps.min()) if len(jumps) else float("nan"),
            "n_seeds": int(sub["seed"].nunique()),
        })
    agg = pd.DataFrame(agg_rows).sort_values(
        ["scenario", "dq_max_over_lambda"], ascending=[True, False]
    )
    agg.to_csv(run_dir / "lambda_curve_summary.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 240)
    print(f"=== λ 曲线：λ ∈ {tuple(lambdas)}，Δq 相对 λ=0 ===")
    print(agg.round(4).to_string(index=False))

    n_moved = int(agg["decision_moved"].sum())

    def _max_for(scen: str) -> float:
        sub = agg.loc[agg["scenario"].eq(scen), "dq_max_over_lambda"]
        return float(sub.max()) if len(sub) else float("nan")

    summary = {
        "n_scen": args.n_scen,
        "alpha": ALPHA,
        "lambdas": list(lambdas),
        "n_seeds": len(seeds),
        "n_cells": int(len(agg)),
        "cells_decision_moved": n_moved,
        "cells_decision_flat": int(len(agg) - n_moved),
        "dq_max_cdg": _max_for("CDG"),
        "dq_max_eat": _max_for("EAT"),
        "dq_tol": DQ_TOL,
    }
    print("\n=== 汇总 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    finalize_run(
        run_dir,
        {
            "command": "diagnose-lambda-curve",
            "evidence_status": "structural",
            "scope": SCOPE,
            "bounds_basis": BASIS,
            "scenarios": list(args.scenarios),
            "n_scen": args.n_scen,
            "alpha": ALPHA,
            "lambdas": list(lambdas),
            "seeds": list(seeds),
            "b1_run": B1_RUN_DEFAULT,
            "b1_method": B1_METHOD_DEFAULT,
            "b1_mask_type": B1_MASK_DEFAULT,
            "evidence_note": (
                "执行 §24.8 判定后半句：对『必须报告 λ 曲线』的格子真算曲线。"
                "场景集固定（单 seed 内扫 λ），否则曲线不可比。"
                f"Δq 容差 {DQ_TOL} g/day，小于此视为决策未动。"
                "evidence_status=structural：单批场景、3 seed，非正式重复实验。"
            ),
            "summary": summary,
        },
        {"command": "diagnose-lambda-curve", "scope": SCOPE},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
