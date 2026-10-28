"""可行域几何：为什么风险厌恶（CVaR）动不了推荐膳食？

## 问题

两条实测事实需要统一解释：

1. `DIAG_cvar_channel`：``λ`` 从 0 到 1，``max|Δq|`` **精确为 0.0000**，
   ``E_cost`` / ``CVaR_cost`` 一位小数都不变。即「换了目标函数形式，解不动」。
2. 价格水平传导在两种口径下**结论相反**：
   - RNI 下 D1（省内价）相对 D0（合并价）位移 **54.00 g/day**（江苏）；
   - EAR 下同一对比位移 **0.0000 g/day**。

这两件事可能是同一个原因：**可行域被钉死**。若可行域是单点，
则任何目标函数（线性期望、CVaR、任意 λ）都给出同一个解，
「风险厌恶无效」就不是 CVaR 的缺陷，而是约束集的属性。

## 设计

对每个 (口径 × 情景 × 省)，在**三层**约束上逐组求 ``[min, max]``：

* ``box``       —— 只有组内上下界 ``q_lower ≤ q ≤ q_upper``
* ``box+joint`` —— 再加联合约束（如 CDG 的 ``q_G05+q_G06 ∈ [40,75]``）
* ``full``      —— 再加**进入求解器的**营养约束（``active_mask`` 为真的那些）

``width = max − min``。``width < 1e-6`` 记为该组被钉死。

第三层才是求解器真正的可行域。前两层是分解，用来看「是谁把域压小的」。

**响应性检验**（比宽度更直接）：把单个组的价格乘 1.3 后重解确定性 LP，
看 ``max|Δq|``。若对**每个**组都无响应，则 ``q`` 与目标函数无关——
这是「域被钉死」的充分证据，且不依赖宽度计算是否正确。

## 判读

* ``full`` 层全部组宽度 ≈ 0 → 可行域是单点/极薄片，**任何**目标形式都无效；
* ``full`` 宽但单组抬价无响应 → 该组在当前顶点处不是「可移动方向」；
* ``RNI`` 宽而 ``EAR`` 窄 → 切 EAR 的隐藏代价：把价格传导一起掐掉了
  （因为 EAR 让更多营养素变为可操作，``active_mask`` 变大，约束变多）。

用法：
    python scripts/diagnose_feasible_width.py
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
from src.robust_modopt import solve_chance_modopt  # noqa: E402
from src.io_utils import create_run_dir, finalize_run  # noqa: E402

SCOPE = "k6_price"
SCENARIOS = ("CDG", "EAT", "HEAL_base")
BASES = ("rni", "ear")
TILT = 1.3  # 单组抬价倍数
PIN_TOL = 1e-6


def _rows_for(inst, include_joint: bool, include_nutrient: bool):
    """把三层约束拼成 linprog 的 A_ub / b_ub。"""
    a_rows: list[np.ndarray] = []
    b_rows: list[float] = []
    if include_joint:
        for coeff, lo, hi in inst.extra_constraints:
            c = np.asarray(coeff, dtype=float)
            if np.isfinite(lo):
                a_rows.append(-c)
                b_rows.append(-float(lo))
            if np.isfinite(hi):
                a_rows.append(c)
                b_rows.append(float(hi))
    if include_nutrient:
        mask = inst.active_mask
        n_mat = inst.nutrient_coeff[0]
        for j in range(len(inst.nutrients)):
            if not mask[j]:
                continue
            row = n_mat[j]
            lo = inst.nutrient_lower[j]
            hi = inst.nutrient_upper[j]
            if np.isfinite(lo):
                a_rows.append(-row)
                b_rows.append(-float(lo))
            if np.isfinite(hi):
                a_rows.append(row)
                b_rows.append(float(hi))
    if not a_rows:
        return None, None
    return np.vstack(a_rows), np.asarray(b_rows, dtype=float)


def group_widths(inst, include_joint: bool, include_nutrient: bool):
    """逐组求可行域上的 [min, max]。不可行时返回 nan。"""
    from scipy.optimize import linprog

    k = len(inst.groups)
    a_ub, b_ub = _rows_for(inst, include_joint, include_nutrient)
    bounds = list(zip(
        np.asarray(inst.q_lower, float).tolist(),
        np.asarray(inst.q_upper, float).tolist(),
    ))
    lo_v = np.full(k, np.nan)
    hi_v = np.full(k, np.nan)
    for i in range(k):
        e = np.zeros(k)
        e[i] = 1.0
        r = linprog(e, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method="highs")
        if r.success:
            lo_v[i] = float(r.fun)
        r2 = linprog(-e, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method="highs")
        if r2.success:
            hi_v[i] = float(-r2.fun)
    return lo_v, hi_v


def _solve_det(inst, obj_s):
    """确定性单场景硬约束求解（与 D1 同口径）。"""
    mask = inst.active_mask
    return solve_chance_modopt(
        obj_s,
        inst.nutrient_coeff[:, mask, :],
        inst.nutrient_lower[mask],
        inst.nutrient_upper[mask],
        inst.q_lower,
        inst.q_upper,
        inst.objective_weights,
        epsilon=0.05,
        extra_constraints=inst.extra_constraints,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_feasible_width")
    args = ap.parse_args()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    contract = Contract.load_scope(SCOPE)
    usable, _ = contract.complete_provinces()

    width_rows: list[dict] = []
    region_rows: list[dict] = []
    tilt_rows: list[dict] = []
    d01_rows: list[dict] = []

    for basis in BASES:
        for scenario in SCENARIOS:
            for province in usable:
                inst = contract.instance(province, scenario, bounds_basis=basis)
                k = len(inst.groups)

                for layer, (ij, inu) in {
                    "box": (False, False),
                    "box+joint": (True, False),
                    "full": (True, True),
                }.items():
                    lo_v, hi_v = group_widths(inst, ij, inu)
                    ok = np.isfinite(lo_v) & np.isfinite(hi_v)
                    width = np.where(ok, hi_v - lo_v, np.nan)
                    region_rows.append({
                        "basis": basis, "scenario": scenario,
                        "province": province, "layer": layer,
                        "feasible": bool(ok.all()),
                        "groups_pinned": int((width[ok] < PIN_TOL).sum()),
                        "groups_total": int(ok.sum()),
                        "total_width": float(np.nansum(width)),
                        "max_width": float(np.nanmax(width)) if ok.any() else np.nan,
                        "n_active_nutrient": int(inst.active_mask.sum()),
                        "n_nutrient": int(len(inst.nutrients)),
                        "n_joint": int(len(inst.extra_constraints)),
                    })
                    for g, w, lo_i, hi_i in zip(inst.groups, width, lo_v, hi_v):
                        width_rows.append({
                            "basis": basis, "scenario": scenario,
                            "province": province, "layer": layer, "group": g,
                            "min": lo_i, "max": hi_i, "width": w,
                            "pinned": bool(np.isfinite(w) and w < PIN_TOL),
                        })

                # ---- 单组抬价响应性（full 层） ----
                obj, _ = deterministic(inst)
                obj = np.asarray(obj, dtype=float)
                base = _solve_det(inst, obj)
                if not base.success:
                    continue
                q0 = np.asarray(base.q, dtype=float)
                for i, g in enumerate(inst.groups):
                    tilted = obj.copy()
                    tilted[:, 0, i] *= TILT  # obj 形状 [S, L, K]，L=0 是成本
                    res = _solve_det(inst, tilted)
                    tilt_rows.append({
                        "basis": basis, "scenario": scenario,
                        "province": province, "group": g,
                        "success": bool(res.success),
                        "max_abs_dq": (
                            float(np.abs(np.asarray(res.q, float) - q0).max())
                            if res.success else np.nan
                        ),
                    })

                # ---- D1 vs D0（复算，用于与宽度对照） ----
                inst0 = contract.instance(
                    province, scenario, bounds_basis=basis, price_mode="pooled"
                )
                obj0, _ = deterministic(inst0)
                r0 = _solve_det(inst0, np.asarray(obj0, dtype=float))
                d01_rows.append({
                    "basis": basis, "scenario": scenario, "province": province,
                    "success": bool(r0.success),
                    "max_abs_d1_d0": (
                        float(np.abs(np.asarray(r0.q, float) - q0).max())
                        if r0.success else np.nan
                    ),
                })

    wdf = pd.DataFrame(width_rows)
    rdf = pd.DataFrame(region_rows)
    tdf = pd.DataFrame(tilt_rows)
    ddf = pd.DataFrame(d01_rows)
    for name, df in (
        ("group_widths.csv", wdf),
        ("region_summary.csv", rdf),
        ("price_tilt.csv", tdf),
        ("d1_vs_d0.csv", ddf),
    ):
        df.to_csv(run_dir / name, index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 240)

    print("=== 可行域宽度：被钉死的组数 / 总组数（full 层 = 求解器真正看到的域）===")
    piv = rdf[rdf["layer"].eq("full")].pivot_table(
        index=["scenario", "province"], columns="basis",
        values=["groups_pinned", "total_width"],
    )
    print(piv.round(3).to_string())

    print("\n=== 三层对比：总宽度合计（越大越自由）===")
    agg = rdf.pivot_table(
        index=["basis", "scenario"], columns="layer", values="total_width", aggfunc="mean"
    )
    print(agg.round(2).to_string())

    print("\n=== active_mask 规模（谁被排除出约束）===")
    am = rdf[rdf["layer"].eq("full")].pivot_table(
        index=["scenario", "province"], columns="basis", values="n_active_nutrient"
    )
    print(am.to_string())

    print(f"\n=== 单组价格 ×{TILT} 的响应性（max|Δq|，g/day；0 = 目标函数推不动）===")
    tp = tdf.pivot_table(
        index=["scenario", "province"], columns="basis", values="max_abs_dq", aggfunc="max"
    )
    print(tp.round(4).to_string())

    print("\n=== D1 vs D0 位移（g/day）===")
    print(
        ddf.pivot_table(index=["scenario", "province"], columns="basis",
                        values="max_abs_d1_d0").round(4).to_string()
    )

    summary = {
        "pinned_ratio_full_ear": float(
            rdf[rdf["layer"].eq("full") & rdf["basis"].eq("ear")]["groups_pinned"].sum()
            / max(1, rdf[rdf["layer"].eq("full") & rdf["basis"].eq("ear")]["groups_total"].sum())
        ),
        "pinned_ratio_full_rni": float(
            rdf[rdf["layer"].eq("full") & rdf["basis"].eq("rni")]["groups_pinned"].sum()
            / max(1, rdf[rdf["layer"].eq("full") & rdf["basis"].eq("rni")]["groups_total"].sum())
        ),
        "tilt_max_dq_ear": float(
            tdf[tdf["basis"].eq("ear")]["max_abs_dq"].max(skipna=True)
        ),
        "tilt_max_dq_rni": float(
            tdf[tdf["basis"].eq("rni")]["max_abs_dq"].max(skipna=True)
        ),
        "d1d0_max_ear": float(ddf[ddf["basis"].eq("ear")]["max_abs_d1_d0"].max(skipna=True)),
        "d1d0_max_rni": float(ddf[ddf["basis"].eq("rni")]["max_abs_d1_d0"].max(skipna=True)),
        "d1d0_positive_provinces_rni": int(
            ddf[ddf["basis"].eq("rni")]["max_abs_d1_d0"].gt(1e-6).sum()
        ),
        "d1d0_positive_provinces_ear": int(
            ddf[ddf["basis"].eq("ear")]["max_abs_d1_d0"].gt(1e-6).sum()
        ),
    }
    print("\n=== 汇总 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    finalize_run(
        run_dir,
        {
            "command": "diagnose-feasible-width",
            "evidence_status": "structural",
            "scope": SCOPE,
            "scenarios": list(SCENARIOS),
            "bases": list(BASES),
            "pin_tol": PIN_TOL,
            "tilt": TILT,
            "evidence_note": (
                "纯 LP 几何计算，无随机场景、无求解器启发式，结果可逐位复现。"
                "full 层 = box ∩ 联合约束 ∩ active_mask 营养约束，与求解器看到的域一致"
            ),
            "summary": summary,
        },
        {"command": "diagnose-feasible-width", "scope": SCOPE},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
