"""决策空间方案对比：不同准入规则下能进优化的食物组数量。

对每个方案重新跑四道门槛，报告纳入组数、决策变量与目标函数之比，
以及每个入选组的营养篮子与价格品类是否对得上。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ontology import HARD_NUTRIENTS, ONTOLOGY  # noqa: E402

DATA = ROOT / "data" / "input" / "clean_tables"
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "decision_space_20261023_134000"
OUT.mkdir(parents=True, exist_ok=True)

HARD_ALL = list(HARD_NUTRIENTS)
HARD_CORE = ["能量", "蛋白质", "脂肪", "碳水化合物"]

nutrition = pd.read_csv(DATA / "nutrition.csv")
crosswalk = pd.read_csv(DATA / "food_crosswalk.csv")
audit = pd.read_csv(PROCESSED / "group_audit.csv").set_index("group_id")


def nutrition_cells(group_nutrition: str, treat_trace_as_zero: bool):
    """返回 (食物列表, 每种硬营养素的可用食物数, 每格是否可用)。"""
    foods = crosswalk.loc[
        crosswalk["model_food_group"].eq(group_nutrition)
        & crosswalk["eligible_for_model"].astype(bool), "food_name"
    ].tolist()
    block = nutrition[nutrition.loc[:, "food_name"].isin(foods)]
    usable = {}
    for nutrient in HARD_ALL:
        cell = block[block["nutrient_name"].eq(nutrient)].set_index("food_name")
        covered = 0
        for food in foods:
            if food not in cell.index:
                continue
            value = cell.loc[food, "value_per_100g"]
            status = cell.loc[food, "value_status"]
            if pd.notna(value):
                covered += 1
            elif status == "trace" and treat_trace_as_zero:
                covered += 1
        usable[nutrient] = covered
    return foods, usable


def evaluate(scenario: dict) -> pd.DataFrame:
    rows = []
    for group in ONTOLOGY:
        gid = group["group_id"]
        zh = group["group_zh"]
        price_cats = group["price_categories"]
        nut_label = group["nutrition_groups"][0] if group["nutrition_groups"] else ""
        foods, usable = nutrition_cells(nut_label, scenario["trace_as_zero"])
        a = audit.loc[gid]
        price_ok = (a["price_observations"] >= scenario["min_obs"]
                    and a["price_regions"] >= scenario["min_regions"])
        cons_ok = a["consumption_regions"] >= 7
        env_ok = bool(a["environment_gate"])

        nutrients = HARD_CORE if scenario["nutrient_set"] == "core" else HARD_ALL
        if not foods:
            coverage = 0.0
            per_nutrient_ok = 0
        else:
            ratios = [usable[n] / len(foods) for n in nutrients]
            per_nutrient_ok = sum(1 for r in ratios if r >= 1.0)
            coverage = min(ratios) if ratios else 0.0
        cell_ratio = (sum(usable[n] for n in nutrients) / (len(nutrients) * len(foods))
                      if foods else 0.0)

        if scenario["nutrition_rule"] == "all_cells":
            nut_ok = bool(foods) and coverage >= 1.0
        elif scenario["nutrition_rule"] == "cell_ratio":
            nut_ok = bool(foods) and cell_ratio >= scenario["min_cell_ratio"]
        else:
            nut_ok = bool(foods) and per_nutrient_ok >= scenario["min_nutrients"]

        rows.append({
            "group_id": gid, "group_zh": zh,
            "price_obs": int(a["price_observations"]), "price_regions": int(a["price_regions"]),
            "price_ok": price_ok, "consumption_ok": cons_ok, "environment_ok": env_ok,
            "nutrition_foods": len(foods), "nutrition_cell_ratio": round(cell_ratio, 3),
            "nutrition_min_coverage": round(coverage, 3), "nutrition_ok": nut_ok,
            "include": price_ok and cons_ok and env_ok and nut_ok,
            "price_categories": "|".join(price_cats),
            "nutrition_basket": "|".join(foods) if foods else "（无食物）",
        })
    return pd.DataFrame(rows)


SCENARIOS = {
    "A0_现状": dict(min_obs=18, min_regions=3, nutrient_set="all",
                  nutrition_rule="all_cells", trace_as_zero=False),
    "A1_只放宽价格": dict(min_obs=12, min_regions=2, nutrient_set="all",
                     nutrition_rule="all_cells", trace_as_zero=False),
    "A2_只认trace为有效": dict(min_obs=18, min_regions=3, nutrient_set="all",
                        nutrition_rule="all_cells", trace_as_zero=True),
    "A3_格子比例90%": dict(min_obs=18, min_regions=3, nutrient_set="all",
                       nutrition_rule="cell_ratio", min_cell_ratio=0.90,
                       trace_as_zero=True),
    "A4_缩到4项营养": dict(min_obs=18, min_regions=3, nutrient_set="core",
                      nutrition_rule="all_cells", trace_as_zero=True),
    "A5_价格+trace+90%": dict(min_obs=12, min_regions=2, nutrient_set="all",
                          nutrition_rule="cell_ratio", min_cell_ratio=0.90,
                          trace_as_zero=True),
    "A6_价格+trace+80%": dict(min_obs=12, min_regions=2, nutrient_set="all",
                          nutrition_rule="cell_ratio", min_cell_ratio=0.80,
                          trace_as_zero=True),
}

summary = []
detail = {}
for name, sc in SCENARIOS.items():
    df = evaluate(sc)
    detail[name] = df
    inc = df[df.include]
    summary.append({
        "scenario": name,
        "included": len(inc),
        "groups": "|".join(inc["group_zh"]),
        "vars_per_objective": round(len(inc) / 6, 2),
        "rejected": "|".join(df.loc[~df.include, "group_zh"]),
    })

summary_df = pd.DataFrame(summary)
print("=" * 100)
print("决策空间方案对比（目标函数固定 6 个）")
print("=" * 100)
print(summary_df.to_string(index=False))

print()
print("=" * 100)
print("A0 现状：逐组四道门槛")
a0 = detail["A0_现状"]
print(a0[["group_id", "group_zh", "price_obs", "price_regions", "price_ok",
          "consumption_ok", "environment_ok", "nutrition_foods",
          "nutrition_cell_ratio", "nutrition_ok", "include"]].to_string(index=False))

print()
print("=" * 100)
print("营养篮子与价格品类的对应关系（入选组）")
for name in ["A0_现状", "A6_价格+trace+80%"]:
    print(f"\n--- {name} ---")
    for _, r in detail[name][detail[name].include].iterrows():
        print(f"  {r['group_zh']:8s} 价格: {r['price_categories']:24s} 营养篮子: {r['nutrition_basket']}")

summary_df.to_csv(OUT / "scenario_summary.csv", index=False, encoding="utf-8-sig")
for name, df in detail.items():
    df.to_csv(OUT / f"detail_{name}.csv", index=False, encoding="utf-8-sig")
(OUT / "scenarios.json").write_text(
    json.dumps({"scenarios": SCENARIOS, "hard_nutrients": HARD_ALL,
                "hard_core": HARD_CORE, "objectives": 6},
               ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n产物已写入 {OUT}")
