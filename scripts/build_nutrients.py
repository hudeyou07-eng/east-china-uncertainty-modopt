"""生成 B2 数据合同的组级营养系数文件。

覆盖 docs/EXPERIMENT_PLAN.md 第 3 节的 ``data/processed/nutrients.csv``：

    nutrient, group_id, value_per_kg, lower, upper, source

方法说明（这三条选择都会影响 B2 的营养约束，必须随结果一起报告）：

1. **组内聚合**：组级系数取组内 eligible 食物的加权平均。单品类组（或同一品类
   的不同形态）等权；G06 红肉按**消费结构**加权（猪肉 0.788 / 牛肉 0.136 /
   羊肉 0.076），依据是组级营养密度应满足 ``n̄ = Σ n_i·q_i/T``，权重等于消费份额。
   权重与价格、环境维度共用同一套（``data/input/external/meat_consumption_structure.csv``），
   保证同一个组在三个维度上说的是同一件事。等权隐含"三品类等量消费"，
   会把红肉的脂肪与能量显著高估、蛋白低估。
2. **区间定义**：``lower`` / ``upper`` 取组内食物间的 min / max，用于表达"同一食物组
   内部不同具体食物之间的营养差异"，**不是**参数估计的置信区间。``n_foods`` 与
   ``sd_per_kg`` 一并输出，下游若需换用其他区间口径可自行重算。
3. **痕量值**：``value_status == "trace"`` 表示真实近零含量（原始文本为 Tr），按 0
   计入；``missing`` 才是真正缺失，不计入均值但会让 ``coverage_complete`` 为 False。

单位沿用源表（能量 kJ、蛋白/脂肪/碳水 g、矿物与维生素 mg 或 μg），``unit`` 列显式给出，
不做跨单位换算。

用法：
    python scripts/build_nutrients.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.component_weights import COMPONENT_BY_NUTRITION, weights_for  # noqa: E402
from src.ontology import HARD_NUTRIENTS, ONTOLOGY  # noqa: E402

DATA = ROOT / "data" / "input" / "clean_tables"
PROCESSED = ROOT / "data" / "processed"
SOURCE = "data/input/clean_tables/nutrition.csv + food_crosswalk.csv"


def load_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    nutrition = pd.read_csv(DATA / "nutrition.csv", encoding="utf-8-sig")
    crosswalk = pd.read_csv(DATA / "food_crosswalk.csv", encoding="utf-8-sig")
    return nutrition, crosswalk


def unit_of(nutrition: pd.DataFrame, nutrient: str) -> str:
    units = sorted(nutrition.loc[nutrition["nutrient_name"].eq(nutrient), "standard_unit"].dropna().unique())
    if len(units) != 1:
        raise ValueError(f"营养素 {nutrient} 单位不唯一: {units}")
    return units[0]


def build_nutrients() -> pd.DataFrame:
    nutrition, crosswalk = load_tables()
    rows = []

    for group in ONTOLOGY:
        gid = group["group_id"]
        foods = crosswalk.loc[
            crosswalk["model_food_group"].isin(group["nutrition_groups"])
            & crosswalk["eligible_for_model"].astype(bool),
            "food_name",
        ].tolist()

        for nutrient in HARD_NUTRIENTS:
            unit = unit_of(nutrition, nutrient)
            block = nutrition[
                nutrition["food_name"].isin(foods) & nutrition["nutrient_name"].eq(nutrient)
            ]

            pairs: list[tuple[str, float]] = []
            n_trace = 0
            for food in foods:
                rec = block[block["food_name"].eq(food)]
                if rec.empty:
                    continue
                val = rec["value_per_100g"].iloc[0]
                status = rec["value_status"].iloc[0]
                if pd.notna(val):
                    pairs.append((food, float(val) * 10.0))  # per 100 g -> per kg
                elif status == "trace":
                    pairs.append((food, 0.0))
                    n_trace += 1

            n_foods = len(foods)
            n_observed = len(pairs) - n_trace
            n_missing = n_foods - len(pairs)
            arr = np.asarray([v for _, v in pairs], dtype=float)

            # 组级值：结构加权（缺失品类按已观测品类归一），其余组等权。
            weights = weights_for(gid, [f for f, _ in pairs], COMPONENT_BY_NUTRITION)
            if not pairs:
                value, method = float("nan"), "none"
            elif weights:
                wsum = sum(weights.values())
                value = float(sum(v * weights[f] for f, v in pairs) / wsum)
                method = "structure_weighted(" + "/".join(
                    f"{COMPONENT_BY_NUTRITION[f]}={weights[f] / wsum:.3f}" for f, _ in pairs
                ) + ")"
            else:
                value = float(arr.mean())
                method = "flat_mean"

            rows.append(
                {
                    "nutrient": nutrient,
                    "group_id": gid,
                    "value_per_kg": value,
                    "lower": float(arr.min()) if arr.size else np.nan,
                    "upper": float(arr.max()) if arr.size else np.nan,
                    "unit": unit,
                    "source": SOURCE,
                    "n_foods": n_foods,
                    "n_observed": n_observed,
                    "n_trace": n_trace,
                    "n_missing": n_missing,
                    "sd_per_kg": float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
                    "coverage_complete": bool(n_foods > 0 and n_missing == 0),
                    "aggregation": method,
                }
            )

    out = pd.DataFrame(rows)
    out = out.sort_values(["group_id", "nutrient"]).reset_index(drop=True)
    if (out["lower"].dropna() > out["upper"].dropna()).any():
        raise ValueError("存在 lower > upper 的行")
    return out


def main() -> None:
    out = build_nutrients()
    path = PROCESSED / "nutrients.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")

    print(f"[nutrients] {len(out)} 行 = {out['group_id'].nunique()} 组 × {out['nutrient'].nunique()} 营养素")
    print(f"  单位: {out.groupby('nutrient')['unit'].first().to_dict()}")
    print("\n按组统计覆盖率:")
    stat = out.groupby("group_id").agg(
        覆盖完整=("coverage_complete", "sum"),
        行数=("coverage_complete", "size"),
        食物数=("n_foods", "first"),
    )
    stat["完整率"] = (stat["覆盖完整"] / stat["行数"]).round(2)
    print(stat.to_string())

    full = stat[stat["覆盖完整"] == stat["行数"]].index.tolist()
    print(f"\n11 项硬营养素全覆盖（无 missing）的组: {full}")

    trace_rows = out[out["n_trace"] > 0]
    if not trace_rows.empty:
        print("\n含痕量值（按 0 计入系数）的格:")
        for r in trace_rows.itertuples():
            print(f"  {r.group_id} {r.nutrient}: n_foods={r.n_foods}, n_trace={r.n_trace}")

    print(
        "\n口径提醒：本表按『痕量为真实近零』给出可用系数，"
        "而 group_audit 的 nutrition_gate 采用更严格口径（痕量不算有效观测）。\n"
        "两者对 G06 的判定因此不同：审计判 10/11（羊肉碳水为 trace）而本表为全覆盖。"
        "该差异直接决定红肉能否进入优化（trace_as_valid=True 时 K=4）。"
    )


if __name__ == "__main__":
    main()
