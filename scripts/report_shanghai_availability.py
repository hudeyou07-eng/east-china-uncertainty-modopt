"""R401：上海的**数据可得性报告**（不是决策情景）。

## 为什么 R401 改了性质

`EXPERIMENT_PLAN.md` 原定义 R401 为「上海 3 情景 × D3，产出稳定标签」。
但主决策口径 `k6_price` 需要 G07 水产品，而上海的 G07 在价格面板里**整块缺失**，
无法装配实例。继续当作决策 run 只会产生一个空目录或一个假失败。

2026-10-28 裁定（`R-2026-10-28-c`，方案 B）：
**上海不进入决策层，改为「数据边界」的显式证据。** 本脚本产出这张证据表。

## 它回答四个问题

1. 上海在每个组上到底有多少年有价？（12 组 × 9 年覆盖矩阵）
2. 缺的是哪些组、缺到什么级别？（P0 整块缺失 / P1 / P2）
3. 能不能用批发价桥接补上？（桥接表品类清单里有没有水产品）
4. 在 `k4_official` 与 `k6_price` 两个口径下，上海分别缺哪些组？

## 输出

* `coverage_matrix.csv`：12 组 × 9 年，单元格为 `observed` / `bridged` / `missing`
* `group_summary.csv`：逐组的有价年数 / 观测年数 / 桥接年数 / 首末年
* `scope_gap.csv`：两个口径各自需要的组、上海缺的组、可否进入
* `missing_classification.csv`：来自 `price_panel_clean.xlsx` 的「仍缺数据」分级
* `verdict.json`：结论（可直接引用）
* `report.md`：给人读的一页

## 用法

    python scripts/report_shanghai_availability.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.io_utils import create_run_dir, finalize_run, write_json  # noqa: E402

PROVINCE = "上海"
YEARS = list(range(2016, 2025))
SCOPES = {"k4_official": "group_audit.csv", "k6_price": "group_audit_trace_c0.95.csv"}


def cell_state(row: pd.Series) -> str:
    if pd.notna(row.get("price_cny_kg")):
        return "bridged" if row.get("price_source") == "bridged" else "observed"
    return "missing"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="R401_shanghai_availability")
    args = ap.parse_args()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    px = pd.read_csv(ROOT / "data/processed/group_prices.csv", encoding="utf-8-sig")
    onto = pd.read_csv(ROOT / "data/processed/ontology.csv", encoding="utf-8-sig")
    groups = onto["group_id"].tolist()
    label = dict(zip(onto["group_id"], onto["group_zh"]))

    sh = px[px["province"] == PROVINCE].copy()
    sh["state"] = sh.apply(cell_state, axis=1)

    # ---- 1. 覆盖矩阵 ----
    matrix = sh.pivot(index="group_id", columns="year", values="state")
    matrix = matrix.reindex(index=groups, columns=YEARS).fillna("missing")
    matrix.insert(0, "group_zh", [label.get(g, "") for g in matrix.index])
    matrix.to_csv(run_dir / "coverage_matrix.csv", encoding="utf-8-sig", index_label="group_id")

    # ---- 2. 逐组汇总 ----
    rows = []
    for gid in groups:
        g = sh[sh["group_id"] == gid]
        have = g[g["state"] != "missing"]
        rows.append({
            "group_id": gid,
            "group_zh": label.get(gid, ""),
            "n_years_total": len(YEARS),
            "n_years_priced": int(len(have)),
            "n_years_observed": int((g["state"] == "observed").sum()),
            "n_years_bridged": int((g["state"] == "bridged").sum()),
            "first_year": int(have["year"].min()) if len(have) else None,
            "last_year": int(have["year"].max()) if len(have) else None,
            "truth_eligible_years": int((have["truth_eligible"] == True).sum())  # noqa: E712
            if "truth_eligible" in have
            else 0,
        })
    summary = pd.DataFrame(rows)
    for col in ("first_year", "last_year"):
        summary[col] = summary[col].astype("Int64")
    summary.to_csv(run_dir / "group_summary.csv", index=False, encoding="utf-8-sig")

    # ---- 3. 口径缺口 ----
    gap_rows = []
    for scope, audit_file in SCOPES.items():
        audit = pd.read_csv(ROOT / "data/processed" / audit_file, encoding="utf-8-sig")
        need = audit.loc[audit["include"] == 1, "group_id"].tolist()
        missing = [g for g in need if int((sh[sh["group_id"] == g]["state"] != "missing").sum()) == 0]
        gap_rows.append({
            "scope": scope,
            "audit_file": audit_file,
            "groups_required": "|".join(need),
            "n_groups_required": len(need),
            "groups_missing_for_shanghai": "|".join(missing),
            "n_groups_missing": len(missing),
            "shanghai_usable": len(missing) == 0,
        })
    gaps = pd.DataFrame(gap_rows)
    gaps.to_csv(run_dir / "scope_gap.csv", index=False, encoding="utf-8-sig")

    # ---- 4. 缺失分级（来自权威面板的「仍缺数据」表） ----
    raw = pd.read_excel(ROOT / "data/input/price/price_panel_clean.xlsx", sheet_name="仍缺数据")
    sh_missing = raw[raw["省份"] == PROVINCE]
    miss = (
        sh_missing.groupby(["品类", "缺口类型"])
        .size()
        .reset_index(name="n_cells")
        .sort_values(["缺口类型", "n_cells"], ascending=[True, False])
    )
    miss.to_csv(run_dir / "missing_classification.csv", index=False, encoding="utf-8-sig")

    # ---- 5. 桥接可行性 ----
    bridge = pd.read_csv(ROOT / "data/input/external/price_bridge_wholesale.csv", encoding="utf-8-sig")
    bridge_cats = sorted(bridge["category"].unique().tolist())
    aquatic_in_bridge = [c for c in bridge_cats if "水产" in c]

    # 旧清洗表里那条无年份的单点记录：必须显式登记，否则读者会问「明明有一条价」
    legacy = pd.read_csv(ROOT / "data/input/clean_tables/prices.csv", encoding="utf-8-sig")
    legacy_hit = legacy[(legacy["region"] == PROVINCE) & (legacy["category"].astype(str).str.contains("水产"))]

    verdict = {
        "run_id": "R401",
        "command": "report-shanghai-availability",
        "evidence_status": "structural",
        "province": PROVINCE,
        "decision_scope_main": "k6_price",
        "can_enter_k6_price": False,
        "blocking_group": "G07",
        "blocking_reason": "G07（水产品）在价格面板 9 年全部缺失；批发价桥接表不含水产品品类，仓库内不可修复",
        "can_enter_k4_official": bool(gaps.loc[gaps["scope"] == "k4_official", "shanghai_usable"].iloc[0]),
        "n_groups_with_any_price": int((summary["n_years_priced"] > 0).sum()),
        "groups_without_any_price": summary.loc[summary["n_years_priced"] == 0, "group_id"].tolist(),
        "bridge_categories": bridge_cats,
        "aquatic_categories_in_bridge": aquatic_in_bridge,
        "legacy_single_point_records": [
            {
                "price_record_id": r["price_record_id"],
                "category": r["category"],
                "price_value_cny_kg": float(r["price_value"]),
                "source_file": r["source_file"],
                "source_row": int(r["source_row"]),
                "has_year": False,
                "usable_in_panel": False,
                "why": "无年份字段的单时点记录，无法定位到 2016–2024 的某一年；强行使用等于给该组建一个年份不明的价",
            }
            for _, r in legacy_hit.iterrows()
        ],
        "missing_cells_p0": int((sh_missing["缺口类型"] == "整块缺失-品类").sum()),
        "conclusion": (
            "上海在 k6_price 下不可装配（缺 G07 且不可桥接），故不进入决策层；"
            "在 k4_official 的四个组上齐备，可作为附录单点对照，但不得与 K=6 结果并列比较。"
        ),
        "artifacts": [
            "coverage_matrix.csv",
            "group_summary.csv",
            "scope_gap.csv",
            "missing_classification.csv",
            "report.md",
        ],
    }

    # ---- 6. 一页报告 ----
    lines = [
        f"# R401 上海数据可得性报告",
        "",
        f"- 决策口径 `k6_price` 可否纳入：**否**（缺 {verdict['blocking_group']}）",
        f"- 合同口径 `k4_official` 可否纳入：**{'是' if verdict['can_enter_k4_official'] else '否'}**",
        f"- 有任一价格的组：{verdict['n_groups_with_any_price']}/12；完全无价格的组："
        f"{'、'.join(verdict['groups_without_any_price']) or '无'}",
        f"- 桥接表品类：{'、'.join(bridge_cats)}（水产品：**无**）",
        "",
        "## 逐组覆盖",
        "",
        "| 组 | 名称 | 有价年数 | 观测 | 桥接 | 首年 | 末年 |",
        "|---|---|---|---|---|---|---|",
    ]
    def fmt(v) -> str:
        return "—" if pd.isna(v) else str(int(v))

    for _, r in summary.iterrows():
        lines.append(
            f"| {r['group_id']} | {r['group_zh']} | {r['n_years_priced']}/{r['n_years_total']} | "
            f"{r['n_years_observed']} | {r['n_years_bridged']} | {fmt(r['first_year'])} | {fmt(r['last_year'])} |"
        )
    lines += [
        "",
        "## 口径缺口",
        "",
        "| 口径 | 需要组数 | 上海缺失组 | 可用 |",
        "|---|---|---|---|",
    ]
    for _, r in gaps.iterrows():
        lines.append(
            f"| {r['scope']} | {r['n_groups_required']} | {r['groups_missing_for_shanghai'] or '—'} | "
            f"{'是' if r['shanghai_usable'] else '否'} |"
        )
    if verdict["legacy_single_point_records"]:
        rec = verdict["legacy_single_point_records"][0]
        lines += [
            "",
            "## 一条容易被误用的记录",
            "",
            f"`clean_tables/prices.csv` 里有一条上海水产品价 {rec['price_value_cny_kg']} 元/kg"
            f"（{rec['price_record_id']}，来自 `{rec['source_file']}` 第 {rec['source_row']} 行）。",
            "它**没有年份字段**，无法定位到 2016–2024 的某一年；且权威面板把该组 9 年全部标为"
            "「整块缺失-品类（P0）」。故它不能用作该组的一年观测。",
        ]
    lines += ["", f"> {verdict['conclusion']}", ""]
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")

    finalize_run(
        run_dir,
        verdict,
        {
            "command": "report-shanghai-availability",
            "run_id": "R401",
            "province": PROVINCE,
            "years": YEARS,
            "scopes": SCOPES,
            "data_inputs": [
                "data/processed/group_prices.csv",
                "data/processed/ontology.csv",
                "data/processed/group_audit.csv",
                "data/processed/group_audit_trace_c0.95.csv",
                "data/input/price/price_panel_clean.xlsx",
                "data/input/external/price_bridge_wholesale.csv",
                "data/input/clean_tables/prices.csv",
            ],
        },
    )
    print(f"[R401] {run_dir}")
    print(f"  k6_price 可用: {verdict['can_enter_k6_price']} | k4_official 可用: {verdict['can_enter_k4_official']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
