# Data dictionary

| File | Role | Main fields or sheets | Current use |
|---|---|---|---|
| `price/price_panel_clean.xlsx` | Auditable annual price panel | province, category, year, annual mean, unit, data nature, source cell | B0 audit and B1 calibration |
| `price/price_category_catalog.xlsx` | Complete category catalogue and source trace | province sheets with category rows and annual source cells | Restores the full 14 category grid |
| `clean_tables/consumption.csv` | Regional food consumption | region, year, food group, consumption value and unit | Baseline contract preparation |
| `clean_tables/consumption_coverage.csv` | Consumption coverage summary | region and coverage statistics | Coverage gate |
| `clean_tables/food_crosswalk.csv` | Food ontology mapping | source category and harmonized food group | Crosswalk review |
| `clean_tables/prices.csv` | Harmonized price table | region, year, food group, price and unit | B2 input preparation |
| `clean_tables/price_summary.csv` | Price QA summary | coverage and validation summaries | Data audit |
| `clean_tables/nutrition.csv` | Nutrient composition | food group, nutrient, value and unit | Nutrient coefficient preparation |
| `clean_tables/china_lca.csv` | China LCA records | food, study/source and environmental indicators | Environmental coefficient preparation |
| `clean_tables/lca_summary.csv` | LCA QA summary | record and coverage counts | Data audit |
| `clean_tables/global_environment.csv` | Global environmental factors | food and harmonized impact indicators | Boundary sensitivity preparation |
| `workbook/diet_model_clean_data.xlsx` | Consolidated reviewed workbook | clean tables, dictionaries, QA and transformation log | Human review and handoff |

Formal processed schemas and gates are defined in `docs/EXPERIMENT_PLAN.md`.
