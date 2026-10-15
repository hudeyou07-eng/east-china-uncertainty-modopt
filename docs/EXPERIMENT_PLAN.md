# Experiment Plan

**Problem:** 在华东区域价格、消费、营养和环境数据不完整且粒度错位的条件下，验证 uncertainty-propagating MODOpt 是否能产生营养可靠、方向稳定的食物组建议。
**Method thesis:** 后验预测场景与逐地区联合营养机会约束能够降低确定性填充造成的建议翻转，同时保留原有成本—环境多目标结构。
**Date:** 2026-10-15

## 1. Claim Map

| Claim | Why it matters | Minimum convincing evidence | Blocks |
|---|---|---|---|
| C1 数据层 | 结构化缺失下，输入不确定性必须经过校准，否则下游置信度没有意义 | 在伪缺失真值上，层级模型的点误差不劣于强基线，且 80%/95% 区间覆盖接近名义覆盖；硬约束违反率为 0 | B0, B1 |
| C2 决策层 | 论文主张不是插补更漂亮，而是建议更可靠 | 在遮蔽前真值上，机会约束 MODOpt 相比确定性均值填充显著提高联合营养可行率、降低方向翻转率和 95 分位 regret | B2, B3, B4 |
| Anti-claim | 改善不能只来自更保守的食物界、更大场景数或不同目标权重 | 冻结相同 (K\)、相同决策界和目标权重；通过无机会约束、场景数和权重消融隔离主机制 | B3 |

## 2. Paper Storyline

### Main paper must prove

1. 当前数据缺口与跨粒度错位会使确定性 MODOpt 的建议发生可测量的方向翻转。
2. 层级概率估计在真实缺失几何下提供校准的不确定性。
3. 联合营养机会约束在伪完整真值上提高营养可靠性，并保留稳定建议。
4. 稳定建议在七地区、三个原有膳食情景和预注册敏感性设置中可解释。

### Appendix can support

- 完整数据 provenance 与逐组审计表。
- 所有遮蔽重复、地区结果、收敛曲线和求解日志。
- 边界网格、MNAR shift、目标等权和原权重的敏感性结果。
- CHEI/ELDI 全部组成项。

### Intentionally cut

- 2050 本地长期预测与 MAgPIE 完整耦合。
- GAN/VAE/diffusion synthetic tabular data。
- 无真值支持的 68 食物条目级政策结论。
- CVaR、第二套稳健优化器和模型堆叠。

## 3. Frozen Data Contract

正式运行前必须生成并冻结以下文件：

| File | Required columns / arrays | Gate |
|---|---|---|
| `data/processed/group_audit.csv` | group_id, label, baseline_source, price_obs, price_regions, nutrient_coverage, environment_coverage, include, reason | 每个 include=1 的组通过全部覆盖规则 |
| `data/processed/baseline_consumption.csv` | province, year, group_id, value_g_day, observed | 无负值；主结论组有可识别基线 |
| `data/processed/group_prices.csv` | province, year, group_id, price_cny_kg, observed, source | 只有定义匹配的最终组单位价格 |
| `data/processed/nutrients.csv` | nutrient, group_id, value_per_kg, lower, upper, source | 所有硬营养素覆盖率 100% |
| `data/processed/environment.csv` | impact, group_id, value_per_kg, source, boundary | 所有主目标覆盖率 100%，系统边界统一 |
| `data/processed/decision_bounds.csv` | province, scenario, group_id, lower_g_day, upper_g_day | 有限、冻结、lower ≤ upper |
| `data/processed/model_manifest.json` | hashes, units, ontology_version, weights_version, timestamp | 与结果一起保存 |

任何 gate 未通过，正式 B2–B4 不启动；允许继续运行 B0/B1 数据诊断。

## 4. Experiment Blocks

### B0 — Data contract and solver sanity

- **Claim tested:** 实现忠实于 proposal，数据和求解器没有静默兜底。
- **Why:** 阻止随机值、零填充、单位错位和不可行模型进入正式实验。
- **Inputs:** 原始价格、消费、营养、环境文件；synthetic toy fixture。
- **Runs:** R000–R006。
- **Checks:**
  - provenance、单位、缺失率、重复键、非负性；
  - 食物组冻结与审计表；
  - 禁止 random fallback / `fillna(0)` / global mean fallback；
  - toy MILP 已知解、可行/不可行检测、Big-M 紧度；
  - 相同 seed 结果哈希一致。
