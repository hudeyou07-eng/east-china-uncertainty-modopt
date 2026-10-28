# East China Uncertainty Aware MODOpt

本仓库研究在价格、消费、营养和环境数据不完整且粒度错位时，如何生成营养可靠、方向稳定、可以审计的华东地区膳食优化建议。

This repository studies how to produce nutritionally reliable, directionally stable, and auditable dietary optimization recommendations for East China when price, consumption, nutrient, and environmental data are incomplete or mismatched in granularity.

## Research question

哪些食物组调整方向在合理的数据补全、缺失机制和参数边界下仍然不会翻转？

Which food group adjustment directions remain unchanged across defensible data completion assumptions, missingness mechanisms, and parameter bounds?

## Current status

> 快照日期 **2026-10-28**。逐 run 状态见 `docs/EXPERIMENT_TRACKER.md`，全部重要改动汇总见 `docs/PROJECT_SUMMARY.md`。

| Block | Status | Meaning |
|---|---|---|
| B0 data and solver checks | Implemented and smoke tested | 数据审计、失败保护和 synthetic MILP 链路已验证；R003 手工可验算 LP fixture 已补（`tests/test_lp_fixture.py`） |
| B1 structured missingness calibration | **Done (both panels)** | 价格面板 `B1_formal_withmice_20261023_124906`（1200 行）；消费面板 `R103_105_consumption_formal_20261026_174725`（1200 行）；MAR/MNAR 敏感性 `R108_109_price_formal_20261026_175443` |
| Food group crosswalk | Frozen at `onto-v1.0.0` | **决策口径 `k6_price`（K=6，6 省，上海因缺 G07 出局）**；合同口径仍 K=4，K=3 仅作偏离对照 |
| B2 decision reliability | **Done-conditional** | `R200_203_b2_formal_20261027_222841`（EAR）/ `_224315`（RNI）；EAR 下 D0≡D1≡D3，是**干净零结果**。已按 `DONE-conditional` 定稿，放行条件（口径披露）见 tracker 同名小节 |
| B3 / B4 | Not started | M3 敏感性只跑了 smoke + 8 个单点；B4 未开工 |

关键口径（作者 2026-10-27 裁定）：`optimization.decision_scope: k6_price`、
`optimization.bounds_basis: ear`（钙 650 / 铁 12 / 锌 8.25 / 硒 50 / 硫胺素 1.1 / 核黄素 1.1 / 烟酸 11）、
`optimization.cv_nutrient: 0.0`（食物成分表是物理常数，只扰动价格）。

合同闭合方式：`python scripts/build_contract_files.py` 一条命令完成
「重建审计表 → 汇总 7 个产物 hash → 跑 §3 七条 gate → 回写 manifest → 落 R002 run 目录」。
run 目录自包含 `metrics.json` / `config.json` / `environment.json` / `DONE` / `contract_gate_report.json`。

三处口径决策仍需人工复核（详见 `docs/EXPERIMENT_TRACKER.md` 末节）：
G06 组内权重来源、痕量格决定红肉去留、决策边界用联合约束而非硬拆指南类别。

价格 / 营养 / 环境三个维度的组内权重已统一为**消费结构加权**
（猪肉 0.788 / 牛肉 0.136 / 羊肉 0.076，表观消费份额，来源见
`data/input/external/meat_consumption_structure.csv`），由 `src/component_weights.py` 统一提供。
等权并不中性：它等价于假设"中国人吃的红肉有三分之二是牛羊肉"，
会把红肉成本高估 19%、排放高估 45%，同时把能量与脂肪低估 42% / 67%。

价格源：主分析使用零售价面板 `data/input/price/price_panel_clean.xlsx`（元/500g）。
商务预报批发价（元/公斤）不在主分析中使用，登记于
`data/processed/model_manifest.json` 的 `alternative_sources`，计划用于 B4 的价格口径敏感性检验。

