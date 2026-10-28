"""价格面板口径诊断：换一套价格构造，EAR 的零结果还成立吗？

## 背景

CHANGELOG §25.7 发现 `Contract.price_panel()` 只用 `price_cny_kg`（观测口径），
而 `price_cny_kg_full`（观测 + 批发价桥接）从未被调用。
当时的表述暗示「换成 full 就能把 B1 插补接进决策」——**这是错的**，
已在 §28.1 更正：`price_cny_kg_full` 是**桥接**，不是 MICE 插补，
源码注释也写明它「仅供 B4 敏感性对照，不进入主口径」。

但换面板这件事本身仍值得测：如果决策对价格构造不敏感，
那么「EAR 零结果」就不是某一种价格构造的巧合。

## 三个要回答的问题

1. 两套面板的组价差多少？
2. 换面板后决策变不变（`|Δq|`）？
3. `G06` 的「部分结构」行低估了多少？（只观测到猪肉时，
   牛肉/羊肉被丢掉、权重归一成 pork=1.0，组价系统性偏低）

## 用法

    python scripts/diagnose_price_panel.py
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
SCENARIOS = ("CDG", "EAT")
BASES = ("ear", "rni")
PRICE_CSV = ROOT / "data" / "processed" / "group_prices.csv"


def _solve(inst, prices):
    """与 run_b2.py 的 D1 同口径（epsilon=0，单场景等价硬约束）。"""
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


def _panel(raw: pd.DataFrame, col: str, provinces: list[str], groups: list[str]) -> pd.DataFrame:
    """按 (省, 组) 对可用年份取均值——与 `Contract.price_panel()` 同一算法。"""
    return (
        raw.groupby(["province", "group_id"])[col]
        .mean()
        .unstack()
        .reindex(index=provinces, columns=groups)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_price_panel")
    args = ap.parse_args()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    contract = Contract.load_scope(SCOPE)
    usable, excluded = contract.complete_provinces()
    groups = list(contract.groups)

    raw = pd.read_csv(PRICE_CSV, encoding="utf-8-sig")
    raw = raw[raw["group_id"].isin(groups)]

    p_obs = _panel(raw, "price_cny_kg", usable, groups)
    p_full = _panel(raw, "price_cny_kg_full", usable, groups)

    # 2026-10-27（CHANGELOG §31）之后，主口径对 G06 也改成「缺品类先桥接补全」，
    # 于是两列在**交集**上逐行相同。但**整列并不相同**：`full` 还多填了
    # 「整组零观测」的年份（§32.1），那些行主口径仍是 NaN。
    #
    # 所以判据必须是「交集相同 **且** 行数相同」，只判 `p_full.equals(p_obs)`
    # 会把「交集相同」误读成「整列冗余」——我上一版就是这么错的（§31.1）。
    both = p_full.notna() & p_obs.notna()
    same_on_overlap = bool(
        (p_full[both].to_numpy() == p_obs[both].to_numpy()).all()
    ) if int(both.to_numpy().sum()) else False
    same_shape = bool((p_full.notna() == p_obs.notna()).all().all())
    if same_on_overlap and same_shape:
        print(
            "[提示] price_cny_kg 与 price_cny_kg_full 完全重合（交集相同且缺失位置相同），\n"
            "       本次对比恒为 0，不能作为「换面板不影响决策」的证据。\n"
            "       修复前的诊断结果见 CHANGELOG §28，旧面板备份在\n"
            "       artifacts/group_prices_before_g06fix.csv。"
        )
    elif same_on_overlap:
        extra = int(p_full.notna().to_numpy().sum() - both.to_numpy().sum())
        print(
            f"[提示] 两列在交集上逐行相同，但 full 多填了 {extra} 个格子"
            f"（整组零观测的年份）。对比仍然有意义，但差异只来自这些格子——\n"
            "       它们的价格是批发价桥接（truth_eligible=False，见 CHANGELOG §32.1）。"
        )

    # ---- 1. 面板差异 ----
    rel = (p_full / p_obs - 1.0) * 100.0
    panel_rows = []
    for prov in usable:
        for g in groups:
            panel_rows.append(
                {
                    "province": prov,
                    "group": g,
                    "price_obs": float(p_obs.loc[prov, g]),
                    "price_full": float(p_full.loc[prov, g]),
                    "rel_diff_pct": float(rel.loc[prov, g]),
                }
            )
    pdf = pd.DataFrame(panel_rows)

    # ---- 2. 决策是否改变 ----
    decision_rows = []
    for basis in BASES:
        for scenario in SCENARIOS:
            for prov in usable:
                try:
                    inst = contract.instance(prov, scenario, bounds_basis=basis)
                except Exception as exc:  # noqa: BLE001 - 记录而不中断
                    decision_rows.append(
                        {
                            "basis": basis, "scenario": scenario, "province": prov,
                            "status": f"instance_failed:{type(exc).__name__}",
                        }
                    )
                    continue
                a = p_obs.loc[prov].to_numpy(dtype=float)
                b = p_full.loc[prov].to_numpy(dtype=float)
                if np.isnan(b).any():
                    decision_rows.append(
                        {
                            "basis": basis, "scenario": scenario, "province": prov,
                            "status": "full_panel_has_nan",
                        }
                    )
                    continue
                ra = _solve(inst, a)
                rb = _solve(inst, b)
                ok = bool(ra.success) and bool(rb.success)
                decision_rows.append(
                    {
                        "basis": basis,
                        "scenario": scenario,
                        "province": prov,
                        "status": "ok" if ok else "solver_failed",
                        "dq": float(np.abs(np.asarray(ra.q, float) - np.asarray(rb.q, float)).max())
                        if ok else float("nan"),
                        "obj_obs": float(ra.objective) if ok else float("nan"),
                        "obj_full": float(rb.objective) if ok else float("nan"),
                        "obj_rel_change": float(rb.objective / ra.objective - 1.0) if ok else float("nan"),
                    }
                )
    ddf = pd.DataFrame(decision_rows)

    # ---- 3. G06 下界行的低估幅度 ----
    # 2026-10-27（CHANGELOG §32.8）后这个指标必须换算法：
    # 旧算法是 `price_cny_kg_full / price_cny_kg - 1`，测的是「主口径 vs 桥接补满」。
    # 但 §31 修完之后主口径**本身就含桥接补全**，两者在桥接行上恒等 → 恒报 0.0%，
    # 是一个「还在跑但已经测不到东西」的死指标。
    #
    # 现在有意义的比较是：**只观测到单品类（下界）的那几年，比同省其它年低多少**。
    # 参照取同省 G06 的 complete/bridged 年份；该省若没有这类年份，退回跨省中位比值。
    # 这是**估计**，不是测量——参照本身也含桥接成分，assumption 写在 ref_source 列。
    g6 = raw[raw["group_id"].eq("G06")].copy()
    agg_str = g6["aggregation"].astype(str)
    is_lb = agg_str.str.contains("lowerbound", regex=False)
    is_ref = agg_str.str.startswith("structure_weighted_complete") | agg_str.str.startswith(
        "structure_weighted_bridged"
    )

    # 省内的「下界 / 参照」比值；没有参照年份的省留空
    prov_ratio = (
        g6.assign(_lb=is_lb, _ref=is_ref)
        .groupby("province")
        .apply(
            lambda s: (
                s.loc[s["_lb"], "price_cny_kg"].mean() / s.loc[s["_ref"], "price_cny_kg"].mean()
                if s["_lb"].any() and s["_ref"].any()
                else np.nan
            ),
            include_groups=False,
        )
    )
    pooled_ratio = float(
        g6.loc[is_lb, "price_cny_kg"].mean() / g6.loc[is_ref, "price_cny_kg"].mean()
    ) if is_lb.any() and is_ref.any() else float("nan")

    part = g6[is_lb]
    rows = []
    for r in part.itertuples():
        ref = prov_ratio.get(r.province, np.nan)
        if np.isfinite(ref):
            ref_val, src = float(ref), "same_province_complete_or_bridged"
        else:
            ref_val, src = pooled_ratio, "pooled_all_provinces"
        under = (1.0 / ref_val - 1.0) * 100.0 if np.isfinite(ref_val) and ref_val > 0 else float("nan")
        rows.append({
            "province": r.province,
            "year": r.year,
            "aggregation": r.aggregation,
            "price_lowerbound": r.price_cny_kg,
            "reference_price": float(r.price_cny_kg) / ref_val if np.isfinite(ref_val) else float("nan"),
            "understate_pct": under,
            "ref_source": src,
        })
    g6_rows = pd.DataFrame(rows)

    pdf.to_csv(run_dir / "panel_diff.csv", index=False, encoding="utf-8-sig")
    ddf.to_csv(run_dir / "decision_change.csv", index=False, encoding="utf-8-sig")
    g6_rows.to_csv(run_dir / "g06_partial_structure.csv", index=False, encoding="utf-8-sig")

    ok_d = ddf[ddf["status"].eq("ok")]
    summary = {
        "panel_abs_diff_median_pct": float(np.nanmedian(np.abs(rel.to_numpy(dtype=float)))),
        "panel_abs_diff_max_pct": float(np.nanmax(np.abs(rel.to_numpy(dtype=float)))),
        "panel_nan_full": int(p_full.isna().sum().sum()),
        "g06_lowerbound_rows": int(len(g6_rows)),
        "g06_lowerbound_understate_median_pct": float(g6_rows["understate_pct"].median())
        if len(g6_rows) else float("nan"),
        "g06_lowerbound_understate_max_pct": float(g6_rows["understate_pct"].max())
        if len(g6_rows) else float("nan"),
        "g06_lowerbound_ref_sources": sorted(set(g6_rows["ref_source"])) if len(g6_rows) else [],
        "g06_pooled_lb_to_ref_ratio": pooled_ratio,
        "n_decision_cells": int(len(ok_d)),
        "n_decision_unchanged": int((ok_d["dq"] < 1e-6).sum()) if len(ok_d) else 0,
        "dq_max_ear": float(ok_d[ok_d["basis"].eq("ear")]["dq"].max()) if len(ok_d) else float("nan"),
        "dq_max_rni": float(ok_d[ok_d["basis"].eq("rni")]["dq"].max()) if len(ok_d) else float("nan"),
        "obj_rel_change_abs_median": float(ok_d["obj_rel_change"].abs().median()) if len(ok_d) else float("nan"),
    }

    pd.set_option("display.width", 240)
    print("=== 1. 组价差异（full / obs − 1，%）===")
    print(rel.round(1).to_string())
    print(
        f"\n  |差异| 中位 {summary['panel_abs_diff_median_pct']:.1f}%  "
        f"最大 {summary['panel_abs_diff_max_pct']:.1f}%  "
        f"full 面板缺失格 {summary['panel_nan_full']}"
    )

    print("\n=== 2. 换面板后决策是否改变（dq = max|Δq|，g/day）===")
    if len(ok_d):
        print(
            ok_d.pivot_table(index=["basis", "scenario"], columns="province", values="dq")
            .round(4)
            .to_string()
        )
    print("\n  目标值相对变化（%）：")
    if len(ok_d):
        print(
            ok_d.pivot_table(index=["basis", "scenario"], columns="province", values="obj_rel_change")
            .mul(100).round(2)
            .to_string()
        )

    print("\n=== 3. G06 下界行（只观测到单品类）相对参照价低估多少 ===")
    print(
        f"  {summary['g06_lowerbound_rows']} 行，低估中位 {summary['g06_lowerbound_understate_median_pct']:.1f}%，"
        f"最大 {summary['g06_lowerbound_understate_max_pct']:.1f}%"
        f"（参照来源 {summary['g06_lowerbound_ref_sources']}）"
    )

    print("\n=== 汇总 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    finalize_run(
        run_dir,
        {
            "command": "diagnose-price-panel",
            "evidence_status": "structural",
            "scope": SCOPE,
            "scenarios": list(SCENARIOS),
            "bases": list(BASES),
            "price_columns": ["price_cny_kg", "price_cny_kg_full"],
            "provinces_excluded": excluded,
            "evidence_note": (
                "对比观测口径与「观测+桥接」口径的组价，以及换面板后决策是否改变。"
                "注意 price_cny_kg_full 是桥接口径，不是 MICE 插补（CHANGELOG §28.1）。"
            ),
            "summary": summary,
        },
        {"command": "diagnose-price-panel", "scope": SCOPE},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
