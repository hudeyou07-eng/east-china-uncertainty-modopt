"""CVaR 为什么动不了决策：是「CVaR 不行」还是「扰动太小」？

## 背景

`DIAG_cvar_channel` 实测：EAR 口径、CDG 情景、``cv_price=0.05`` 下，
``λ`` 从 0 扫到 1，``max|Δq|`` **精确为 0.0000**。

这个「精确为 0」有两种截然不同的解释，对应完全相反的研究决策：

* **H1（结构说）**：这个可行域上「期望最优」与「尾部最优」本来就是同一个点，
  风险厌恶无对象可权衡 → 论文不需要做鲁棒/随机决策，只需做评估。
* **H2（度量说）**：``cv=0.05`` 的独立对数正态扰动太弱，所有场景的成本向量
  几乎共线，任何场景重加权都只是把目标方向微微倾斜，而 LP 的最优顶点
  对这种小倾斜不敏感 → 结论是**扰动设计**的产物，换成真实后验（组间相关、
  厚尾、有真实的猪肉/蔬菜价格冲击）就可能翻盘。

区分两者很关键：H1 可以写成结论，H2 只能写成「待 B1 后验复核」。

## 设计

固定 ``λ=1``（纯 CVaR），扫 ``cv_price ∈ {0.05, 0.10, 0.20, 0.35, 0.50}``：

* ``direction_dispersion``：场景成本向量相对点估计的**方向**偏离
  ``max_s ||c_s/||c_s|| − c̄/||c̄||||``。H2 预测它与位移强相关。
* ``max_abs_dq``：相对同 cv 下 λ=0 的最大组级位移。
* ``d_CVaR_pct``：CVaR 相对 λ=0 的变化。若位移仍为 0 但 CVaR 下降，
  说明存在「免费的风险改善」（同一顶点在尾部更好），是 H1 的强证据。

另加一个**结构性对照**：``common`` 模式（所有组同比例涨跌，即单因子冲击）。
此时成本方向完全不变，H1/H2 都预测零位移——用来验证「零位移」不来自代码 bug。

## 证据等级

``plumbing_only``：场景是占位对数正态，不是 B1 后验。本脚本的用途是
**区分机制**，不是给出正式数值。

用法：
    python scripts/diagnose_cvar_dispersion.py
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
CVS = (0.05, 0.10, 0.20, 0.35, 0.50)
LAMBDA = 1.0
ALPHA = 0.90
N_SCEN = 200
SEED = 20261027


def _empirical_cvar(costs: np.ndarray, alpha: float) -> float:
    n_tail = max(1, int(round((1.0 - alpha) * len(costs))))
    return float(np.sort(costs)[-n_tail:].mean())


def _lognormal(rng, point, cv, size):
    if cv <= 0:
        return np.repeat(point[None, ...], size, axis=0)
    sigma = np.sqrt(np.log1p(cv * cv))
    mu = -0.5 * sigma * sigma
    return point[None, ...] * rng.lognormal(mu, sigma, size=(size,) + point.shape)


def _scenarios(inst, cv: float, mode: str):
    """``idiosyncratic`` = 各组独立冲击（与 placeholder_scenarios 一致）；
    ``common`` = 单因子，所有组同比例冲击（方向不变，作为零位移对照）。"""
    rng = np.random.default_rng(SEED)
    point = inst.objective_coeff[0]  # [L, K]
    if mode == "idiosyncratic":
        obj = _lognormal(rng, point, cv, N_SCEN)
    elif mode == "common":
        sigma = np.sqrt(np.log1p(cv * cv))
        mu = -0.5 * sigma * sigma
        factor = rng.lognormal(mu, sigma, size=(N_SCEN, 1, 1))  # 单一因子
        obj = point[None, ...] * factor
    else:
        raise ValueError(mode)
    nut = np.repeat(inst.nutrient_coeff[0][None, ...], N_SCEN, axis=0)
    return obj, nut


def _solve(inst, obj, nut, lam: float):
    mask = inst.active_mask
    return solve_chance_modopt(
        obj, nut[:, mask, :],
        inst.nutrient_lower[mask], inst.nutrient_upper[mask],
        inst.q_lower, inst.q_upper, inst.objective_weights,
        epsilon=0.05, extra_constraints=inst.extra_constraints,
        risk_weight=lam, cvar_alpha=ALPHA,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_cvar_dispersion")
    args = ap.parse_args()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    contract = Contract.load_scope(SCOPE)
    usable, _ = contract.complete_provinces()
    rows: list[dict] = []

    for scenario in SCENARIOS:
        for province in usable:
            inst = contract.instance(province, scenario, bounds_basis=BASIS)
            for mode in ("idiosyncratic", "common"):
                for cv in CVS:
                    obj, nut = _scenarios(inst, cv, mode)
                    r0 = _solve(inst, obj, nut, 0.0)
                    if not r0.success:
                        continue
                    q0 = np.asarray(r0.q, float)
                    cost0 = np.asarray(obj, float)[:, 0, :] @ q0

                    r1 = _solve(inst, obj, nut, LAMBDA)
                    if not r1.success:
                        rows.append({
                            "scenario": scenario, "province": province, "mode": mode,
                            "cv": cv, "success": False,
                        })
                        continue
                    q1 = np.asarray(r1.q, float)
                    cost1 = np.asarray(obj, float)[:, 0, :] @ q1

                    # 场景成本向量的方向离散度
                    cmat = np.asarray(obj, float)[:, 0, :]
                    norms = np.linalg.norm(cmat, axis=1, keepdims=True)
                    unit = cmat / norms
                    cbar = cmat.mean(axis=0)
                    ubar = cbar / np.linalg.norm(cbar)
                    disp = float(np.linalg.norm(unit - ubar[None, :], axis=1).max())

                    rows.append({
                        "scenario": scenario, "province": province, "mode": mode,
                        "cv": cv, "success": True,
                        "direction_dispersion": disp,
                        "max_abs_dq": float(np.abs(q1 - q0).max()),
                        "E_cost_0": float(cost0.mean()),
                        "E_cost_1": float(cost1.mean()),
                        "CVaR_0": _empirical_cvar(cost0, ALPHA),
                        "CVaR_1": _empirical_cvar(cost1, ALPHA),
                    })

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "cvar_dispersion.csv", index=False, encoding="utf-8-sig")
    ok = df[df["success"]].copy()
    ok["d_CVaR_pct"] = (ok["CVaR_1"] / ok["CVaR_0"] - 1.0) * 100.0

    pd.set_option("display.width", 220)
    print(f"=== λ={LAMBDA}（纯 CVaR，α={ALPHA}）/ {BASIS} / S={N_SCEN} ===")
    print("\n方向离散度 max_s ||c_s/|c_s| − c̄/|c̄|||")
    print(
        ok.pivot_table(index=["scenario", "province"], columns=["mode", "cv"],
                       values="direction_dispersion").round(4).to_string()
    )
    print("\n决策位移 max|Δq|（g/day）")
    print(
        ok.pivot_table(index=["scenario", "province"], columns=["mode", "cv"],
                       values="max_abs_dq", aggfunc="max").round(3).to_string()
    )
    print("\nCVaR 相对 λ=0 的变化（%）")
    print(
        ok.pivot_table(index=["scenario", "province"], columns=["mode", "cv"],
                       values="d_CVaR_pct", aggfunc="mean").round(3).to_string()
    )

    summary = {
        "max_dq_at_cv005_idio": float(
            ok[ok["mode"].eq("idiosyncratic") & ok["cv"].eq(0.05)]["max_abs_dq"].max()
        ),
        "max_dq_at_cv050_idio": float(
            ok[ok["mode"].eq("idiosyncratic") & ok["cv"].eq(0.50)]["max_abs_dq"].max()
        ),
        "max_dq_common_any": float(
            ok[ok["mode"].eq("common")]["max_abs_dq"].max()
        ),
        "disp_at_cv005": float(
            ok[ok["mode"].eq("idiosyncratic") & ok["cv"].eq(0.05)]["direction_dispersion"].max()
        ),
        "disp_at_cv050": float(
            ok[ok["mode"].eq("idiosyncratic") & ok["cv"].eq(0.50)]["direction_dispersion"].max()
        ),
        "corr_disp_vs_dq": float(
            ok[ok["mode"].eq("idiosyncratic")][["direction_dispersion", "max_abs_dq"]]
            .corr().iloc[0, 1]
        ),
        "max_d_CVaR_pct": float(ok["d_CVaR_pct"].abs().max()),
    }
    print("\n=== 汇总 ===")
    for k, v in summary.items():
        print(f"  {k}: {v:.6f}")

    finalize_run(
        run_dir,
        {
            "command": "diagnose-cvar-dispersion",
            "evidence_status": "plumbing_only",
            "scope": SCOPE,
            "bounds_basis": BASIS,
            "scenarios": list(SCENARIOS),
            "cvs": list(CVS),
            "lambda": LAMBDA,
            "alpha": ALPHA,
            "n_scenarios": N_SCEN,
            "evidence_note": (
                "占位对数正态场景，非 B1 后验。用途是区分『CVaR 结构性无效』"
                "与『扰动太弱』两种解释，不作为正式数值"
            ),
            "summary": summary,
        },
        {"command": "diagnose-cvar-dispersion", "scope": SCOPE},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
