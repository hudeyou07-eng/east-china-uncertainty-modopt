"""R305：联合机会约束 vs 逐营养素（marginal）机会约束。

## 问题

正式口径 D3 用的是**联合**机会约束：每个场景一个 ``z_s``，
预算 ``Σ_s z_s ≤ floor(εS)``，语义是「至少 1−ε 的场景**全部营养素同时达标**」。

R302 暴露了一个问题：江苏在 ε=0.05 下无解，需要 ε≈0.30 才可行。
当时的解释是「9 个营养素各自几个百分点的违反概率复合」。若这个解释成立，
那么改成**逐营养素**约束（每个营养素各自允许 floor(εS) 个场景违反）应当能
让江苏在小 ε 下就可行。

本脚本直接检验，并量化代价——**marginal 不是免费的**：
它只保证每个营养素各自的违反率 ≤ ε，联合违反率的上界是 **J·ε** 而不是 ε。
J=9、ε=0.05 时，理论上「全部营养素同时达标」的场景可以低到 55%，
与 joint 承诺的 95% 完全不是一回事。

## 指标

对每个 (省, ε, 模式)：

* ``solve_success``：求解器是否给出解；
* ``marginal_viol_max``：逐营养素违反率的最大值（应 ≤ ε + 取整误差）；
* ``joint_viol_rate``：**任一**营养素被违反的场景比例（真正的可靠性指标）；
* ``joint_viol_over_eps``：``joint_viol_rate / ε``，>1 表示没兑现 ε 承诺；
* ``objective``：目标值（marginal 更松，理应更优，这是「用可靠性换成本」）。

## 证据等级

``plumbing_only``：场景仍是占位噪声。可采信的是**两种模式的语义差别**与
「marginal 能救回哪些省」这类结构性事实，不是绝对违反率数值。

用法：
    python scripts/run_r305_chance_mode.py --profile smoke
    python scripts/run_r305_chance_mode.py --profile smoke --epsilons 0.05 0.30
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

from src.b2_problem import Contract  # noqa: E402
from src.b2_scenarios import placeholder_scenarios  # noqa: E402
from src.io_utils import create_run_dir, finalize_run  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402

PROFILES = {"smoke": 200, "formal": 200}  # R301 证明 S=200 已在平台期
DEFAULT_EPS = (0.0, 0.02, 0.05, 0.10, 0.20, 0.30)
MODES = ("joint", "marginal")


def violation_rates(
    q: np.ndarray,
    nut: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    mask: np.ndarray,
    tol: float = 1e-9,
) -> tuple[np.ndarray, float]:
    """把解 q 代回场景，算逐营养素违反率与联合违反率。

    ``nut``: [S, J, K]，已按 active_mask 切片。
    返回 ``(per_nutrient_rate[J], joint_rate)``。
    """
    achieved = np.einsum("sjk,k->sj", nut, np.asarray(q, dtype=float))
    below = np.isfinite(lower)[None, :] & (achieved < lower[None, :] - tol)
    above = np.isfinite(upper)[None, :] & (achieved > upper[None, :] + tol)
    violated = below | above  # [S, J]
    per_nutrient = violated.mean(axis=0)
    joint = float(violated.any(axis=1).mean())
    return per_nutrient, joint


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default="smoke", choices=sorted(PROFILES))
    ap.add_argument("--scenario", default="CDG")
    ap.add_argument("--epsilons", type=float, nargs="+", default=list(DEFAULT_EPS))
    ap.add_argument("--modes", nargs="+", default=list(MODES))
    ap.add_argument("--cv-price", type=float, default=0.05)
    ap.add_argument("--cv-nutrient", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=20261026)
    ap.add_argument("--time-limit", type=float, default=60.0, help="单次求解的 MILP 时间上限（秒）")
    ap.add_argument(
        "--mip-rel-gap",
        type=float,
        default=1e-3,
        help="MILP 相对 gap。高 ε 的 marginal 实例接近退化，1e-3 常撞时限；"
        "诊断可行性时可放宽到 1e-2（此时只影响目标值精度，不影响可行性结论）",
    )
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    n_scen = PROFILES[args.profile]
    start = time.time()
    contract = Contract.load()
    usable, skipped = contract.complete_provinces()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id or "R305_chance_mode")

    print(f"省份 {len(usable)}，S={n_scen}，模式 {args.modes}，ε {args.epsilons}")
    if skipped:
        print(f"硬不可行跳过：{', '.join(skipped)}")

    rows: list[dict] = []
    for province in usable:
        inst = contract.instance(province, args.scenario)
        if not inst.hard_feasible:
            continue
        obj, nut_full = placeholder_scenarios(
            inst, n_scen, args.seed, args.cv_price, args.cv_nutrient
        )
        mask = inst.active_mask
        nut = nut_full[:, mask, :]
        lower = inst.nutrient_lower[mask]
        upper = inst.nutrient_upper[mask]
        j_count = int(mask.sum())

        for eps in args.epsilons:
            for mode in args.modes:
                t0 = time.time()
                res = solve_chance_modopt(
                    obj,
                    nut,
                    lower,
                    upper,
                    inst.q_lower,
                    inst.q_upper,
                    inst.objective_weights,
                    epsilon=eps,
                    extra_constraints=inst.extra_constraints,
                    chance_mode=mode,
                    time_limit=args.time_limit,
                    mip_rel_gap=args.mip_rel_gap,
                )
                elapsed = time.time() - t0
                if not res.success:
                    rows.append(
                        {
                            "province": province,
                            "epsilon": eps,
                            "mode": mode,
                            "solve_success": False,
                            "objective": float("nan"),
                            "marginal_viol_max": float("nan"),
                            "joint_viol_rate": float("nan"),
                            "joint_viol_over_eps": float("nan"),
                            "z_sum": float("nan"),
                            "z_budget": float(np.floor(eps * n_scen + 1e-12)),
                            "n_nutrients": j_count,
                            "seconds": elapsed,
                            "message": res.message[:60],
                            "timed_out": "time limit" in res.message.lower(),
                        }
                    )
                    continue
                per_nutrient, joint_rate = violation_rates(
                    res.q, nut, lower, upper, mask
                )
                rows.append(
                    {
                        "province": province,
                        "epsilon": eps,
                        "mode": mode,
                        "solve_success": True,
                        "objective": float(res.objective),
                        "marginal_viol_max": float(per_nutrient.max()),
                        "joint_viol_rate": joint_rate,
                        "joint_viol_over_eps": (
                            joint_rate / eps if eps > 0 else float("inf")
                        ),
                        "z_sum": float(np.nansum(res.z)),
                        "z_budget": float(np.floor(eps * n_scen + 1e-12)),
                        "n_nutrients": j_count,
                        "seconds": elapsed,
                        "message": res.message[:60],
                        "timed_out": False,
                    }
                )

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "chance_mode_results.csv", index=False, encoding="utf-8-sig")

    print()
    print("=== 求解成功率（行=省，列=模式×ε） ===")
    piv = df.pivot_table(
        index="province",
        columns=["mode", "epsilon"],
        values="solve_success",
        aggfunc="first",
    )
    print(piv.astype("Int64").to_string())

    ok = df[df.solve_success]
    print()
    print("=== 联合违反率（真正的可靠性指标；joint 应 ≤ ε） ===")
    if len(ok):
        piv2 = ok.pivot_table(
            index="province", columns=["mode", "epsilon"], values="joint_viol_rate"
        )
        print(piv2.round(3).to_string())

    print()
    print("=== 违反率 / ε（>1 表示没兑现 ε 承诺） ===")
    if len(ok):
        piv3 = ok[ok.epsilon > 0].pivot_table(
            index="province", columns=["mode", "epsilon"], values="joint_viol_over_eps"
        )
        print(piv3.round(2).to_string())

    print()
    print("=== 逐营养素违反率的最大值（marginal 应 ≤ ε+取整） ===")
    if len(ok):
        piv4 = ok.pivot_table(
            index="province", columns=["mode", "epsilon"], values="marginal_viol_max"
        )
        print(piv4.round(3).to_string())

    summary = (
        df.groupby(["mode", "epsilon"])
        .agg(
            solve_rate=("solve_success", "mean"),
            joint_viol_mean=("joint_viol_rate", "mean"),
            marginal_viol_mean=("marginal_viol_max", "mean"),
            objective_mean=("objective", "mean"),
            seconds_mean=("seconds", "mean"),
        )
        .reset_index()
    )
    summary.to_csv(run_dir / "chance_mode_summary.csv", index=False, encoding="utf-8-sig")
    print()
    print("=== 汇总 ===")
    print(summary.round(3).to_string(index=False))

    finalize_run(
        run_dir,
        {
            "command": "r305-chance-mode",
            "scenario": args.scenario,
            "profile": args.profile,
            "scenarios": n_scen,
            "epsilons": list(args.epsilons),
            "modes": list(args.modes),
            "seed": args.seed,
            "cv_price": args.cv_price,
            "cv_nutrient": args.cv_nutrient,
            "provinces_used": usable,
            "provinces_skipped": skipped,
            "wall_seconds": time.time() - start,
            "evidence_status": "plumbing_only",
            "evidence_note": (
                "场景为占位对数正态噪声。可采信的是两种模式的语义差别与"
                "「marginal 能救回哪些省」这类结构性事实；"
                "绝对违反率数值不作结论。"
            ),
            "summary": summary.to_dict("records"),
        },
        {
            "command": "r305-chance-mode",
            "scenario": args.scenario,
            "profile": args.profile,
            "scenarios": n_scen,
            "epsilons": list(args.epsilons),
            "modes": list(args.modes),
            "seed": args.seed,
            "time_limit": args.time_limit,
            "mip_rel_gap": args.mip_rel_gap,
        },
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
