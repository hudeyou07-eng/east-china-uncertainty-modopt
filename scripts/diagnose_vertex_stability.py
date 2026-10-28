"""为什么价格对 CDG 的决策完全无效？—— 检验「分量最小点」假说。

## 问题

三件实测事实在 CDG 情景下同时成立，需要一个统一解释：

1. ``D1 vs D0`` 位移 **0.0000**（EAR，6/6 省）——价格**水平**不影响决策；
2. ``λ`` 从 0 扫到 1，``max|Δq|`` **0.0000**——价格**不确定性**不影响决策；
3. 但可行域**不是单点**（EAR/CDG 总宽度 236–373 g，无一组被钉死）。

第 3 条排除了「域被钉死」，第 1、2 条又要求「任何价格都不影响」。
唯一能同时满足的机制是：**可行域存在一个分量最小点**。

若存在 ``q*`` 使得对任意可行 ``q`` 都有 ``q*_k ≤ q_k``（逐组），
则对任意正价格向量 ``c > 0`` 都有 ``c·q* ≤ c·q``——``q*`` 是**所有**正价格
下的最优解。价格水平、价格不确定性、风险偏好、场景重加权，全都无从影响。

## 检验

**T1 分量最小点存在性**：取逐组最小值的向量
``q_min = (min_region q_1, …, min_region q_K)``（由 LP 逐组求得），
把它代回全部约束。若可行，则 ``q_min`` 就是分量最小点，假说成立。

**T2 顶点稳定性**：对每个省，在均值价格向量上乘独立对数正态扰动
（``σ=0.6``，远大于真实价格波动）生成 60 个随机正价格方向，
各自解一次确定性 LP，数**不同**最优解（按 1e-4 分桶）的个数。
若 ``n_distinct = 1``，说明最优顶点与价格方向无关——T1 的直接推论。

**T3 反例定位**：对 ``n_distinct > 1`` 的省，报出随机方向下的最大位移，
用来说明「价格确实能影响决策」的省份长什么样，与 CDG 形成对照。

## 判读

* T1 成立 + T2 = 1 → 价格传导为零是**约束集的结构性质**，不是模型缺陷，
  也不是 CVaR 的失败；论文应写「在该情景下膳食由营养下界唯一确定」。
* T1 不成立但 T2 = 1 → 顶点唯一但非分量最小，需另找机制（如退化顶点）。
* T2 > 1 → 价格能影响决策，CDG 的零位移另有原因，本假说被否证。

用法：
    python scripts/diagnose_vertex_stability.py
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
from src.b2_scenarios import deterministic  # noqa: E402
from src.io_utils import create_run_dir, finalize_run  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402

SCOPE = "k6_price"
BASIS = "ear"
SCENARIOS = ("CDG", "EAT", "HEAL_base")
N_DIR = 60
SIGMA = 0.6
SEED = 20261027
FEAS_TOL = 1e-6


def _region_rows(inst):
    """full 层的 A_ub / b_ub（box 由 bounds 承担）。"""
    a_rows, b_rows = [], []
    for coeff, lo, hi in inst.extra_constraints:
        c = np.asarray(coeff, float)
        if np.isfinite(lo):
            a_rows.append(-c)
            b_rows.append(-float(lo))
        if np.isfinite(hi):
            a_rows.append(c)
            b_rows.append(float(hi))
    mask = inst.active_mask
    n_mat = inst.nutrient_coeff[0]
    for j in range(len(inst.nutrients)):
        if not mask[j]:
            continue
        row = n_mat[j]
        if np.isfinite(inst.nutrient_lower[j]):
            a_rows.append(-row)
            b_rows.append(-float(inst.nutrient_lower[j]))
        if np.isfinite(inst.nutrient_upper[j]):
            a_rows.append(row)
            b_rows.append(float(inst.nutrient_upper[j]))
    a_ub = np.vstack(a_rows) if a_rows else None
    b_ub = np.asarray(b_rows, float) if b_rows else None
    return a_ub, b_ub


def _per_group_min(inst):
    from scipy.optimize import linprog

    k = len(inst.groups)
    a_ub, b_ub = _region_rows(inst)
    bounds = list(zip(inst.q_lower.tolist(), inst.q_upper.tolist()))
    lo = np.full(k, np.nan)
    for i in range(k):
        e = np.zeros(k)
        e[i] = 1.0
        r = linprog(e, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method="highs")
        if r.success:
            lo[i] = float(r.fun)
    return lo, a_ub, b_ub


def _is_feasible(q, inst, a_ub, b_ub):
    k = len(inst.groups)
    if np.any(q < np.asarray(inst.q_lower) - FEAS_TOL):
        return False, "q_lower"
    if np.any(q > np.asarray(inst.q_upper) + FEAS_TOL):
        return False, "q_upper"
    if a_ub is not None:
        viol = a_ub @ q - b_ub
        if np.any(viol > FEAS_TOL):
            return False, f"A_ub row {int(np.argmax(viol))} by {float(viol.max()):.4g}"
    return True, ""


def _solve_det(inst, obj):
    mask = inst.active_mask
    return solve_chance_modopt(
        obj, inst.nutrient_coeff[:, mask, :],
        inst.nutrient_lower[mask], inst.nutrient_upper[mask],
        inst.q_lower, inst.q_upper, inst.objective_weights,
        epsilon=0.05, extra_constraints=inst.extra_constraints,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_vertex_stability")
    args = ap.parse_args()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    contract = Contract.load_scope(SCOPE)
    usable, _ = contract.complete_provinces()
    rng = np.random.default_rng(SEED)

    rows: list[dict] = []
    detail: list[dict] = []

    for scenario in SCENARIOS:
        for province in usable:
            inst = contract.instance(province, scenario, bounds_basis=BASIS)
            obj, _ = deterministic(inst)
            obj = np.asarray(obj, float)
            base = _solve_det(inst, obj)
            if not base.success:
                rows.append({
                    "scenario": scenario, "province": province,
                    "solver_success": False,
                })
                continue
            q_base = np.asarray(base.q, float)

            # ---- T1 分量最小点 ----
            q_min, a_ub, b_ub = _per_group_min(inst)
            ok_min = bool(np.isfinite(q_min).all())
            if ok_min:
                feasible, why = _is_feasible(q_min, inst, a_ub, b_ub)
            else:
                feasible, why = False, "LP 不可行"

            # ---- T2 随机价格方向的顶点稳定性 ----
            c_point = obj[0, 0, :]  # 成本系数（元/g）
            sols = []
            for _ in range(N_DIR):
                mult = np.exp(rng.normal(0.0, SIGMA, size=len(inst.groups)))
                o = obj.copy()
                o[:, 0, :] = c_point[None, :] * mult[None, :]
                r = _solve_det(inst, o)
                if r.success:
                    sols.append(np.asarray(r.q, float))
            if not sols:
                rows.append({
                    "scenario": scenario, "province": province,
                    "solver_success": True, "n_dir_success": 0,
                })
                continue
            sols = np.vstack(sols)
            keys = {tuple(np.round(s, 4)) for s in sols}
            dist_from_base = np.abs(sols - q_base[None, :]).max(axis=1)
            spread = float(np.abs(sols - sols[0][None, :]).max())

            rows.append({
                "scenario": scenario, "province": province,
                "solver_success": True,
                "n_dir_success": len(sols),
                "n_distinct_vertices": len(keys),
                "componentwise_min_exists": feasible,
                "why_not": why,
                "q_min_sum": float(q_min.sum()) if ok_min else np.nan,
                "q_base_sum": float(q_base.sum()),
                "max_dist_from_base": float(dist_from_base.max()),
                "spread_across_dirs": spread,
            })
            for g, qb, qm in zip(inst.groups, q_base, q_min):
                detail.append({
                    "scenario": scenario, "province": province, "group": g,
                    "q_base": qb, "q_group_min": qm,
                    "gap": qb - qm,
                })

    rdf = pd.DataFrame(rows)
    ddf = pd.DataFrame(detail)
    rdf.to_csv(run_dir / "vertex_stability.csv", index=False, encoding="utf-8-sig")
    ddf.to_csv(run_dir / "q_vs_groupmin.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 240)
    print("=== T1 分量最小点存在性 + T2 顶点稳定性 ===")
    print(rdf[["scenario", "province", "n_distinct_vertices",
               "componentwise_min_exists", "why_not",
               "max_dist_from_base", "spread_across_dirs"]].to_string(index=False))

    print("\n=== 最优解与逐组最小值之差（>0 说明该组被'多吃了'）===")
    if not ddf.empty:
        piv = ddf.pivot_table(index=["scenario", "province"], columns="group",
                              values="gap")
        print(piv.round(2).to_string())

    summary = {
        "scenarios_with_single_vertex": int(
            (rdf["n_distinct_vertices"].eq(1)).sum()
        ),
        "scenarios_total": int(rdf["n_distinct_vertices"].notna().sum()),
        "componentwise_min_count": int(rdf["componentwise_min_exists"].sum()),
        "cdg_single_vertex": bool(
            rdf[rdf["scenario"].eq("CDG")]["n_distinct_vertices"].eq(1).all()
        ),
        "cdg_componentwise_min": bool(
            rdf[rdf["scenario"].eq("CDG")]["componentwise_min_exists"].all()
        ),
    }
    print("\n=== 汇总 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    finalize_run(
        run_dir,
        {
            "command": "diagnose-vertex-stability",
            "evidence_status": "structural",
            "scope": SCOPE,
            "bounds_basis": BASIS,
            "scenarios": list(SCENARIOS),
            "n_dir": N_DIR,
            "sigma": SIGMA,
            "evidence_note": (
                "纯 LP 顶点枚举 + 可行性检验，无随机场景语义；"
                "随机价格方向仅用于探测顶点对目标方向的敏感性"
            ),
            "summary": summary,
        },
        {"command": "diagnose-vertex-stability", "scope": SCOPE},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
