# East China Uncertainty Aware MODOpt

本仓库研究在价格、消费、营养和环境数据不完整且粒度错位时，如何生成营养可靠、方向稳定、可以审计的华东地区膳食优化建议。

This repository studies how to produce nutritionally reliable, directionally stable, and auditable dietary optimization recommendations for East China when price, consumption, nutrient, and environmental data are incomplete or mismatched in granularity.

## Research question

哪些食物组调整方向在合理的数据补全、缺失机制和参数边界下仍然不会翻转？

Which food group adjustment directions remain unchanged across defensible data completion assumptions, missingness mechanisms, and parameter bounds?

## Current status

| Block | Status | Meaning |
|---|---|---|
| B0 data and solver checks | Implemented and smoke tested | 数据审计、失败保护和 synthetic MILP 链路已验证 |
| B1 structured missingness calibration | Implemented, formal run pending | 可正式运行 5 folds × 20 repeats |
| Food group crosswalk | Pending two person review | 未冻结前不得启动正式 B2 to B4 |
| B2 to B4 real MODOpt | Solver core only | 真实数据接口等待 processed data contract |

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
├── outputs/                 # Generated runs, ignored by Git
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
```

All tests must pass before a formal run.

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

- `docs/Research_Proposal.docx`: reviewed Chinese and English research proposal.
- `docs/EXPERIMENT_PLAN.md`: claim driven full experiment plan.
- `docs/EXPERIMENT_TRACKER.md`: run level tracker.

## Reproducibility policy

- Freeze masks, seeds, ontology, units, thresholds, and config before B2.
- Every run records input hash, source tree hash, environment, config, and run ID.
- Never use random fallback, zero fill, or undocumented global means in formal results.
- Never overwrite completed run directories.
- Keep smoke evidence separate from paper results.

## Collaboration

Use feature branches such as `feature/formal-calibration` and `data/group-crosswalk`. Keep `main` runnable. Every pull request should state the claim or gate it supports and include the test command used.
