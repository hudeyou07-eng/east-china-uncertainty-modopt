"""R304：目标权重 W 的不确定性是否改变决策。

## 问题

模型把成本/营养/环境三个目标压成一个加权和，权重取 ``w0 = (0.5, 0.25, 0.25)``。
这个权重是**研究者的判断**，不是数据估出来的。那么：

> 如果真实权重与假设的权重不一致，决策会错多少？

R303 只比较了 ``original`` 与 ``equal`` 两个**离散**权重集，
回答的是「换一套权重会不会改变结论」。本节点回答的是**连续分布**下的问题：
权重在 ``w0`` 附近按 Dirichlet 抖动时，决策的翻转率与遗憾有多大。

## 设定

* 权重抽样：``w_hat ~ Dirichlet(κ · w0)``，均值恰为 ``w0``，``κ`` 控制集中度
  （κ 大 → 贴近 ``w0``；κ 小 → 散开）。取 κ ∈ {100, 20, 5} 对应 tight/medium/loose。
* **场景固定为点估计（S=1）**：本节点只问权重的效应，不能与场景不确定性混淆。
  因此每次求解是一个 LP，可以抽几百次。
* 决策者按 ``w_hat`` 求解决策 ``q(w_hat)``；真实权重是 ``w0``。
* **遗憾** ``regret = [f(q(w_hat); w0) − f(q(w0); w0)] / |f(q(w0); w0)|``，
  其中 ``f`` 与求解器同口径（``normalized_cost_vector``）。遗憾恒 ≥ 0（当且仅当
  ``w_hat`` 选到同一个顶点时为 0）。

## 指标

* ``regret_mean`` / ``regret_p95`` / ``regret_max``；
* ``flip_any_rate``：至少有一个组的相对基线方向发生翻转的抽样比例；
* ``max_abs_delta``：``max |q(w_hat) − q(w0)|``。

## 证据等级

``plumbing_only``：场景为点估计。可采信的是**权重误设的敏感度量级**，
以及「哪些省对权重更敏感」这类结构性对比。

用法：
    python scripts/run_r304_weight_uncertainty.py --draws 200
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

from src.b2_evaluate import direction  # noqa: E402
from src.b2_problem import Contract  # noqa: E402
from src.b2_scenarios import deterministic  # noqa: E402
from src.io_utils import create_run_dir, finalize_run  # noqa: E402
from src.robust_modopt import solve_chance_modopt, weighted_objective_value  # noqa: E402

KAPPAS = {"tight": 100.0, "medium": 20.0, "loose": 5.0}
FLIP_TOL = 1.0  # g/day，判定「这个组的决策变了」的实用阈值


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="CDG")
    ap.add_argument("--epsilon", type=float, default=0.05)
    ap.add_argument("--draws", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20261026)
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    start = time.time()
    contract = Contract.load()
    usable, skipped = contract.complete_provinces()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id or "R304_weight_uncertainty")
    rng = np.random.default_rng(args.seed)

    rows: list[dict] = []
    draw_rows: list[dict] = []

    for province in usable:
        inst = contract.instance(province, args.scenario)
        if not inst.hard_feasible:
            continue
        obj, nut = deterministic(inst)
        mask = inst.active_mask
        w0 = np.asarray(inst.objective_weights, dtype=float)

        def solve_with(weights: np.ndarray):
            return solve_chance_modopt(
                obj,
                nut[:, mask, :],
                inst.nutrient_lower[mask],
                inst.nutrient_upper[mask],
                inst.q_lower,
                inst.q_upper,
                weights,
                epsilon=args.epsilon,
                extra_constraints=inst.extra_constraints,
            )

        base = solve_with(w0)
        if not base.success:
            print(f"{province}: 基线失败 —— {base.message}")
            continue
        q0 = np.asarray(base.q, dtype=float)
        f0 = weighted_objective_value(obj, q0, w0, inst.q_lower, inst.q_upper)
        dir0 = direction(q0, inst.baseline)

        for label, kappa in KAPPAS.items():
            regrets: list[float] = []
            flips: list[int] = []
            deltas: list[float] = []
            for _ in range(args.draws):
                w_hat = rng.dirichlet(kappa * w0)
                res = solve_with(w_hat)
                if not res.success:
                    continue
                q = np.asarray(res.q, dtype=float)
                f_true = weighted_objective_value(
                    obj, q, w0, inst.q_lower, inst.q_upper
                )
                regret = (f_true - f0) / abs(f0)
                d = direction(q, inst.baseline)
                n_flip = int((d != dir0).sum())
                max_delta = float(np.abs(q - q0).max())
                regrets.append(regret)
                flips.append(n_flip)
                deltas.append(max_delta)
                draw_rows.append(
                    {
                        "province": province,
                        "concentration": label,
                        "kappa": kappa,
                        "w_cost": float(w_hat[0]),
                        "w_nutrition": float(w_hat[1]),
                        "w_environment": float(w_hat[2]),
                        **{f"q_{g}": float(v) for g, v in zip(inst.groups, q)},
                        "regret": regret,
                        "n_flips": n_flip,
                        "max_abs_delta": max_delta,
                    }
                )
            if not regrets:
                continue
            arr = np.asarray(regrets)
            rows.append(
                {
                    "province": province,
                    "concentration": label,
                    "kappa": kappa,
                    "n_draws": len(regrets),
                    "regret_mean": float(arr.mean()),
                    "regret_p95": float(np.percentile(arr, 95)),
                    "regret_max": float(arr.max()),
                    "regret_zero_share": float((arr < 1e-9).mean()),
                    "flip_any_rate": float(np.mean(np.asarray(flips) > 0)),
                    "flips_mean": float(np.mean(flips)),
                    "max_abs_delta_p95": float(np.percentile(deltas, 95)),
                    "max_abs_delta_max": float(np.max(deltas)),
                    "baseline_objective": f0,
                }
            )

    df = pd.DataFrame(rows)
    draws = pd.DataFrame(draw_rows)
    df.to_csv(run_dir / "weight_uncertainty_summary.csv", index=False, encoding="utf-8-sig")
    draws.to_csv(run_dir / "weight_uncertainty_draws.csv", index=False, encoding="utf-8-sig")

    if df.empty:
        print("没有任何省跑出结果")
        return 1

    print("=== 权重误设的遗憾（相对值，p95） ===")
    print(
        df.pivot_table(index="province", columns="concentration", values="regret_p95")
        .round(4)
        .to_string()
    )
    print()
    print("=== 至少一个组翻转的抽样比例 ===")
    print(
        df.pivot_table(index="province", columns="concentration", values="flip_any_rate")
        .round(3)
        .to_string()
    )
    print()
    print("=== max |Δq| 的 p95（g/day） ===")
    print(
        df.pivot_table(index="province", columns="concentration", values="max_abs_delta_p95")
        .round(2)
        .to_string()
    )
    print()
    print("=== 按集中度汇总（六省平均） ===")
    print(
        df.groupby("concentration")
        .agg(
            regret_mean=("regret_mean", "mean"),
            regret_p95=("regret_p95", "mean"),
            flip_any_rate=("flip_any_rate", "mean"),
            max_abs_delta_p95=("max_abs_delta_p95", "mean"),
        )
        .round(4)
        .to_string()
    )

    finalize_run(
        run_dir,
        {
            "command": "r304-weight-uncertainty",
            "scenario": args.scenario,
            "epsilon": args.epsilon,
            "draws": args.draws,
            "seed": args.seed,
            "kappas": KAPPAS,
            "flip_tol_g": FLIP_TOL,
            "provinces_used": usable,
            "provinces_skipped": skipped,
            "wall_seconds": time.time() - start,
            "evidence_status": "plumbing_only",
            "evidence_note": (
                "场景固定为点估计（S=1），只测权重误设的影响。"
                "遗憾按 normalized_cost_vector 口径在真实权重 w0 下评估。"
            ),
            "summary": df.to_dict("records"),
        },
        {
            "command": "r304-weight-uncertainty",
            "scenario": args.scenario,
            "epsilon": args.epsilon,
            "draws": args.draws,
            "seed": args.seed,
            "kappas": KAPPAS,
        },
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
