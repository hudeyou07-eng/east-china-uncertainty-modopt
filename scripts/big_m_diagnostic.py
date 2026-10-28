"""R306：Big-M 诊断（tight vs global）。

机会约束的建模方式是把「违反量」乘上大 M 接到二元变量 ``z`` 上：

    Σ_j n_sj q_j  ≥  ℓ_j − M⁻_sj · z_s
    Σ_j n_sj q_j  ≤  u_j + M⁺_sj · z_s
    Σ_s z_s ≤ floor(ε·S)

``M`` 取多大是建模自由度。取太大，LP 松弛变松，分支定界变慢甚至数值不稳；
取太小，可行域被错误裁剪（``z=1`` 时也放不出足够的违反量）。

`src/robust_modopt.py` 默认用 **tight**：逐 (场景, 营养素) 由 box 极值推出
最小可用 M。本脚本用 **global**（全表统一取最大）作对照，验证这个选择不是白写的。

判定标准（预注册）：

- 两种 M 的最优 ``q`` 必须一致（差异 < 1 g/day）——不一致说明 tight 裁掉了可行解；
- tight 的求解时间不应慢于 global（若更慢，说明 tight 反而破坏了大 M 的稀疏性）。

**只在 toy 问题上做**（R306 的范围就是 toy）：真实实例含 200 场景 × 9 营养素 = 3600 行，
跑 global 对照只是为了看规模效应，不构成论文证据。

用法：
    python scripts/big_m_diagnostic.py
    python scripts/big_m_diagnostic.py --scenarios 20 50 100
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

from src.io_utils import create_run_dir, finalize_run  # noqa: E402
from src.robust_modopt import _box_extrema, make_toy_problem, solve_chance_modopt  # noqa: E402

SEEDS = (1, 2, 3, 4, 5)
MODES = ("tight", "global")


def m_spread(problem: dict) -> dict:
    """统计该问题里 tight M 的分布。

    **这一步不能省。** 若各 (场景, 营养素) 的 M 几乎相同，那么 tight 与 global
    本来就是同一个模型，两者结果一致是定义决定的，不能当作「tight 有效」的证据。
    必须先确认 M 有足够跨度，结论才有意义。
    """
    ql, qu = problem["q_lower"], problem["q_upper"]
    n_scen, j_count, _ = problem["nutrient_coeff"].shape
    values: list[float] = []
    for s in range(n_scen):
        for j in range(j_count):
            mn, mx = _box_extrema(problem["nutrient_coeff"][s, j], ql, qu)
            values.append(max(0.0, float(problem["nutrient_lower"][j] - mn)))
            values.append(max(0.0, float(mx - problem["nutrient_upper"][j])))
    arr = np.asarray(values)
    nonzero = arr[arr > 0]
    if nonzero.size == 0:
        return {"n": int(arr.size), "n_nonzero": 0, "ratio": float("nan")}
    return {
        "n": int(arr.size),
        "n_nonzero": int(nonzero.size),
        "m_min": float(nonzero.min()),
        "m_max": float(nonzero.max()),
        "ratio_max_over_min": float(nonzero.max() / nonzero.min()),
        "global_over_mean": float(nonzero.max() / nonzero.mean()),
    }


def run_case(problem: dict, mode: str, epsilon: float, time_limit: float):
    t0 = time.time()
    res = solve_chance_modopt(
        objective_coeff=problem["objective_coeff"],
        nutrient_coeff=problem["nutrient_coeff"],
        nutrient_lower=problem["nutrient_lower"],
        nutrient_upper=problem["nutrient_upper"],
        q_lower=problem["q_lower"],
        q_upper=problem["q_upper"],
        objective_weights=problem["objective_weights"],
        epsilon=epsilon,
        time_limit=time_limit,
        big_m=mode,
    )
    return res, time.time() - t0


def main() -> int:
    parser = argparse.ArgumentParser(description="R306 Big-M diagnostic (tight vs global)")
    parser.add_argument("--scenarios", nargs="+", type=int, default=[20, 50, 100])
    parser.add_argument("--epsilon", type=float, default=0.05)
    parser.add_argument("--time-limit", type=float, default=120.0)
    parser.add_argument("--run-id", default="R306_big_m")
    args = parser.parse_args()

    run_dir = create_run_dir(ROOT / "outputs", args.run_id)
    rows: list[dict] = []
    spreads: list[dict] = []

    for n_scen in args.scenarios:
        for seed in SEEDS:
            problem = make_toy_problem(seed, scenarios=n_scen)
            spreads.append({"n_scenarios": n_scen, "seed": seed, **m_spread(problem)})
            solutions: dict[str, np.ndarray] = {}
            for mode in MODES:
                res, elapsed = run_case(problem, mode, args.epsilon, args.time_limit)
                ok = bool(res.success) and np.isfinite(res.q).all()
                if ok:
                    solutions[mode] = res.q
                rows.append(
                    {
                        "n_scenarios": n_scen,
                        "seed": seed,
                        "big_m": mode,
                        "success": ok,
                        "objective": float(res.objective) if ok else float("nan"),
                        "runtime": elapsed,
                        "mip_gap": res.mip_gap if res.mip_gap is not None else float("nan"),
                        "q": "|".join(f"{v:.4f}" for v in res.q) if ok else "",
                    }
                )

            if len(solutions) == len(MODES):
                delta = float(np.abs(solutions["tight"] - solutions["global"]).max())
                rows.append(
                    {
                        "n_scenarios": n_scen,
                        "seed": seed,
                        "big_m": "delta",
                        "success": True,
                        "objective": float("nan"),
                        "runtime": float("nan"),
                        "mip_gap": float("nan"),
                        "q": f"{delta:.6f}",
                    }
                )

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "big_m_results.csv", index=False, encoding="utf-8-sig")
    spread_df = pd.DataFrame(spreads)
    spread_df.to_csv(run_dir / "big_m_spread.csv", index=False, encoding="utf-8-sig")

    solve_df = df[df["big_m"].isin(MODES)]
    summary = (
        solve_df.groupby(["n_scenarios", "big_m"], as_index=False)
        .agg(
            n=("seed", "size"),
            solve_rate=("success", "mean"),
            runtime_mean=("runtime", "mean"),
            runtime_max=("runtime", "max"),
            objective_mean=("objective", "mean"),
        )
        .sort_values(["n_scenarios", "big_m"])
    )
    summary.to_csv(run_dir / "big_m_summary.csv", index=False, encoding="utf-8-sig")

    delta_df = df[df["big_m"].eq("delta")].copy()
    delta_df["delta_q_max"] = delta_df["q"].astype(float)
    delta_summary = (
        delta_df.groupby("n_scenarios", as_index=False)
        .agg(
            n_pairs=("seed", "size"),
            delta_mean=("delta_q_max", "mean"),
            delta_max=("delta_q_max", "max"),
        )
        .sort_values("n_scenarios")
    )
    delta_summary.to_csv(
        run_dir / "big_m_agreement.csv", index=False, encoding="utf-8-sig"
    )

    # 判定
    worst_delta = float(delta_summary["delta_max"].max()) if not delta_summary.empty else float("nan")
    agree = bool(np.isfinite(worst_delta) and worst_delta < 1.0)
    tight_speed = summary.pivot_table(index="n_scenarios", columns="big_m", values="runtime_mean")
    tight_faster = bool(
        ("tight" in tight_speed.columns)
        and ("global" in tight_speed.columns)
        and bool((tight_speed["tight"] <= tight_speed["global"] * 1.05).all())
    )

    metrics = {
        "command": "big-m-diagnostic",
        "purpose": "R306：验证 tight Big-M 不裁剪可行解、且不劣于 global",
        "epsilon": args.epsilon,
        "seeds": list(SEEDS),
        "scenario_grid": args.scenarios,
        "max_delta_q_between_modes": worst_delta,
        "solutions_agree": agree,
        "tight_not_slower": tight_faster,
        "m_spread": spread_df.groupby("n_scenarios")[
            ["ratio_max_over_min", "global_over_mean"]
        ].mean().round(3).to_dict("index"),
        "summary": summary.to_dict("records"),
        "agreement": delta_summary.to_dict("records"),
    }
    finalize_run(
        run_dir,
        metrics,
        {
            "command": "big-m-diagnostic",
            "epsilon": args.epsilon,
            "seeds": list(SEEDS),
            "scenario_grid": args.scenarios,
        },
    )

    print("[R306] Big-M 诊断（toy 问题，5 个种子）")
    print()
    print(summary.assign(runtime_mean=lambda d: d.runtime_mean.round(3)).to_string(index=False))
    print()
    print("两种 M 的解一致性：")
    print(delta_summary.round(4).to_string(index=False))
    print()
    print("tight M 的跨度（决定这个对照是否有意义）：")
    print(
        spread_df.groupby("n_scenarios")[["ratio_max_over_min", "global_over_mean"]]
        .mean()
        .round(2)
        .to_string()
    )
    print()
    print(f"最大 Δq = {worst_delta:.4f} g → 解一致：{agree}")
    print(f"tight 不慢于 global（5% 容差）：{tight_faster}")
    print()
    print(f"[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
