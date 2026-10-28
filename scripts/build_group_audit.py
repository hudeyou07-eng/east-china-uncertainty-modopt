"""Build the frozen food-group ontology and the group audit table.

This is the first of the seven B2 processed-data contract files defined in
docs/EXPERIMENT_PLAN.md section 3. It maps every raw category label from the
four data domains (price, consumption, nutrition, environment) onto a single
`group_id`, then applies the price / nutrition / environment gates and records
an explicit include decision with a reason.

Outputs:
    data/processed/ontology.csv
    data/processed/group_audit.csv
    data/processed/group_audit_summary.json
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

from src.data_audit import load_clean_price_panel  # noqa: E402
from src.mapping_audit import audit_mapping  # noqa: E402
from src.ontology import (  # noqa: E402
    ENV_METRICS,
    GLOBAL_ENV_METRICS,
    HARD_NUTRIENTS,
    MIN_CONSUMPTION_REGIONS,
    MIN_PRICE_OBSERVATIONS,
    MIN_PRICE_REGIONS,
    ONTOLOGY,
    ONTOLOGY_VERSION,
)

DATA = ROOT / "data" / "input"
PROCESSED = ROOT / "data" / "processed"

OIL_DENSITY = 0.92



def price_stats(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group in ONTOLOGY:
        subset = panel[panel["group_raw"].isin(group["price_categories"])]
        observed = subset[subset["observed"]]
        rows.append(
            {
                "group_id": group["group_id"],
                "price_observations": int(observed["value"].notna().sum()),
                "price_regions": int(observed["province"].nunique()),
                "price_truth_eligible": int(observed["truth_eligible"].sum())
                if "truth_eligible" in observed
                else int(observed["value"].notna().sum()),
                "price_categories_matched": len(subset["group_raw"].unique()),
                "price_categories_expected": len(group["price_categories"]),
            }
        )
    return pd.DataFrame(rows)


def nutrition_stats(
    trace_as_valid: bool = False,
    min_cell_coverage: float = 1.0,
) -> pd.DataFrame:
    """组级营养覆盖统计。

    Parameters
    ----------
    trace_as_valid
        是否把 ``value_status == "trace"`` 的格子视为有效近零值。痕量是真实的
        近零含量而不是未知，把它当缺失处理会让含痕量的整组出局。
    min_cell_coverage
        组内"食物乘硬营养素"格子的最低可用比例。1.0 等价于原先的全或无规则。
    """
    nutrition = pd.read_csv(DATA / "clean_tables" / "nutrition.csv")
    crosswalk = pd.read_csv(DATA / "clean_tables" / "food_crosswalk.csv")
    rows = []
    for group in ONTOLOGY:
        foods = crosswalk.loc[
            crosswalk["model_food_group"].isin(group["nutrition_groups"])
            & crosswalk["eligible_for_model"].astype(bool),
            "food_name",
        ].tolist()
        block = nutrition[nutrition["food_name"].isin(foods)]
        coverage = []
        trace_cells = 0
        usable_cells = 0
        for nutrient in HARD_NUTRIENTS:
            cell = block[block["nutrient_name"].eq(nutrient)].set_index("food_name")
            if len(foods) == 0:
                coverage.append(0.0)
                continue
            covered = 0
            for food in foods:
                if food not in cell.index:
                    continue
                value = cell.loc[food, "value_per_100g"]
                status = cell.loc[food, "value_status"]
                if pd.notna(value):
                    covered += 1
                elif status == "trace":
                    trace_cells += 1
                    if trace_as_valid:
                        covered += 1
            usable_cells += covered
            coverage.append(covered / len(foods))
        total_cells = len(HARD_NUTRIENTS) * len(foods)
        rows.append(
            {
                "group_id": group["group_id"],
                "nutrition_foods": len(foods),
                "nutrition_min_hard_coverage": float(min(coverage)) if coverage else 0.0,
                "nutrition_cell_ratio": (usable_cells / total_cells) if total_cells else 0.0,
                "nutrition_trace_cells": trace_cells,
                "nutrition_hard_nutrients_passing": int(sum(1 for c in coverage if c >= 1.0)),
                "nutrition_hard_nutrients_required": len(HARD_NUTRIENTS),
                "nutrition_min_cell_coverage_required": min_cell_coverage,
            }
        )
    return pd.DataFrame(rows)


def consumption_stats() -> pd.DataFrame:
    consumption = pd.read_csv(DATA / "clean_tables" / "consumption.csv")
    usable = consumption[consumption["include_in_cross_region_analysis"].astype(bool)]
    rows = []
    for group in ONTOLOGY:
        subset = usable[usable["food_group"].isin(group["consumption_groups"])]
        all_rows = consumption[consumption["food_group"].isin(group["consumption_groups"])]
        sources = sorted({str(s) for s in all_rows["source_file"].dropna().unique()})
        rows.append(
            {
                "group_id": group["group_id"],
                "consumption_regions": int(subset["region"].nunique()),
                "consumption_years": int(subset["year"].nunique()),
                "consumption_observed_cells": int(subset["value_kg_person_year"].notna().sum()),
                "baseline_source": "|".join(sources) if sources else "none",
            }
        )
    return pd.DataFrame(rows)


def environment_stats() -> pd.DataFrame:
    lca = pd.read_csv(DATA / "clean_tables" / "china_lca.csv")
    global_env = pd.read_csv(DATA / "clean_tables" / "global_environment.csv")
    rows = []
    for group in ONTOLOGY:
        lca_block = lca[lca["food_group"].isin(group["lca_groups"])]
        lca_metrics = sorted(lca_block["metric"].dropna().unique().tolist())
        lca_foods = int(lca_block["food_item"].nunique())
        lca_proxy = int(lca_block["is_group_average_proxy"].astype(bool).sum())
        global_block = global_env[global_env["entity"].isin(group["global_env_entities"])]
        global_metrics = [
            m for m in GLOBAL_ENV_METRICS if global_block[m].notna().any()
        ]
        rows.append(
            {
                "group_id": group["group_id"],
                "lca_foods": lca_foods,
                "lca_metrics_available": ";".join(lca_metrics),
                "lca_metrics_count": len(lca_metrics),
                "lca_group_average_proxy_rows": lca_proxy,
                "global_env_entities_matched": len(global_block),
                "global_env_metrics_available": ";".join(global_metrics),
                "global_env_metrics_count": len(global_metrics),
            }
        )
    return pd.DataFrame(rows)


def build_audit(
    trace_as_valid: bool = False,
    min_cell_coverage: float = 1.0,
    min_mapping_ratio: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    panel = load_clean_price_panel(
        DATA / "price" / "price_panel_clean.xlsx",
        OIL_DENSITY,
        DATA / "price" / "price_category_catalog.xlsx",
    )
    # 口径审计需要原始的「口径构成」列，长表里没有，单独读一次
    raw_sheet = pd.read_excel(DATA / "price" / "price_panel_clean.xlsx", "年均值表")
    nut_foods = set(
        pd.read_csv(DATA / "clean_tables" / "nutrition.csv")["food_name"].unique()
    )
    mapping = audit_mapping(raw_sheet, nut_foods)[
        ["group_id", "mapped_ratio", "verdict", "missing_items"]
    ].rename(columns={
        "mapped_ratio": "mapping_mapped_ratio",
        "verdict": "mapping_verdict",
        "missing_items": "mapping_missing_items",
    })
    ontology = pd.DataFrame(
        [
            {
                "group_id": g["group_id"],
                "group_en": g["group_en"],
                "group_zh": g["group_zh"],
                "price_categories": "|".join(g["price_categories"]),
                "consumption_groups": "|".join(g["consumption_groups"]),
                "nutrition_groups": "|".join(g["nutrition_groups"]),
                "lca_groups": "|".join(g["lca_groups"]),
                "global_env_entities": "|".join(g["global_env_entities"]),
                # 环境实体的品类子结构。空串表示按实体扁平等权聚合。
                # 必须进快照，否则「层级等权」这个决策无法从产物反查。
                "global_env_subgroups": "; ".join(
                    f"{k}={'+'.join(v)}" for k, v in (g.get("global_env_subgroups") or {}).items()
                ),
            }
            for g in ONTOLOGY
        ]
    )
    audit = (
        ontology[["group_id", "group_zh"]]
        .merge(price_stats(panel), on="group_id")
        .merge(nutrition_stats(trace_as_valid, min_cell_coverage), on="group_id")
        .merge(consumption_stats(), on="group_id")
        .merge(environment_stats(), on="group_id")
        .merge(mapping, on="group_id")
    )

    audit["price_gate"] = (
        (audit["price_regions"] >= MIN_PRICE_REGIONS)
        & (audit["price_observations"] >= MIN_PRICE_OBSERVATIONS)
        & (audit["price_categories_matched"] == audit["price_categories_expected"])
    )
    audit["consumption_gate"] = audit["consumption_regions"] >= MIN_CONSUMPTION_REGIONS
    if min_cell_coverage >= 1.0:
        audit["nutrition_gate"] = (
            (audit["nutrition_foods"] > 0)
            & (audit["nutrition_hard_nutrients_passing"]
               == audit["nutrition_hard_nutrients_required"])
        )
    else:
        audit["nutrition_gate"] = (
            (audit["nutrition_foods"] > 0)
            & (audit["nutrition_cell_ratio"] >= min_cell_coverage)
        )
    audit["environment_gate"] = (
        (audit["lca_metrics_count"] == len(ENV_METRICS))
        & (audit["global_env_metrics_count"] == len(GLOBAL_ENV_METRICS))
    )
    if min_mapping_ratio is None:
        audit["mapping_gate"] = True
    else:
        audit["mapping_gate"] = (
            (audit["price_observations"] == 0)
            | (audit["mapping_mapped_ratio"] >= min_mapping_ratio)
        )

    def decide(row: pd.Series) -> tuple[bool, str]:
        failures = []
        if not row["price_gate"]:
            failures.append(
                f"价格不足({row['price_observations']}观测/{row['price_regions']}省，"
                f"门槛{MIN_PRICE_OBSERVATIONS}/{MIN_PRICE_REGIONS})"
            )
        if not row["consumption_gate"]:
            failures.append(f"消费基线缺({row['consumption_regions']}/{MIN_CONSUMPTION_REGIONS}省)")
        if not row["nutrition_gate"]:
            if min_cell_coverage >= 1.0:
                failures.append(
                    f"硬营养系数不全({row['nutrition_hard_nutrients_passing']}/"
                    f"{row['nutrition_hard_nutrients_required']}项达标，"
                    f"{row['nutrition_foods']}种食物)"
                )
            else:
                failures.append(
                    f"营养格子覆盖不足({row['nutrition_cell_ratio']:.3f}，"
                    f"门槛{min_cell_coverage:.2f}，{row['nutrition_foods']}种食物，"
                    f"痕量{row['nutrition_trace_cells']}格)"
                )
        if not row["environment_gate"]:
            failures.append(
                f"环境系数不全(LCA {row['lca_metrics_count']}/3，全球表 {row['global_env_metrics_count']}/4)"
            )
        if not row["mapping_gate"]:
            failures.append(
                f"价格口径与营养篮子错位(覆盖率{row['mapping_mapped_ratio']:.2f}，"
                f"门槛{min_mapping_ratio:.2f}，缺{row['mapping_missing_items']})"
            )
        if failures:
            return False, "；".join(failures)
        return True, "四域齐备，可进入优化"

    decisions = audit.apply(decide, axis=1, result_type="expand")
    audit["include"] = decisions[0]
    audit["reason"] = decisions[1]
    audit["unit"] = "CNY/kg"

    audit = audit[
        [
            "group_id", "group_zh", "unit", "baseline_source",
            "price_observations", "price_regions", "price_gate",
            "consumption_regions", "consumption_gate",
            "nutrition_foods", "nutrition_min_hard_coverage", "nutrition_cell_ratio",
            "nutrition_trace_cells", "nutrition_gate",
            "lca_metrics_count", "global_env_metrics_count", "environment_gate",
            "mapping_mapped_ratio", "mapping_verdict", "mapping_missing_items",
            "mapping_gate",
            "include", "reason",
        ]
    ].sort_values("group_id")

    summary = {
        "ontology_version": ONTOLOGY_VERSION,
        "ontology_groups": int(len(ontology)),
        "included_groups": int(audit["include"].sum()),
        "included_group_ids": audit.loc[audit["include"], "group_id"].tolist(),
        "excluded": audit.loc[~audit["include"], ["group_id", "group_zh", "reason"]].to_dict("records"),
        "gates": {
            "min_price_regions": MIN_PRICE_REGIONS,
            "min_price_observations": MIN_PRICE_OBSERVATIONS,
            "min_consumption_regions": MIN_CONSUMPTION_REGIONS,
            "hard_nutrients": HARD_NUTRIENTS,
            "trace_as_valid": trace_as_valid,
            "min_cell_coverage": min_cell_coverage,
            "min_mapping_ratio": min_mapping_ratio,
        },
    }
    return ontology, audit, summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="构建 ontology 与组级四域审计。默认行为与历史版本一致。"
    )
    parser.add_argument(
        "--trace-as-valid", action="store_true",
        help="把 value_status 为 trace 的格子视为有效近零值",
    )
    parser.add_argument(
        "--min-cell-coverage", type=float, default=1.0,
        help="组内营养格子的最低可用比例，1.0 为全或无规则（默认）",
    )
    parser.add_argument(
        "--min-mapping-ratio", type=float, default=None,
        help="价格口径中能对上营养食物的最低观测比例，不传则不启用该门槛",
    )
    parser.add_argument(
        "--suffix", default="",
        help="输出文件后缀，用于保存敏感性分析结果而不覆盖基线",
    )
    args = parser.parse_args()

    PROCESSED.mkdir(parents=True, exist_ok=True)
    ontology, audit, summary = build_audit(
        trace_as_valid=args.trace_as_valid,
        min_cell_coverage=args.min_cell_coverage,
        min_mapping_ratio=args.min_mapping_ratio,
    )
    tail = f"_{args.suffix}" if args.suffix else ""
    if not tail:
        ontology.to_csv(PROCESSED / "ontology.csv", index=False, encoding="utf-8-sig")
    audit.to_csv(PROCESSED / f"group_audit{tail}.csv", index=False, encoding="utf-8-sig")
    (PROCESSED / f"group_audit_summary{tail}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
