# Reproducibility data bundle

This private repository contains the minimum cleaned data bundle required for authorized project members to reproduce the current audit and calibration workflow. It does not contain the full `student_doc/` folder, personal records, preview images, caches, or redundant intermediate exports.

## Included inputs

```text
data/input/
├── price/
│   ├── price_panel_clean.xlsx
│   └── price_category_catalog.xlsx
├── clean_tables/
│   ├── consumption.csv
│   ├── consumption_coverage.csv
│   ├── food_crosswalk.csv
│   ├── prices.csv
│   ├── price_summary.csv
│   ├── nutrition.csv
│   ├── china_lca.csv
│   ├── lca_summary.csv
│   └── global_environment.csv
└── workbook/
    └── diet_model_clean_data.xlsx
```

The experiment runner currently uses the two price workbooks directly. The clean tables and consolidated workbook are included to support crosswalk review and the B2 to B4 processed data contract.

`DATA_MANIFEST.json` records the byte size and SHA256 digest of every included input. Run `python scripts/build_data_manifest.py` after an authorized data update.

正式 B2 到 B4 之前，必须在 `data/processed/` 生成并冻结：

| File | Required content |
|---|---|
| `group_audit.csv` | group ID, labels, sources, coverage, include decision and reason |
| `baseline_consumption.csv` | province, year, group ID, g per person per day and observed flag |
| `group_prices.csv` | province, year, group ID, CNY per kg and source |
| `nutrients.csv` | nutrient coefficients and defensible bounds per kg edible food |
| `environment.csv` | environmental coefficients, sources and harmonized boundaries |
| `decision_bounds.csv` | province and scenario specific lower and upper intake bounds |
| `model_manifest.json` | hashes, units, ontology version, weights version and timestamp |

Every included food group must have an identifiable consumption baseline, sufficient unit price coverage, complete hard nutrient coefficients, and complete environmental objective coefficients. Crosswalk, units, and system boundaries require independent two person review.

## Access and redistribution

These files are included for authorized collaboration in this private repository. Before making the repository public, review every source license and replace, remove, or externally archive any table that cannot be redistributed. Do not add personal data, credentials, or unreviewed raw source folders.
