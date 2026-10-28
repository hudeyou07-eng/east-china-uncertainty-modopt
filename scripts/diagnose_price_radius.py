"""价格扰动半径：EAR 下价格要偏多少，推荐膳食才会变？

## 为什么需要这个数

第十轮接线后发现：EAR 口径下 D0 ≡ D1 ≡ D3，`|Δq|` 精确为 0，
D1 在 100 个协议单元间逐位不变（CHANGELOG §25.6）。

这个「零对比度」有两种解释，对应完全相反的处置：

* **H1（稳健）**：EAR 的可行域把决策钉得很稳，价格偏几十个点都不动
  → 零对比度是**结论**，M2 可以写成「决策对价格信息稳健」；
* **H2（伪影）**：只是我们喂进去的扰动太小（协议位移仅 0.298%）
  → 零对比度是**设计产物**，必须回退 RNI 或改价格口径。

区分两者只需要一个量：**价格扰动半径**。

## 两个度量

**A. 单组价格半径**：把某一组的价格乘 ``1+δ``，找最小的 δ 使最优解改变。
报逐组最小 δ——「最敏感的那一组要偏多少」。

**B. 省际价差放大倍数**：D0 与 D1 的差别是「合并价 vs 省内价」。
在对数空间插值外推 ``p(t) = p_pooled · (p_province / p_pooled)^t``，
``t=0`` 是 D0、``t=1`` 是 D1。找最小的 t 使解改变。
（用乘法而非线性外推：线性外推在 ``t=12`` 时会让价格变负。）
``t=1`` 不动而 ``t=3`` 才动，说明真实省际价差信号比翻转阈值弱 3 倍。

**合并价的省集合必须与 ``run_b2.py`` 的 D0 完全一致**：
``base_panel = price_panel().reindex(provinces)`` 只含 6 个决策省，
``imputed_panel.mean(axis=0)`` 因此是 **6 省均值**。
初版这里误用 ``price_panel().mean(axis=0)``（7 省，含被排除的上海），
导致 B 度量复现的不是真正的 D0——安徽在 7 省口径下 ``t=4``，
在 6 省口径下 ``t=1``，差了 4 倍。现已改为 ``panel.loc[usable]``。

## 判读

* 若 A 的最小 δ ≫ 协议位移量级（0.3%）且 ≫ 0.05，则 H1 成立；
* 若 A 的最小 δ 在个位数百分点，则 EAR 只是「恰好没踩到阈值」，
  换一批数据就会翻，H2 成立；
* B 的临界 t 直接告诉作者：把价差放大多少倍才能看到对比度。

用法：
    python scripts/diagnose_price_radius.py
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
from src.ontology import HARD_NUTRIENTS  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402

SCOPE = "k6_price"
SCENARIOS = ("CDG", "EAT", "HEAL_base")
BASES = ("ear", "rni")
DELTAS = (0.01, 0.02, 0.05, 0.10, 0.20, 0.30, 0.50, 1.00, 2.00)
T_GRID = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0)
DQ_TOL = 1e-4


def _solve(inst, prices):
    """给定价格向量求解确定性硬约束 LP（其余全部沿用 ``inst``）。

    ``epsilon=0.0`` 与 ``run_b2.py`` 的 D1 一致（单场景下等价于硬约束）。
    实测 eps=0.05 在单场景时给出同一解，但口径必须与正式批次统一。
    """
    inst_p = inst.with_prices(prices)
    mask = inst_p.active_mask
    return solve_chance_modopt(
        inst_p.objective_coeff,
        inst_p.nutrient_coeff[:, mask, :],
        inst_p.nutrient_lower[mask],
        inst_p.nutrient_upper[mask],
        inst_p.q_lower,
        inst_p.q_upper,
        inst_p.objective_weights,
        epsilon=0.0,
        extra_constraints=inst_p.extra_constraints,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_price_radius")
    args = ap.parse_args()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    contract = Contract.load_scope(SCOPE)
    usable, _ = contract.complete_provinces()
    panel = contract.price_panel()

    rows: list[dict] = []
    contrast_rows: list[dict] = []
    binding_rows: list[dict] = []

    for basis in BASES:
        for scenario in SCENARIOS:
            for province in usable:
                inst = contract.instance(province, scenario, bounds_basis=basis)
                mask = inst.active_mask
                base = panel.loc[province].to_numpy(dtype=float)
                r0 = _solve(inst, base)
                if not r0.success:
                    rows.append({
                        "basis": basis, "scenario": scenario, "province": province,
                        "solver_success": False,
                    })
                    continue
                q0 = np.asarray(r0.q, float)

                # ---- C. 绑定约束集合（解释稳定性差异的来源）----
                # 注意：inst.nutrient_lower/upper 是**已扣除非决策组偏移**的生效界，
                # 因此必须与「决策组贡献」比较，不能与含偏移的总量比较。
                contrib = inst.nutrient_coeff[0, mask, :] @ q0
                eff_lo = inst.nutrient_lower[mask]
                eff_hi = inst.nutrient_upper[mask]
                rel_lo = (contrib - eff_lo) / np.maximum(np.abs(eff_lo), 1e-9)
                rel_hi = np.where(
                    np.isinf(eff_hi), np.inf,
                    (eff_hi - contrib) / np.maximum(np.abs(eff_hi), 1e-9),
                )
                act_names = [n for n, ok in zip(HARD_NUTRIENTS, mask) if ok]
                bind_lo = [n for n, v in zip(act_names, rel_lo) if abs(v) < 1e-4]
                bind_hi = [n for n, v in zip(act_names, rel_hi) if abs(v) < 1e-4]
                at_q_lo = [
                    g for g, v, l in zip(inst.groups, q0, inst.q_lower)
                    if abs(v - l) < 1e-6
                ]
                at_q_hi = [
                    g for g, v, u in zip(inst.groups, q0, inst.q_upper)
                    if abs(v - u) < 1e-6
                ]
                binding_rows.append({
                    "basis": basis, "scenario": scenario, "province": province,
                    "bind_lower": "|".join(bind_lo),
                    "bind_upper": "|".join(bind_hi),
                    "n_bind_lower": len(bind_lo),
                    "q_at_lower": "|".join(at_q_lo),
                    "q_at_upper": "|".join(at_q_hi),
                })

                # ---- A. 单组价格半径 ----
                for i, g in enumerate(inst.groups):
                    first = np.nan
                    for delta in DELTAS:
                        prices = base.copy()
                        prices[i] = base[i] * (1.0 + delta)
                        r = _solve(inst, prices)
                        if not r.success:
                            continue
                        dq = float(np.abs(np.asarray(r.q, float) - q0).max())
                        if dq > DQ_TOL:
                            first = delta
                            break
                    rows.append({
                        "basis": basis, "scenario": scenario, "province": province,
                        "group": g, "solver_success": True,
                        "radius_delta": first,
                        "never_moved": bool(np.isnan(first)),
                    })

                # ---- B. 省际价差放大（口径必须与 D0 一致：仅决策省均值）----
                pooled = contract.pooled_price(usable)
                q_pool = None
                rp = _solve(inst, pooled)
                if rp.success:
                    q_pool = np.asarray(rp.q, float)
                first_t = np.nan
                for t in T_GRID:
                    # 对数空间插值/外推：t=0 为合并价、t=1 为省内价，且恒为正
                    prices = pooled * (base / pooled) ** t
                    r = _solve(inst, prices)
                    if not r.success:
                        continue
                    dq = float(np.abs(np.asarray(r.q, float) - q_pool).max())
                    if dq > DQ_TOL:
                        first_t = t
                        break
                contrast_rows.append({
                    "basis": basis, "scenario": scenario, "province": province,
                    "pool_success": bool(rp.success),
                    "t_first_move": first_t,
                    "never_moved_to_t12": bool(np.isnan(first_t)),
                    "max_rel_gap": float(np.abs(base / pooled - 1.0).max()),
                })

    rdf = pd.DataFrame(rows)
    cdf = pd.DataFrame(contrast_rows)
    bdf = pd.DataFrame(binding_rows)
    rdf.to_csv(run_dir / "price_radius.csv", index=False, encoding="utf-8-sig")
    cdf.to_csv(run_dir / "contrast_amplification.csv", index=False, encoding="utf-8-sig")
    bdf.to_csv(run_dir / "binding_constraints.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 240)
    ok = rdf[rdf["solver_success"].eq(True)]
    print("=== A. 单组价格扰动半径（δ：价格乘 1+δ 时解首次改变）===")
    piv = ok.pivot_table(index=["basis", "scenario"], columns="group",
                         values="radius_delta", aggfunc="min")
    print(piv.round(3).to_string())

    print("\n=== 各省最敏感的那一组（半径最小值）===")
    best = (
        ok.groupby(["basis", "scenario", "province"])["radius_delta"]
        .min().reset_index()
    )
    print(best.pivot_table(index=["basis", "scenario"], columns="province",
                           values="radius_delta").round(3).to_string())

    print("\n=== B. 省际价差放大到几倍时解改变（t）===")
    print(cdf.pivot_table(index=["basis", "scenario"], columns="province",
                          values="t_first_move").round(2).to_string())

    print("\n=== C. 最优解的绑定约束（解释 A/B 差异的来源）===")
    print(bdf[bdf["scenario"].eq("CDG")][
        ["basis", "province", "bind_lower", "n_bind_lower", "q_at_lower", "q_at_upper"]
    ].to_string(index=False))

    summary = {
        "min_radius_ear": float(ok[ok["basis"].eq("ear")]["radius_delta"].min()),
        "median_radius_ear": float(ok[ok["basis"].eq("ear")]["radius_delta"].median()),
        "min_radius_rni": float(ok[ok["basis"].eq("rni")]["radius_delta"].min()),
        "median_radius_rni": float(ok[ok["basis"].eq("rni")]["radius_delta"].median()),
        "groups_never_moved_ear": int(
            ok[ok["basis"].eq("ear")]["never_moved"].sum()
        ),
        "groups_total_ear": int(len(ok[ok["basis"].eq("ear")])),
        "t_first_move_ear_median": float(
            cdf[cdf["basis"].eq("ear")]["t_first_move"].median()
        ),
        "ear_never_moved_to_t12": int(
            cdf[cdf["basis"].eq("ear")]["never_moved_to_t12"].sum()
        ),
        "ear_cells_total": int(len(cdf[cdf["basis"].eq("ear")])),
        # t=1 就是「省内价 vs 6 省合并价」，即真正的 D0↔D1 对比度是否成立
        "ear_cells_moved_at_t1": int(
            cdf[cdf["basis"].eq("ear")]["t_first_move"].eq(1.0).sum()
        ),
        "rni_cells_moved_at_t1": int(
            cdf[cdf["basis"].eq("rni")]["t_first_move"].eq(1.0).sum()
        ),
        "max_rel_gap_ear": float(cdf[cdf["basis"].eq("ear")]["max_rel_gap"].max()),
        "max_rel_gap_rni": float(cdf[cdf["basis"].eq("rni")]["max_rel_gap"].max()),
        "pool_scope": f"{len(usable)} 省（与 D0 的 base_panel.reindex(provinces) 一致）",
        "protocol_shift_mean_ref": 0.00298,
    }
    print("\n=== 汇总 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    finalize_run(
        run_dir,
        {
            "command": "diagnose-price-radius",
            "evidence_status": "structural",
            "scope": SCOPE,
            "scenarios": list(SCENARIOS),
            "bases": list(BASES),
            "deltas": list(DELTAS),
            "t_grid": list(T_GRID),
            "dq_tol": DQ_TOL,
            "evidence_note": (
                "纯 LP 价格扰动扫描，无随机场景。"
                "A 度量单组价格半径，B 度量省际价差需要放大几倍才翻转决策。"
                "B 的合并价口径 = 6 个决策省均值，与 run_b2.py 的 D0 一致；"
                "t=1 即真正的 D0↔D1 对比度。"
            ),
            "summary": summary,
        },
        {"command": "diagnose-price-radius", "scope": SCOPE},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