- **Success criterion:** 全部测试通过；toy 解满足所有约束；同 seed 完全复现；错误输入明确失败。
- **Failure interpretation:** 工程或数据合同未闭合，禁止启动正式实验。
- **Target:** Appendix audit table + reproducibility checklist。
- **Priority:** MUST-RUN。

### B1 — Structured missingness calibration

- **Claim tested:** 层级概率估计在真实缺失几何下提供校准的不确定性。
- **Dataset:** 相对稠密的价格与消费子面板。
- **Split:** 5-fold outer validation；每折对三类缺失几何各 20 repeats：
  1. single-cell MCAR；
  2. consecutive-year block；
  3. province × food-group block。
- **Compared systems:**
  - B1a global/group mean；
  - B1b within-series linear interpolation；
  - B1c MICE/IterativeImputer；
  - B1d additive hierarchical/Bayesian ridge（main）。
- **Metrics:** scaled MAE、log-RMSE、80%/95% coverage、mean interval width、calibration error、negative/range violations、runtime。
- **Primary comparisons:** B1d vs strongest of B1b/B1c using paired repeats；report effect size and bootstrap CI。
- **Success criterion:** main method has no constraint violations；95% coverage within 90–98% and 80% coverage within 74–86%，or materially better calibration than all baselines at comparable interval width；point error remains competitive。
- **Failure interpretation:**
  - point error poor + coverage good → simplify mean structure or shrinkage；
  - point error good + undercoverage → variance model inadequate；
  - block extrapolation fails → move block to partial-identification sensitivity, do not probabilistically impute。
- **Target:** Main Table 1, calibration figure, appendix per-mask results。
- **Priority:** MUST-RUN。

### B2 — Main decision reliability

- **Claim tested:** uncertainty-propagating MODOpt improves true downstream reliability.
- **Dataset:** pseudo-complete subpanels with ground truth retained before masking。
- **Protocol:** same 5 folds × 20 repeats × 3 missing geometries；for each repeat run mask → fit → scenario generation → solve → evaluate on pre-mask truth。
- **Compared systems:**
  - D0 mean-fill deterministic MODOpt；
  - D1 posterior-mean deterministic MODOpt；
  - D2 posterior-scenario expected-objective MODOpt without chance constraint；
  - D3 posterior-scenario MODOpt + joint nutrition chance constraint（main）。
- **Frozen controls:** same (K\)、decision bounds、objective weights、scenario definitions and post-hoc CHEI/ELDI implementation。
- **Primary metrics:** joint nutrient feasibility on truth、direction flip rate、95th-percentile regret。
- **Secondary:** mean regret、cost/environment distributions、CHEI、ELDI、solver status/runtime/MIP gap。
- **Success criterion:** D3 has the highest or statistically tied-highest true joint feasibility and materially lower flip rate than D0；95th regret does not worsen beyond a predeclared practical margin of 5% relative to D2。
- **Failure interpretation:**
  - feasibility unchanged → chance mechanism unnecessary or uncertainty too small；
  - feasibility improves but regret explodes → epsilon/bounds overly conservative；
  - flips remain high → data do not identify direction; report as data-sensitive rather than force conclusion。
- **Target:** Main Table 2 + main stable/flip figure。
- **Priority:** MUST-RUN。

### B3 — Mechanism isolation and simplicity

- **Claim tested:** gains come from propagating uncertainty into nutrition constraints, not unrelated settings。
- **Ablations:**
  - A1 no chance constraint（D2）；
  - A2 independent nutrient-wise chance indicators instead of joint indicator；
  - A3 fixed global Big-M（diagnostic only, must not be used in final method）；
  - A4 train scenarios 50/100/200/500；
  - A5 epsilon 0/0.02/0.05/0.10；
  - A6 original objective weights vs equal weights；
  - A7 no posterior (W\) uncertainty；
  - A8 remove MNAR shift / boundary sensitivity from conclusion gate。
- **Metrics:** feasibility, flip rate, p95 regret, solution stability, runtime, MIP gap。
- **Success criterion:** D3 advantage persists across reasonable scenario counts and weights；200 scenarios are on the stability plateau；joint constraint adds reliability beyond D2 without unacceptable regret。
- **Failure interpretation:** retain the simplest variant supported by evidence; do not protect a component that adds no decision value。
- **Target:** Main ablation table (A1, A4, A5); remaining plots in appendix。
- **Priority:** A1/A4/A5 MUST-RUN；others NICE-TO-HAVE after B2 succeeds。