Smoke results prove that the software path runs. They are not paper evidence. The optimization smoke test uses a synthetic fixture and must not be reported as a substantive research result.

## Repository structure

```text
.
├── README.md
├── requirements.txt
├── run_experiments.py
├── configs/                 # Frozen experiment configuration
├── src/                     # Audit, masking, imputation, metrics, MILP
├── tests/                   # Automated smoke and edge case tests
├── docs/                    # Bilingual proposal and experiment protocol
├── data/                    # Versioned reproducibility inputs and processed contract
├── artifacts/smoke/         # Small reviewed smoke evidence only
├── outputs/                 # All 44 run directories, versioned so results are auditable
└── scripts/                 # Reproducible document or utility builders
```

## Setup

Python 3.10 to 3.12 is recommended. No GPU is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Test

```powershell
python -m unittest tests.test_smoke -v
python scripts/check_tracker.py          # 文档与磁盘产物的一致性门禁（15 项）
python scripts/verify_tracker_numbers.py # 关键数字对回产物（27 项断言）
```

All tests must pass before a formal run. The tracker check must pass before a run is
cited in the paper: it verifies that every run directory the tracker references exists,
that every `outputs/` directory is indexed, and that the progress totals match the
per-run status column. `verify_tracker_numbers.py` re-derives 27 key numbers from the
run artifacts and asserts they appear verbatim in the ledger.

## Run order

### 1 Data audit

```powershell
python run_experiments.py audit --run-id R001_price_audit
```

### 2 Minimal workflow check

```powershell
python run_experiments.py all-smoke --profile smoke --run-id M0_all_smoke
```

### 3 Formal B1 calibration

```powershell
python run_experiments.py calibration --profile formal --run-id R100_109_formal
```

A completed run contains `metrics.json`, `config.json`, `environment.json`, and `DONE`. A failed run is retained with `FAILED.json` and must not be silently deleted.

## Data access

The repository includes the minimum cleaned input bundle required for team reproduction. The default configuration uses repository-local relative paths, so audit and calibration can run after clone without the original `student_doc/` directory. Raw source folders, personal material, and redundant intermediate files remain excluded.

Formal B2 to B4 experiments require all processed files listed in `data/README.md` to pass their coverage and unit gates.

## Main documents

Start here: **[`docs/PROJECT_SUMMARY.md`](docs/PROJECT_SUMMARY.md)** — the single consolidated entry
point (results, key decisions, limitations, reproduction, change digest).

- `docs/README.md`: the documentation map (what to read, what is archived, verification commands).
- `docs/PROJECT_SUMMARY.md`: **consolidated summary of all substantive changes** (2026-10-23 → 10-28).
- `docs/EXPERIMENT_PLAN.md`: claim driven full experiment plan, with four pre-registration revisions.
- `docs/EXPERIMENT_TRACKER.md`: the single run-level ledger (46 runs, artifact index, and the five
  interpretation traps). Figure 1 and Figure 2 are English-labelled SVG.
- `docs/CHANGELOG_2026-10-26.md`: the round-by-round evidence chain (§1–§38), cited by section number.
- `docs/PANEL_LEDGER.md`: price panel v1/v2/v3 version ledger.
- `docs/Research_Proposal.docx`: reviewed Chinese and English research proposal.
- `docs/archive/`: historical audit, decision log, cleanup ledger and the resolved decision page
  (kept because the changelog still cites them by file name).

## Reproducibility policy

- Freeze masks, seeds, ontology, units, thresholds, and config before B2.
- Every run records input hash, source tree hash, environment, config, and run ID.
- Never use random fallback, zero fill, or undocumented global means in formal results.
- Never overwrite completed run directories.
- Keep smoke evidence separate from paper results.

## Collaboration

Use feature branches such as `feature/formal-calibration` and `data/group-crosswalk`. Keep `main` runnable. Every pull request should state the claim or gate it supports and include the test command used.
