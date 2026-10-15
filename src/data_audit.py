from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


YEAR_RE = re.compile(r"(20\d{2})")


def _parse_price(value: object, invalid_tokens: Iterable[str]) -> float:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    text = str(value).strip()
    if not text:
        return np.nan
    if any(token in text for token in invalid_tokens):
        return np.nan
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in {"", ".", "-"}:
        return np.nan
    number = float(cleaned)
    if not np.isfinite(number) or number <= 0:
        return np.nan
    return number


def load_price_panel(path: Path, invalid_tokens: Iterable[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Price workbook not found: {path}")
    records: list[pd.DataFrame] = []
    book = pd.ExcelFile(path)
    for province in book.sheet_names:
        raw = pd.read_excel(path, sheet_name=province)
        if raw.empty or len(raw.columns) < 2:
            raise ValueError(f"Sheet {province!r} has no usable price table")
        category_col = raw.columns[0]
        year_cols = [c for c in raw.columns[1:] if YEAR_RE.search(str(c))]
        if not year_cols:
            raise ValueError(f"Sheet {province!r} has no year columns")
        long = raw.melt(
            id_vars=[category_col], value_vars=year_cols, var_name="year_raw", value_name="raw_value"
        ).rename(columns={category_col: "group_raw"})
        long["province"] = province
        long["year"] = long["year_raw"].astype(str).str.extract(YEAR_RE.pattern)[0].astype(int)
        long["value"] = [
            _parse_price(value, invalid_tokens) for value in long["raw_value"].tolist()
        ]
        long["observed"] = long["value"].notna()
        long["group_raw"] = long["group_raw"].astype(str).str.strip()
        records.append(long[["province", "group_raw", "year", "value", "observed", "raw_value"]])
    panel = pd.concat(records, ignore_index=True)
    duplicate = panel.duplicated(["province", "group_raw", "year"], keep=False)
    if duplicate.any():
        keys = panel.loc[duplicate, ["province", "group_raw", "year"]].head(10).to_dict("records")
        raise ValueError(f"Duplicate province/group/year keys found: {keys}")
    return panel.sort_values(["province", "group_raw", "year"]).reset_index(drop=True)


def load_clean_price_panel(
    path: Path, oil_density_kg_per_litre: float, category_catalog_path: Path | None = None
) -> pd.DataFrame:
    """Load the auditable annual-mean sheet and expand it to the full 7×14×9 grid."""
    if not path.exists():
        raise FileNotFoundError(f"Clean price workbook not found: {path}")
    raw = pd.read_excel(path, sheet_name="年均值表")
    required = {"省份", "品类", "年份", "年均值", "单位"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Clean price sheet is missing columns: {sorted(missing)}")
    observed = raw.rename(
        columns={
            "省份": "province",
            "品类": "group_raw",
            "年份": "year",
            "年均值": "source_value",
            "单位": "source_unit",
            "数据性质": "data_nature",
            "源单元格": "source_cell",
            "备注": "source_note",
        }
    ).copy()
    observed["year"] = pd.to_numeric(observed["year"], errors="raise").astype(int)
    observed["source_value"] = pd.to_numeric(observed["source_value"], errors="coerce")

    def convert(row: pd.Series) -> float:
        value = row["source_value"]
        if pd.isna(value):
            return np.nan
        if not np.isfinite(float(value)):
            raise ValueError(f"Non-finite price at {row['province']}/{row['group_raw']}/{row['year']}")
        unit = str(row["source_unit"]).strip()
        if unit == "元/500g":
            return float(value) * 2.0
        if unit == "元/kg":
            return float(value)
        if unit == "元/升":
            if oil_density_kg_per_litre <= 0:
                raise ValueError("Oil density must be positive")
            return float(value) / oil_density_kg_per_litre
        raise ValueError(f"Unsupported price unit {unit!r} at {row['province']}/{row['group_raw']}/{row['year']}")

    observed["value"] = observed.apply(convert, axis=1)
    if observed.duplicated(["province", "group_raw", "year"]).any():
        raise ValueError("Clean price sheet contains duplicate province/group/year keys")
    provinces = sorted(observed["province"].dropna().unique())
    groups = set(observed["group_raw"].dropna().unique())
    if category_catalog_path is not None:
        if not category_catalog_path.exists():
            raise FileNotFoundError(f"Raw category catalog not found: {category_catalog_path}")
        first_sheet = pd.ExcelFile(category_catalog_path).sheet_names[0]
        raw_catalog = pd.read_excel(category_catalog_path, sheet_name=first_sheet)
        groups.update(raw_catalog.iloc[:, 0].dropna().astype(str).str.strip().tolist())
    groups = sorted(groups)
    years = list(range(2016, 2025))
    full = pd.MultiIndex.from_product(
        [provinces, groups, years], names=["province", "group_raw", "year"]
    ).to_frame(index=False)
    panel = full.merge(
        observed[
            [
                "province",
                "group_raw",
                "year",
                "value",
                "source_value",
                "source_unit",
                "data_nature",
                "source_cell",
                "source_note",
            ]
        ],
        on=["province", "group_raw", "year"],
        how="left",
        validate="one_to_one",
    )
    panel["observed"] = panel["value"].notna()
    panel["truth_eligible"] = panel["observed"] & panel["data_nature"].eq("实测")
    panel["raw_value"] = panel["source_value"]
    return panel.sort_values(["province", "group_raw", "year"]).reset_index(drop=True)


def audit_price_panel(panel: pd.DataFrame, min_regions: int, min_observations: int) -> tuple[dict, pd.DataFrame]:
    if (panel.loc[panel["observed"], "value"] <= 0).any():
        raise ValueError("Observed prices must be strictly positive")
    total = int(len(panel))
    observed = int(panel["observed"].sum())
    by_province = (
        panel.groupby("province", as_index=False)
        .agg(total=("value", "size"), observed=("observed", "sum"))
        .assign(missing=lambda d: d["total"] - d["observed"], coverage=lambda d: d["observed"] / d["total"])
    )
    group_support = (
        panel.groupby("group_raw", as_index=False)
        .agg(
            price_observations=("observed", "sum"),
            price_regions=("province", lambda s: panel.loc[s.index].query("observed")["province"].nunique()),
        )
    )
    group_support["price_gate"] = (
        (group_support["price_regions"] >= min_regions)
        & (group_support["price_observations"] >= min_observations)
    )
    summary = {
        "rows": total,
        "observed": observed,
        "missing": total - observed,
        "coverage": observed / total if total else 0.0,
        "provinces": int(panel["province"].nunique()),
        "groups": int(panel["group_raw"].nunique()),
        "years": [int(panel["year"].min()), int(panel["year"].max())],
        "groups_passing_price_gate": int(group_support["price_gate"].sum()),
        "truth_eligible_observations": int(panel.get("truth_eligible", panel["observed"]).sum()),
        "data_nature_counts": panel.get("data_nature", pd.Series(dtype=object)).fillna("missing").value_counts().to_dict(),
        "by_province": by_province.to_dict("records"),
    }
    return summary, group_support


def make_group_audit_template(group_support: pd.DataFrame) -> pd.DataFrame:
    template = group_support.rename(columns={"group_raw": "group_label"}).copy()
    template.insert(0, "group_id", [f"G{i + 1:02d}" for i in range(len(template))])
    template["baseline_source"] = "TODO"
    template["nutrient_coverage"] = np.nan
    template["environment_coverage"] = np.nan
    template["unit"] = "CNY/kg"
    template["include"] = False
    template["reason"] = "Pending crosswalk and coefficient audit"
    return template[
        [
            "group_id",
            "group_label",
            "baseline_source",
            "price_observations",
            "price_regions",
            "price_gate",
            "nutrient_coverage",
            "environment_coverage",
            "unit",
            "include",
            "reason",
        ]
    ]
