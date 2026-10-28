"""CVaR 到底把目标方向旋转了多少度？

## 问题

`DIAG_vertex_stability` 否证了「分量最小点」假说：CDG 在随机价格方向下
有 5–7 个不同最优顶点，位移 43–131 g。也就是说**决策对目标方向是敏感的**。

但同一批省在 CVaR 下（``λ=1``，``cv`` 扫到 0.5）位移精确为 0。
两者只能靠一件事调和：**CVaR 对目标方向的旋转量太小**。

## 机制

场景扰动是**逐组独立**的。因此单个场景的总成本主要由冲击的**共同分量**
（整体价格水平）决定，逐组的特异性分量在求和时相互抵消。
于是「最差 10% 场景」恰恰是「整体价格水平最高的场景」，
其成本向量的**方向**与均值方向几乎一致——CVaR 重加权只是把一个方向
微微放大，几乎没有旋转。

对照：随机价格方向（逐组独立、不按总成本排序）能旋转几十度，所以能移动顶点。

## 度量

* ``mean_dir``  = ``c̄ / ||c̄||``，即 λ=0 的目标方向；
* ``cvar_dir``  = 尾部集合（``cost_s ≥ VaR_α``）上 ``c_s`` 的均值方向；
* ``angle_deg`` = 两者夹角；
* ``max_abs_dq`` = 同一批场景下 λ=1 相对 λ=0 的位移。

判读：若 ``angle_deg`` 随 ``cv`` 增大仍停在个位数，则 CDG 的零位移
是「尾部方向 ≈ 均值方向」的直接后果，而非约束集或求解器问题。

用法：
    python scripts/diagnose_cvar_angle.py
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
from src.io_utils import create_run_dir, finalize_run  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402

SCOPE = "k6_price"
BASIS = "ear"
SCENARIOS = ("CDG", "EAT")
CVS = (0.05, 0.20, 0.50)
ALPHA = 0.90
N_SCEN = 200
SEED = 20261027


def _lognormal(rng, point, cv, size):
    sigma = np.sqrt(np.log1p(cv * cv))
    return point[None, ...] * rng.lognormal(-0.5 * sigma * sigma, sigma,
                                            size=(size,) + point.shape)


def _spike(rng, point, cv, size, prob=0.15):
    """组特异性价格冲击：每个场景以 ``prob`` 概率有 1~2 个组暴涨 1.5~3.0 倍。

    用来模拟真实食品价格的形态——猪肉、鲜菜的价格冲击是**单品类**的，
    不是所有品类一起涨 ``cv`` 那么多。这才是 B1 后验会给出的结构。
    """
    mult = np.exp(rng.normal(0.0, cv, size=(size,) + point.shape))
    hit = rng.random(size=(size,) + point.shape) < prob
    mult = np.where(hit, mult * rng.uniform(1.5, 3.0, size=(size,) + point.shape), mult)
    return point[None, ...] * mult


MODES = {"iid": _lognormal, "spike": _spike}


def _solve(inst, obj, nut, lam):
    mask = inst.active_mask
    return solve_chance_modopt(
        obj, nut[:, mask, :],
        inst.nutrient_lower[mask], inst.nutrient_upper[mask],
        inst.q_lower, inst.q_upper, inst.objective_weights,
        epsilon=0.05, extra_constraints=inst.extra_constraints,
        risk_weight=lam, cvar_alpha=ALPHA,
    )


def _angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    ca = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
    return float(np.degrees(np.arccos(np.clip(ca, -1.0, 1.0))))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_cvar_angle")
    args = ap.parse_args()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    contract = Contract.load_scope(SCOPE)
    usable, _ = contract.complete_provinces()
    rows: list[dict] = []

    for scenario in SCENARIOS:
        for province in usable:
            inst = contract.instance(province, scenario, bounds_basis=BASIS)
            for mode, gen in MODES.items():
                for cv in CVS:
                    rng = np.random.default_rng(SEED)
                    obj = gen(rng, inst.objective_coeff[0], cv, N_SCEN)
                    nut = np.repeat(inst.nutrient_coeff[0][None, ...], N_SCEN, axis=0)

                    r0 = _solve(inst, obj, nut, 0.0)
                    if not r0.success:
                        continue
                    q0 = np.asarray(r0.q, float)
                    r1 = _solve(inst, obj, nut, 1.0)
                    if not r1.success:
                        continue
                    q1 = np.asarray(r1.q, float)

                    cmat = np.asarray(obj, float)[:, 0, :]  # [S, K]
                    costs = cmat @ q1
                    n_tail = max(1, int(round((1.0 - ALPHA) * len(costs))))
                    tail = np.argsort(costs)[-n_tail:]
                    mean_dir = cmat.mean(axis=0)
                    cvar_dir = cmat[tail].mean(axis=0)

                    rows.append({
                        "scenario": scenario, "province": province,
                        "mode": mode, "cv": cv,
                        "angle_deg": _angle_deg(mean_dir, cvar_dir),
                        "max_abs_dq": float(np.abs(q1 - q0).max()),
                        "tail_cost_ratio": float(
                            costs[tail].mean() / costs.mean()
                        ),
                    })

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "cvar_angle.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 220)
    print("=== 目标方向旋转角（度）与位移 ===")
    print(df.pivot_table(index=["scenario", "province"], columns=["mode", "cv"],
                         values="angle_deg").round(2).to_string())
    print("\n位移 max|Δq|（g/day）")
    print(df.pivot_table(index=["scenario", "province"], columns=["mode", "cv"],
                         values="max_abs_dq", aggfunc="max").round(2).to_string())
    print("\n尾部/均值 成本比")
    print(df.pivot_table(index=["scenario", "province"], columns=["mode", "cv"],
                         values="tail_cost_ratio").round(3).to_string())

    summary = {
        "angle_max_cdg_iid": float(
            df[df["scenario"].eq("CDG") & df["mode"].eq("iid")]["angle_deg"].max()
        ),
        "angle_max_cdg_spike": float(
            df[df["scenario"].eq("CDG") & df["mode"].eq("spike")]["angle_deg"].max()
        ),
        "dq_max_cdg_iid": float(
            df[df["scenario"].eq("CDG") & df["mode"].eq("iid")]["max_abs_dq"].max()
        ),
        "dq_max_cdg_spike": float(
            df[df["scenario"].eq("CDG") & df["mode"].eq("spike")]["max_abs_dq"].max()
        ),
        "angle_max_all": float(df["angle_deg"].max()),
        "dq_max_all": float(df["max_abs_dq"].max()),
        "corr_angle_vs_dq_iid": float(
            df[df["mode"].eq("iid")][["angle_deg", "max_abs_dq"]].corr().iloc[0, 1]
        ),
        "corr_angle_vs_dq_spike": float(
            df[df["mode"].eq("spike")][["angle_deg", "max_abs_dq"]].corr().iloc[0, 1]
        ),
    }
    print("\n=== 汇总 ===")
    for k, v in summary.items():
        print(f"  {k}: {v:.4f}")

    finalize_run(
        run_dir,
        {
            "command": "diagnose-cvar-angle",
            "evidence_status": "plumbing_only",
            "scope": SCOPE,
            "bounds_basis": BASIS,
            "scenarios": list(SCENARIOS),
            "cvs": list(CVS),
            "alpha": ALPHA,
            "n_scenarios": N_SCEN,
            "evidence_note": (
                "占位对数正态场景；本脚本度量的是『CVaR 对目标方向的旋转量』"
                "这一几何量，与场景分布是否为真实后验关系较弱"
            ),
            "summary": summary,
        },
        {"command": "diagnose-cvar-angle", "scope": SCOPE},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
