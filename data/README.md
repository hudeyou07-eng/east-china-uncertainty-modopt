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

| File | Required content | Status |
|---|---|---|
| `group_audit.csv` | group ID, labels, sources, coverage, include decision and reason | frozen |
| `baseline_consumption.csv` | province, year, group ID, g per person per day and observed flag | frozen |
| `group_prices.csv` | province, year, group ID, CNY per kg and source; 多品类组按消费结构加权 | frozen |
| `nutrients.csv` | nutrient coefficients and defensible bounds per kg edible food; 多品类组按消费结构加权 | frozen |
| `environment.csv` | environmental coefficients, sources and harmonized boundaries; 品类内平均后按消费结构加权 | frozen |
| `decision_bounds.csv` | province and scenario specific lower and upper intake bounds; `bound_type` 区分单组与联合约束 | frozen |
| `model_manifest.json` | hashes, units, ontology version, weights version and timestamp | frozen |

组内权重来自 `data/input/external/meat_consumption_structure.csv`
（猪肉 0.788 / 牛肉 0.136 / 羊肉 0.076，国家统计局 2023 产量 + 海关总署 2023 进口，
表观消费份额），由 `src/component_weights.py` 统一加载并校验和为 1。
价格 / 营养 / 环境三个维度共用同一套权重。

另有两个随合同冻结的附属产物：`ontology.csv`（crosswalk 本体，`group_audit.csv` 的生成依据）
与 `group_audit_sensitivity_c0.90.csv`（预注册敏感性口径）。

`python scripts/build_contract_files.py` 重建全部冻结记录；
`python scripts/check_contract_gates.py` 单独复跑七条 gate 验收，输出 `contract_gate_report.json`。

Every included food group must have an identifiable consumption baseline, sufficient unit price coverage, complete hard nutrient coefficients, and complete environmental objective coefficients. Crosswalk, units, and system boundaries require independent two person review.

## Access and redistribution

These files are included for authorized collaboration in this private repository. Before making the repository public, review every source license and replace, remove, or externally archive any table that cannot be redistributed. Do not add personal data, credentials, or unreviewed raw source folders.
