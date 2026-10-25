"""价格品类与营养篮子的对应性审计（命令行入口）。

逻辑在 src/mapping_audit.py，本脚本只负责读数据、打印、落盘。

输出：
  mapping_audit.csv     逐组的口径覆盖情况与判定
  nutrition_gap.csv     缺失食物按受影响的观测数排序（数据补录的优先级清单）
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.mapping_audit import (  # noqa: E402
    GROUP_PRICE_CATEGORIES, GROUP_ZH, audit_mapping, unmapped_tokens,
)

DATA = ROOT / "data" / "input"
OUT = ROOT / "outputs" / "mapping_audit_20261023_143000"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    panel = pd.read_excel(DATA / "price" / "price_panel_clean.xlsx", "年均值表")
    nutrition = pd.read_csv(DATA / "clean_tables" / "nutrition.csv")
    nut_foods = set(nutrition["food_name"].unique())
    panel["品类"] = panel["品类"].astype(str)

    audit = audit_mapping(panel, nut_foods)
    print("=" * 96)
    print("价格口径与营养表对应性审计")
    print("=" * 96)
    print(audit[["group_id", "group_zh", "price_observations",
                 "observations_fully_mapped", "mapped_ratio",
                 "distinct_missing_items", "verdict"]].to_string(index=False))

    gap_counter: dict[tuple[str, str], int] = {}
    for gid, cats in GROUP_PRICE_CATEGORIES.items():
        sub = panel[panel["品类"].isin(cats)]
        for _, row in sub.iterrows():
            for token in unmapped_tokens(row["品类"], row.get("口径构成"), nut_foods):
                gap_counter[(gid, token)] = gap_counter.get((gid, token), 0) + 1

    gap = pd.DataFrame(
        [{"group_id": g, "group_zh": GROUP_ZH[g], "missing_item": t, "observations": c}
         for (g, t), c in gap_counter.items()]
    ).sort_values(["observations", "group_id"], ascending=[False, True])

    print()
    print("=" * 96)
    print("缺失食物优先级（按受影响的观测数排序，前 20）")
    print("=" * 96)
    print(gap.head(20).to_string(index=False))
    print()
    print(f"受影响的观测总数: {int(gap['observations'].sum())} / {len(panel)} 个价格格")
    print(f"缺失食物种类: {len({t for _, t in gap_counter})} 种")

    audit.to_csv(OUT / "mapping_audit.csv", index=False, encoding="utf-8-sig")
    gap.to_csv(OUT / "nutrition_gap.csv", index=False, encoding="utf-8-sig")
    print(f"\n产物已写入 {OUT}")


if __name__ == "__main__":
    main()
