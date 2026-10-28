"""价格面板的观测覆盖审计 + G3 gate 的两条盲区（CHANGELOG §30）。

## 为什么需要这个脚本

`scripts/check_contract_gates.py` 的 G3 报 PASS，但它有两处没检查：

1. **`thin` 是组级、不是单元级**：`n_obs` 按 `group_id` 汇总所有省所有年份，
   一个组总观测数够了就过，即使某个 (省, 组) 单元只有 1 年观测。
2. **`collapsed` 指标完全由「部分结构」缺陷构成**：它算的是
   「多品类 observed 行里 price == price_min 的比例」，阈值 <50%。
   而 `structure_weighted_partial(pork=1.000)` 的行（只观测到猪肉、权重归一）
   必然等于猪肉价、也就是最低价。实测 23/23 全部来自这类行，排除后是 0.000。
   即**gate 之所以通过，是因为缺陷恰好只影响 45.1%，差 5 个百分点就要 FAIL**。

这个脚本把两件事都量化出来，供论文数据节与 gate 修订引用。

## 输出

* `coverage_by_cell.csv`：36 个 (省, 组) 单元的年份覆盖（总年数 / 观测年数 / 有价年数 / 分类）
* `coverage_summary.json`：分布与计数
* `g3_blindspot.json`：collapsed 的构成拆解、thin 的组级 vs 单元级差异

## 用法

    python scripts/diagnose_price_coverage.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.io_utils import create_run_dir, finalize_run  # noqa: E402

GROUPS = ["G02", "G04", "G05", "G06", "G07", "G08"]
PROVINCES = ["安徽", "山东", "江苏", "江西", "浙江", "福建"]
CATEGORY_WEIGHTS = {"pork": 0.788, "beef": 0.136, "lamb": 0.076}


def classify(g: pd.DataFrame) -> str:
    n = len(g)
    n_obs = int((g["n_observed_categories"] > 0).sum())
    n_br = int((g["price_source"] == "bridged").sum())
    n_have = int(g["price_cny_kg"].notna().sum())
    if n_obs == n:
        return "全部观测"
    if n_obs == 0 and n_br == n:
        return "全部桥接"
    if n_obs > 0 and n_have == n:
        return "部分观测+桥接"
    if n_obs > 0:
        return "部分观测+缺年"
    return "无价格"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_price_coverage")
    args = ap.parse_args()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    px = pd.read_csv(ROOT / "data/processed/group_prices.csv", encoding="utf-8-sig")
    d = px[px["group_id"].isin(GROUPS) & px["province"].isin(PROVINCES)].copy()

    # ---- 逐单元覆盖 ----
    rows = []
    for (prov, gid), g in d.groupby(["province", "group_id"], sort=True):
        rows.append({
            "province": prov,
            "group_id": gid,
            "n_years": int(len(g)),
            "n_obs_years": int((g["n_observed_categories"] > 0).sum()),
            "n_bridged_years": int((g["price_source"] == "bridged").sum()),
            "n_price_years": int(g["price_cny_kg"].notna().sum()),
            "class": classify(g),
        })
    cov = pd.DataFrame(rows)
    cov.to_csv(run_dir / "coverage_by_cell.csv", index=False, encoding="utf-8-sig")

    # ---- G3 盲区 1：thin 的组级 vs 单元级 ----
    per_group = (
        d[d["observed"]].groupby("group_id")
        .agg(n_obs=("price_cny_kg", "size"), n_region=("province", "nunique"))
    )
    per_cell = cov[["province", "group_id", "n_price_years"]].copy()

    # ---- G3 盲区 2：collapsed 的构成 ----
    multi = px[px["n_categories"] > 1]
    obs = multi[multi["observed"]]
    at_min = obs[np.isclose(obs["price_cny_kg"], obs["price_min"], atol=1e-6)]
    part = obs[obs["aggregation"].str.startswith("structure_weighted_partial")]
    clean = obs[~obs["aggregation"].str.startswith("structure_weighted_partial")]

    def _share(frame: pd.DataFrame) -> float:
        if not len(frame):
            return float("nan")
        return float(np.isclose(frame["price_cny_kg"], frame["price_min"], atol=1e-6).mean())

    weight_loss = {}
    for agg in part["aggregation"].unique():
        kept = sum(w for k, w in CATEGORY_WEIGHTS.items() if k in agg)
        weight_loss[agg] = round(1.0 - kept, 4)

    summary = {
        "n_cells": int(len(cov)),
        "cells_all_observed": int((cov["class"] == "全部观测").sum()),
        "cells_fully_bridged": int((cov["class"] == "全部桥接").sum()),
        "cells_le_2_years": int((cov["n_price_years"] <= 2).sum()),
        "cells_le_4_years": int((cov["n_price_years"] <= 4).sum()),
        "cells_exactly_1_year": int((cov["n_price_years"] == 1).sum()),
        "cells_exactly_1_year_list": sorted(
            f"{r['province']}/{r['group_id']}"
            for _, r in cov[cov["n_price_years"] == 1].iterrows()
        ),
        "cells_fully_bridged_list": sorted(
            f"{r['province']}/{r['group_id']}"
            for _, r in cov[cov["class"] == "全部桥接"].iterrows()
        ),
        "median_price_years": float(cov["n_price_years"].median()),
        "g3_collapsed_overall": _share(obs),
        "g3_collapsed_excluding_partial": _share(clean),
        "n_rows_at_min": int(len(at_min)),
        "n_rows_at_min_from_partial": int(
            at_min["aggregation"].str.startswith("structure_weighted_partial").sum()
        ),
        "n_partial_rows": int(len(part)),
        "weight_mass_lost": weight_loss,
        "g3_thin_is_group_level": {
            gid: {"n_obs": int(r["n_obs"]), "n_region": int(r["n_region"])}
            for gid, r in per_group.iterrows()
        },
        "g3_thin_would_flag_cells_below_4y": sorted(
            f"{r['province']}/{r['group_id']}"
            for _, r in per_cell[per_cell["n_price_years"] < 4].iterrows()
        ),
    }

    pd.set_option("display.width", 240)
    print("=== 逐单元年份覆盖（有价格的年数 / 9）===")
    print(cov.pivot(index="province", columns="group_id", values="n_price_years").to_string())
    print()
    print("=== 分类计数 ===")
    for k in ("n_cells", "cells_all_observed", "cells_fully_bridged",
              "cells_le_2_years", "cells_le_4_years", "cells_exactly_1_year"):
        print(f"  {k}: {summary[k]}")
    print(f"  只有 1 年的单元: {summary['cells_exactly_1_year_list']}")
    print(f"  全部桥接的单元: {summary['cells_fully_bridged_list']}")
    print()
    print("=== G3 盲区 2：collapsed 指标的构成 ===")
    print(f"  多品类 observed 行 {len(obs)}；等于 price_min {len(at_min)} 行"
          f"（其中来自部分结构 {summary['n_rows_at_min_from_partial']} 行）")
    print(f"  collapsed 全量 = {summary['g3_collapsed_overall']:.3f}（阈值 <0.5）")
    print(f"  collapsed 排除部分结构 = {summary['g3_collapsed_excluding_partial']:.3f}")
    print(f"  部分结构权重质量损失: {weight_loss}")

    # ---- 一致性筛查：单元偏离「本省自身价格水平」多少 ----
    # 这不是错误判定，只是筛出「值得回源核对」的单元。跨省价格差异本身是真实的，
    # 所以只看残差、不下结论。
    m = d.groupby(["group_id", "province"])["price_cny_kg"].mean().unstack()
    rel = (m.div(m.median(axis=1), axis=0) - 1.0) * 100.0  # 相对组内中位
    screen_rows = []
    for gid in GROUPS:
        for prov in PROVINCES:
            own = float(rel.loc[gid, prov])
            others = float(rel.loc[[g for g in GROUPS if g != gid], prov].median())
            screen_rows.append({
                "group_id": gid,
                "province": prov,
                "rel_to_group_median_pct": own,
                "province_level_pct": others,
                "residual_pct": own - others,
                "n_price_years": int(
                    cov.loc[(cov["province"] == prov) & (cov["group_id"] == gid),
                            "n_price_years"].iloc[0]
                ),
            })
    screen = pd.DataFrame(screen_rows)
    screen["flag_abs_residual_gt_30"] = screen["residual_pct"].abs() > 30.0
    screen.to_csv(run_dir / "consistency_screen.csv", index=False, encoding="utf-8-sig")

    print()
    print("=== 一致性筛查：|残差| > 30 个百分点的单元（仅提示回源核对，非错误判定）===")
    flagged = screen[screen["flag_abs_residual_gt_30"]].sort_values(
        "residual_pct", key=lambda s: s.abs(), ascending=False
    )
    print(flagged.round(1).to_string(index=False) if len(flagged) else "  无")

    summary["consistency_flags"] = [
        {
            "cell": f"{r['province']}/{r['group_id']}",
            "residual_pct": round(float(r["residual_pct"]), 1),
            "n_price_years": int(r["n_price_years"]),
        }
        for _, r in flagged.iterrows()
    ]
    summary["consistency_n_flagged"] = int(len(flagged))

    finalize_run(
        run_dir,
        {
            "command": "diagnose-price-coverage",
            "evidence_status": "structural",
            "scope": "k6_price",
            "groups": GROUPS,
            "provinces": PROVINCES,
            "evidence_note": (
                "纯数据审计，无求解。逐 (省,组) 单元统计年份覆盖，"
                "并拆解 check_contract_gates.py 的 G3 collapsed 指标构成。"
                "结论：G3 的 thin 是组级不是单元级；collapsed 完全由"
                "structure_weighted_partial(pork=1.000) 的行构成。"
            ),
            "summary": summary,
        },
        {"command": "diagnose-price-coverage", "scope": "k6_price"},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