### B4 — Regional and scenario robustness

- **Claim tested:** stable directions reflect traceable regional structure and survive predeclared sensitivity settings。
- **Scope:** seven regions × HEAL_base/CDG/EAT。
- **Sensitivity layers:** leave-one-region-out fit；
  (delta=-0.5,0,+0.5\) residual SD；boundary low/mid/high/worst endpoints；original/equal weights。
- **Metrics:** stable-up/down/data-sensitive label, direction agreement, regional heterogeneity, feasibility, regret, CHEI/ELDI。
- **Conclusion gate:** a group enters the main conclusion only when test direction agreement ≥90%, unchanged across delta and boundary grid, and test feasibility point estimate ≥95% with Wilson 95% CI reported。
- **Target:** Main Figure 2 regional stability heatmap; appendix province scenario panels。
- **Priority:** MUST-RUN for conclusion gate；full visualization polish NICE-TO-HAVE。

## 5. Statistical Analysis Protocol

- Use paired comparisons because every method sees the same mask/repeat。
- Report mean, median, standard deviation, bootstrap 95% CI and paired effect difference。
- For feasibility proportions, report Wilson intervals。
- Do not use p-values alone; state practical margins。
- Correct the family of primary comparisons (D3 vs D0/D1/D2) using Holm adjustment if hypothesis tests are reported。
- Never select hyperparameters on (S_{test}\) or pre-mask truth used for final evaluation。
- Freeze thresholds, masks, seeds, ontology and model-manifest hashes before B2。

## 6. Run Order and Milestones

| Milestone | Goal | Runs | Decision gate | Cost | Main risk |
|---|---|---|---|---|---|
| M0 | code/data sanity | R000–R006 | all tests pass | <30 min CPU | data paths and units |
| M1 | estimate calibration | R100–R112 | coverage/error gate | 1–4 h CPU | dense panel too small |
| M2 | main decision result | R200–R203 | D3 improves feasibility/flip | 4–12 h CPU | MILP runtime |
| M3 | decisive ablations | R300–R307 | 200 scenarios stable; epsilon justified | 4–16 h CPU | combinatorial expansion |
| M4 | seven-region story | R400–R423 | conclusion gate labels available | 8–24 h CPU | some regions non-identifiable |
| M5 | figures and tables | R500–R505 | all paper artifacts reproducible | 1–3 h CPU | inconsistent cached results |

## 7. Compute and Data Budget

- **GPU:** none required。
- **CPU:** 8–16 cores recommended；MILP runs can parallelize by region/scenario/repeat。
- **RAM:** 16 GB minimum, 32 GB recommended。
- **Storage:** <10 GB including scenario arrays and logs。
- **Human review:** two-person verification of crosswalk, units and group audit。
- **Biggest bottleneck:** trustworthy final-group construction, not raw compute。

## 8. Stop / Go Rules

- **STOP before B1:** duplicate keys, invalid units, unresolved group definition, or silent fallback found。
- **STOP before B2:** hard-nutrient/environment coverage below 100% for included groups。
- **GO from B1 to B2:** at least one probabilistic method passes calibration gate for the tested missingness type。
- **NARROW scope:** a block missingness type that fails calibration becomes partial-identification sensitivity only。
- **GO to B3/B4:** B2 main run completes with valid solver status and ground-truth evaluation。
- **CUT component:** an ablation shows no reliability benefit across paired repeats。

## 9. Reproducibility Requirements

- Every run has `run_id`, seed, git/code hash, data manifest hash, config snapshot and command line。
- Save metrics to JSON and row-level results to CSV/Parquet。
- Save masks so all methods share identical held-out cells。
- Never overwrite run directories; use timestamped run IDs。
- A run is complete only when `metrics.json`, `config.json`, `environment.json` and `DONE` exist。
- Failed/infeasible runs retain logs and write `FAILED.json`。

## 10. Final Checklist

- [ ] Main-paper tables are covered by B1 and B2。
- [ ] Novelty is isolated by B3。
- [ ] Simplicity is defended; no extra model is added without evidence。
- [ ] No frontier-model contribution is claimed or forced。
- [ ] Must-run and nice-to-have experiments are separated。
- [ ] Every policy direction passes the pre-registered conclusion gate。
- [ ] Existing demo/random results are excluded from all formal tables。
