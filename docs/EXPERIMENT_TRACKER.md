# Experiment Tracker

> **英文版**（同一份 46-run 账本的英文结案版，含产物索引与五条解读陷阱）：
> `docs/EXPERIMENT_TRACKER_EN.md`。图 1 / 图 2 现为英文标注。
> 两个版本由同一套门禁校验：`check_tracker.py [--file ...]` + `verify_tracker_numbers.py`。

| Run ID | Milestone | Purpose | Variant | Split / scope | Primary metrics | Priority | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| R000 | M0 | environment check | dependency/version | local | imports, solver availability | MUST | DONE | five automated tests passed in the cloned repository |
| R001 | M0 | raw data audit | provenance/units/missing | all raw files | audit errors/warnings | MUST | DONE | 7 regions, 14 groups, 882 cells; 294 truth-eligible observations |
| R002 | M0 | food-group freeze | ontology/crosswalk | all groups | included K, rank, coverage | MUST | DONE | ontology 统一到 `src/ontology.py` (onto-v1.0.0)；**合同文件 K=4**（G02/G05/G06/G08，痕量按近零，Plan 修订 R-2026-10-26-b），原 K=3 保留为 `group_audit_k3_strict.csv`；**决策口径 `k6_price` K=6**（+G04 +G07，`group_audit_trace_c0.95.csv`，见 CHANGELOG §20/§21）；**合同 7/7 齐备且 7/7 gate 通过**；G06 三维度已统一为消费结构加权（猪 0.788/牛 0.136/羊 0.076）；`manifest.decision_scope` 记录 K/组集合/可用省 6/跳过省（上海缺 G07）/联合约束核对 6-6 applied；hash 见 `data/processed/model_manifest.json`；**run 引用 `outputs/R002_group_freeze_20261027_232440`**（面板 v3、`group_prices` hash `3b7ae42d…` 与磁盘一致、gate 7/7）；`outputs/R002_group_freeze_20261027_150751` 是**面板 v1**（`54f7fee0…`，G06 未修）的同一重建，只留档，**其 gate 报告不得引用**——本表 G3 的 `collapsed 0%` / `7/28` / `13/36` 三个数只能来自 `_232440` |
| R003 | M0 | deterministic toy | known LP solution | synthetic toy | objective, feasibility | MUST | DONE | `tests/test_lp_fixture.py` 5 个测试：内点最优 (3,2)/成本 9 手算吻合、两约束同时紧、上界紧 (2.5,3)/成本 11.5、不可行必须 `success=False`、`use_chance_constraint=False` 钉住「等于无营养约束」的语义 |
| R004 | M0 | chance MILP toy | joint indicator | synthetic toy | feasibility, z count | MUST | DONE | optimal result; z count respects epsilon budget |
| R005 | M0 | reproducibility | same seed twice | synthetic toy | result hash | MUST | DONE | 2026-10-26 复验：seed=7 / 20 scenarios 连跑两次，`q` 与 `objective` 的 sha256 均为 `ab9e5ed14ce2ad36`，objective 0.131221215416、q_sum 69.713256651395 完全一致 |
| R006 | M0 | invalid input | negative/unit/missing coeff | synthetic bad fixtures | explicit failure | MUST | DONE | invalid bounds and non-finite coefficients fail loudly |
| R100 | M1 | price MCAR | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | DONE | run: `outputs/B1_formal_withmice_20261023_124906`；1200 行结果，duplicate_rows=0，5 folds × 20 repeats 全覆盖 |
| R101 | M1 | price year-block | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | DONE | 同上 run；mask_type=consecutive_years |
| R102 | M1 | price province×group | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | DONE | 同上 run；MICE 在此几何下崩溃（sMAE 1.182，cov95 0.733）。**更正**：interp 与 group_mean 在此遮蔽下预测**逐格完全相同**（1200/1200 差值<1e-9），故 interp 的欠覆盖实为「组均值欠覆盖」，不能读作「插值方法差」 |
| R103 | M1 | consumption MCAR | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | DONE | run: `outputs/R103_105_consumption_formal_20261026_174725`（20 分片并行，377s）。single_cell n=1300：sMAE MICE **0.036** < interp 0.047 < group_mean 0.138 < hierarchical_rw 0.147；但**标定误差 hierarchical_rw 0.009 最低**（slope 0.990），MICE 0.050、interp 0.075。**注意：消费面板零缺失，此为可恢复性测试，不反映真实缺失机制** |
| R104 | M1 | consumption year-block | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | DONE | 同 run，consecutive_years n=200：sMAE interp **0.056** ≈ MICE 0.059 < group_mean 0.123 ≈ hierarchical_rw 0.137；标定误差 hierarchical_rw **0.034** 最低，但 slope 0.822、cov50 0.590 偏低 |
| R105 | M1 | consumption province×group | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | DONE | 同 run，province_group n=900：**MICE 完全崩溃**（sMAE 1.000，cov95 **0.079**，标定误差 0.736）；interp cov95 0.691 **但 interp 在此遮蔽下与 group_mean 逐格同值**（见 R102 更正），故该数实为组均值的欠覆盖；group_mean 0.149 / hierarchical_rw 0.181 但 cov95 0.918/0.900 最接近名义值。与价格面板 R102 的崩溃模式一致 |
| R106 | M1 | interval calibration | main | aggregate | coverage-width curve | MUST | DONE | 价格面板：`scripts/coverage_curve.py` 由 `B1_formal_withmice_20261023_124906/cell_predictions.csv` 事后重算（不重跑），产出 `coverage_curve.csv` / `coverage_curve_summary.csv` / `coverage_curve_by_fold.csv`。**hierarchical_rw 标定误差最低**（0.054/0.037/0.059，三种遮蔽）；MICE 在 province_group 上 0.262 且 slope 1.18（过度自信）。coverage_slope 全域 <1（0.39–1.18），区间整体偏宽 |
| R107 | M1 | interaction gate | main ± region×group | all masks | paired error/coverage | NICE | DONE | `scripts/interaction_gate.py` 只读复算既有扫描产物，结论落盘于 `outputs/R107_interaction_gate/`。**「both improve」不成立**：`ir10_k1` 在 consecutive_years（−10.3%/−14.3%）与 single_cell（−7.7%/−7.3%）一致改善，但 province_group 轻微退化（+0.6%/+1.7%），严格门控（三掩码全 <1）不通过。机制上说得通：整块缺失时该省该组零观测，交互项无从估计。源 run 仍标 INCOMPLETE，故结论只引用本复算 |
| R108 | M1 | MAR sensitivity | main | all masks | calibration | MUST | DONE | `outputs/R108_109_price_formal_20261026_175443`（5×20，5493s）。**12 个 (遮蔽×方法) 组合的 bias_slope 全为负**（−0.188 ~ −0.991）→ 高值系统性低估；主方法 single_cell slope −0.455 比 interpolation −0.188 **更差**。Q5 平均低估 8.66 元/kg（11%）。**cov95 好 ≠ 无偏** |
| R109 | M1 | MNAR shift | delta grid | blocks | error/coverage | MUST | DONE | 同 run。δ=0 处主方法 cov95 **0.940/0.955/0.954**（三种遮蔽，与名义 0.95 差 ≤1pp）；δ=+0.5 降到 0.925–0.937，δ=−0.5 升到 0.955–0.980。**排序稳定性：主方法在全部 9 个 (遮蔽×δ) 格子均为第 1 名**。smoke 曾出现的「consecutive_years δ=0 时 group_mean 更优」正式批次未复现，该观察作废 |
| R200 | M2 | deterministic baseline | D0 mean-fill | 100 协议单元 × 6 省 | feasibility, flips, p95 regret | MUST | DONE-conditional | **2026-10-28 定稿（§33）**：条件=论文数据节必须写入 §32.5 的三条边界披露；指标与产物一律不变。**2026-10-27 第十轮已接线**：场景=B1 经验残差、重复=B1 遮蔽协议。正式批次 `R200_203_b2_formal_20261027_170542`（EAR，2400 行）与 `..._171718`（RNI 对照）。**EAR 下 D0 \|Δq\| 精确 0.000**（≡D1≡D3）；RNI 下 38.771。旧路径回归验证 diff 全 0。见 CHANGELOG §25。**归因已更正**：EAR 下 D0≡D1 不是因为扰动小，而是顶点稳到连 65% 的合并价差都推不动（§25.9 / §26）。**主指标已换**（§27，预注册偏离已声明）：`\|Δq\|` 变化率 EAR **0.000** / RNI **0.498**（p95 110.97 g/day），`flips` 降为辅助。**第十六轮按修正后价格面板重跑**：EAR `..._222841` / RNI `..._224315`。EAR 下决策列变化 **9.8e-08 g/day**、成本 +0.197%（中位），ghg/land 全 0（§31.3）。**RNI 下 D0 变了 50–111 g/day，查出 D0 是二值开关**（`q_G08` 每省只有 2 个取值、间距为 6 个固定常数；EAR 下只有 1 个取值且跨面板不变）。因此 **D0 变化率 0.498 → 0.460、「D0≠D1 的省份」从安徽/山东/浙江换成江苏/江西/福建**——这个名单是开关读数，**不可引用**。见 §31.8 与 `DIAG_d0_bistability_20261027_231703`。**面板版本注意**：这两个批次记录的是面板 v2 的 hash，当前磁盘是 v3——v2→v3 **价格 0 行变化**（只改 `truth_eligible` 标记），批次继续有效，台账见 `docs/PANEL_LEDGER.md` 与 §32.8 |
| R201 | M2 | posterior mean | D1 | 100 协议单元 × 6 省 | feasibility, flips, p95 regret | MUST | DONE-conditional | 同上（条件见 R200）。**EAR 下 D1 在 100 个单元间逐位不变**（逐组 sd 全 0.0000，`\|Δq\|` 0.000）；RNI 下 3/6 省出现两个顶点（安徽 8.40 / 山东 19.02 / 浙江 10.54 g/day）。协议位移均值仅 0.298%，**远小于顶点稳定半径（EAR 中位 50%、最小 2%）**；但注意 D0↔D1 的价差是 15–65%，不是 0.298%——见 §25.9 更正二与 §26.6。**主指标**：变化率 EAR **0.000** / RNI **0.013**（p95 0.00），即 D1 基本钉在正确顶点。**第十六轮补充**：RNI 下 D1 的 `q_G08` 在安徽/山东/浙江也有 2 个取值（97/3 分布），但该分布**跨面板完全不变**——与 D0 的 98/2→73/27 形成对照（§31.8） |
| R202 | M2 | scenario expected | D2 | 100 协议单元 × 6 省 | feasibility, flips, p95 regret | MUST | DONE-conditional | 同上（条件见 R200）；D2 无营养约束，是**唯一**与其它方法不同的：`\|Δq\|` 128.65、gap −0.80、翻转率 0.194（两口径一致）。红肉被压到 0，符合预期语义 |
| R203 | M2 | proposed method | D3 | 100 协议单元 × 6 省 | feasibility, flips, p95 regret | MUST | DONE-conditional | 同上（条件见 R200）。**EAR 下 D3 ≡ D1**（`\|Δq\|` 0.000，与 §24.1 的结构性零传导一致）；RNI 下 `\|Δq\|` 10.906、翻转率 0.028。营养系数按裁定不扰动，故机会约束在价格场景下退化为硬约束。**主指标**：变化率 EAR **0.000** / RNI **0.333**（p95 36.41）；偏离集中在江西（29.03）、福建（36.41），变化率均为 1.00 |
| R300 | M3 | chance deletion | D3→D2 | primary setting | delta metrics | MUST | DONE | `outputs/M3_all_smoke_20261026_181618`。D3 可行(活跃) **100%** / D2 **0%**；D2 gap **−0.715**（靠违规套利），D3 +0.123。机会约束净贡献=可行率 0→100%，代价是 17% 实例（江苏）无解。**plumbing_only** |
| R301 | M3 | scenario count | 25/50/100/200/400 | primary setting | stability/runtime | MUST | DONE | 同 run。可行率 **S=25 起就恒定 83%**（推翻「S 过小导致江苏失败」的旧假设）；耗时 0.04→20.15 s（S 增 16 倍、时间增 500 倍）。**S=200 是拐点**。网格由 50/100/200/500 改为 25/50/100/200/400（500 已无必要，25 用于验证平台起点） |
| R302 | M3 | epsilon | 0/.02/.05/.10 | primary setting | feasibility/regret | MUST | DONE | 同 run。求解成功率 56%→72%→**83%→83%**（0.05 后饱和）；翻转率 0.60→0.20；gap 0.190→0.099。方向单调，与噪声结构无关，可采信。江苏需 ε≈0.30 才可行（硒余量仅 6.0%，9 营养素联合违反复合） |
| R303 | M3 | objective weights | original/equal | primary setting | direction stability | MUST | DONE | 同 run。可行率 83%/83% 不变，gap 0.123/0.128，最大 \|Δq\| **18.23 g/day**（上海），安徽/浙江为 0。方向稳定，无「按结果挑权重」风险 |
| R304 | M3 | W uncertainty | on/off | primary setting | flips/regret | NICE | DONE | `outputs/R304_weight_uncertainty_20261027_143003`。权重 `Dirichlet(κ·w0)`，每省每档 200 抽。κ=20（成本权重 SD≈6pp）平均遗憾 **0.06%**、翻转率 1.2%；κ=5（SD≈20pp）平均 0.28%、翻转 4.3%。**权重不是主要不确定性来源**；例外浙江（κ=5 下最大遗憾 15.0%、翻转 23.5%） |
| R305 | M3 | joint vs marginal | joint/independent z | primary setting | joint feasibility | NICE | DONE | `R305_chance_mode_20261027_142626` + `R305_high_eps_20261027_143744`。**joint 实测联合违反率精确等于 ε**（5 点全中，公式可信）；marginal 是 ε 的 1.5–1.8 倍（理论上界 9ε，实测远低=违反场景高度重叠）。江苏 joint 需 ε=0.30 / marginal 需 0.20 → **根因是营养余量不足，不是联合性**（修正 §15.2）。marginal 有 1800 个二元变量，ε=0.30 平均 117 s，**算不动** |
| R306 | M3 | Big-M diagnostic | tight/global | toy only | gap/runtime | NICE | DONE | `outputs/R306_big_m_20261026_181747`。先自检 M 跨度 2.4–2.6 倍（对照有效），再比：**解逐位相同 Δq=0，耗时差<2%**。诚实结论=toy 规模上 tight 无性能收益，保留作防御性默认值 |
| R307 | M3 | boundary gate | on/off | primary setting | conclusion labels | NICE | DONE | `outputs/R307_gate_20261027_142902`（影子目录装配，正式门未动）。放宽到覆盖率 0.90 → K=6（+G04 谷物豆类、+G07 水产品）。**三项连锁后果**：①价格传导从 0/6 省恢复为 3/6 省（江苏 54.0 g）；②**山东由硬不可行变可行**（碳水 offset 275.75→39.55）；③上海因缺 G07 出局。共同组位移 39.5–171.6 g（蔬菜最大）→ **蔬菜量与红肉分配是 K 值依赖的**。**归因已由 R307b 更正**：价格传导恢复是 G07 的功劳，不是「K 变大」 |
| R307b | M3 | gate factorial | 2×2: trace × coverage | primary setting | attribution | NICE | DONE | `outputs/R307b_gate_factorial_20261027_145412`。四口径 A/B/C/D。**因子分解结论**：G04 → 解决山东硬不可行（碳水 offset 275.75→39.55）；**G07 → 恢复价格传导（0/7→3/6）**；两者都与 K 大小无关（D 的 K=5 仍是 0/7）。另发现营养门在 c=1.0 处**判据切换**（全或无 vs 平均比例），现有阈值敏感性表不能读作阈值敏感性 |
| R400 | M4 | Jiangsu scenarios | D3/D1 方向标签 | 6 省 × 3 情景（合并批次） | 方向标签、agreement | MUST | DONE | **R400/R402–R406 合并为一个批次** `outputs/R400_406_provinces_20261028_183104`：18 格中 15 格可解、3 格 EAT 硬不可行（山东/江苏/浙江，冲突集「碳水化合物+硫胺素」）。**一致率均值 0.956**；90 个组格标签 = up 36 / down 49 / neutral 1 / **data-sensitive 4**。江苏三格 agreement 均为 **1.000** |
| R401 | M4 | Shanghai availability (redefined) | data audit, no solve | 上海 × 12 组 × 9 年 | coverage, scope gap | MUST | DONE | **2026-10-28 改性质（修订 `R-2026-10-28-c`，方案 B）**：上海在 `k6_price` 下缺 G07 且**不可桥接**（桥接表 9 品类无水产品），不进入决策层，改为数据可得性报告。结论：`k6_price` **不可装配**、`k4_official` **可装配**（G02 3 年 / G05 1 年 / G06 7 年 / G08 3 年），后者只作附录单点、**不得与 K=6 并列**。另登记一条易误用记录：`clean_tables/prices.csv` 的上海水产 30.26 元/kg（P023）**无年份字段**，不可用。run: `outputs/R401_shanghai_availability_20261028_180508` |
| R402 | M4 | Zhejiang scenarios | D3/D1 方向标签 | 3 情景 | 方向标签 | MUST | DONE | 同批次 `R400_406_provinces_20261028_183104`。浙江：HEAL_base **1.000** / CDG **1.000** / EAT **硬不可行**（碳水化合物+硫胺素） |
| R403 | M4 | Shandong scenarios | D3/D1 方向标签 | 3 情景 | 方向标签 | MUST | DONE | 同批次。山东：HEAL_base **1.000** / CDG **1.000** / EAT **硬不可行** |
| R404 | M4 | Anhui scenarios | D3/D1 方向标签 | 3 情景 | 方向标签 | MUST | DONE | 同批次。安徽：HEAL_base **1.000** / CDG **1.000** / **EAT 0.667（低于 90% 门）**；两个 data-sensitive 组是 G07（+8.17 vs −35.30）与 G08（−39.25 vs +302.47），均出现在 EAT |
| R405 | M4 | Jiangxi scenarios | D3/D1 方向标签 | 3 情景 | 方向标签 | MUST | DONE | 同批次。江西：HEAL_base **1.000** / CDG **1.000** / **EAT 0.667（低于 90% 门）**；data-sensitive 同为 G07、G08，形态与安徽一致 |
| R406 | M4 | Fujian scenarios | D3/D1 方向标签 | 3 情景 | 方向标签 | MUST | DONE | 同批次。福建：三情景 agreement 全为 **1.000** |
| R407 | M4 | leave-one-province-out | D0 池化价留一 | 6 fold × 5 省 × 3 情景 | `max\|Δq\|`、方向改变数 | MUST | DONE | `outputs/R407_looro_20261028_183054`。**75 格全部可解，6 格发生方向变化**（78 格 `max\|Δq\|` = 0）。6 格全部落在 **EAT**、省份为安徽/江西/福建、被移除的 fold 为**山东/浙江**，位移 **339.3–341.7 g/day**，牵动 G04/G06/G07/G08。**解读**：留一改变的是池化价（最大 15.7%–24.1%），CDG/HEAL_base 纹丝不动、EAT 局部翻转——与 §26「EAT 顶点稳定半径仅 0.5–1.0°」一致，不能读作「留一不稳健」 |
| R408 | M4 | delta sensitivity | δ 乘性残差对数域 | δ ∈ {−0.5,0,+0.5} × 6 省 × 3 情景 | `max\|Δq\|` vs δ=0 | MUST | DONE | `outputs/R408_delta_20261028_183131`（1.2 min）。45 格可解（9 格为 EAT 硬不可行）。**δ=±0.5 相对 δ=0 的 `max\|Δq\|` 中位 1.4e-11、最大 2.3e-9 g/day**——即机器精度级别的不动。与 M2 的「价格只进目标、`min E[c]·q = min c̄·q`」同源：缩放残差离散度不改变一阶均值 |
| R409 | M4 | boundary grid | low/mid/high/worst | 6 省 × 4 变体 | `max\|Δq\|` vs mid | MUST | DONE | `outputs/R409_bounds_20261028_183421`。24 格：**solved 12（mid 6 + high 6）/ `low` 6 格求解不可行 / `worst` 6 格空盒**。`low` 经 HiGHS 判定为 `Status 8: model_status is Infeasible`（**不是超时、不是求解失败**），`worst` 是下界>上界的空盒。`high` 相对 `mid` 位移 **43.7（中位）–92.05（最大）g/day**；`mid` 为参照解（位移 0）。**结论**：边界变体直接改可行域，`low` 与 `worst` 在 6 省全部不可行——这是「最紧/最低边界不可行」的证据 |
| R500 | M5 | Table 1 | calibration | B1 两个面板 | 表内数值校验 | MUST | DONE | 与 R501–R504 合并为批次 `outputs/R500_504_paper_artifacts`。`table1_price.csv` / `table1_consumption.csv` / `table1.md`：3 遮蔽 × 4 方法 × 8 指标，**只读 `calibration_summary.csv`，不重算**。表内保留「点精度与标定不是同一件事」的注释 |
| R501 | M5 | Table 2 | decision result | B2 两口径 | 表内数值校验 | MUST | DONE | 同批次。`table2_decision.csv` / `table2.md`：2 口径 × 4 方法 = 8 行，含 `dq_change_rate`（主指标）与 `feasible_active`；**显式标注 `feasible_all` 恒为 0 是钙不可达的结构事实**，及 `gap` 不可跨面板比较 |
| R502 | M5 | Figure 1 | stable/flip | B2/M4 | 视觉 QC | MUST | DONE | 同批次。`figure1_stable_flip.csv` + `figure1.svg`（纯 SVG，无 matplotlib 依赖）：三情景标签分布 CDG 36 / EAT 18 / HEAL_base 36 = 90 组格，**`data-sensitive` 4 个全在 EAT** |
| R503 | M5 | Figure 2 | regional heatmap | B4 | 视觉 QC | MUST | DONE | 同批次。`figure2_regional_heatmap.csv` + `figure2.svg`：CDG 下 6 省 × 6 组的方向标签矩阵。**只画 6 个决策省**（上海不进决策层，见 R401） |
| R504 | M5 | appendix pack | all | all | completeness | NICE | DONE | 同批次。`artifact_manifest.json`（每个产物的 bytes + sha256）+ `appendix_index.md`（产物清单 + 源 run 路径 + 复现命令） |
| R505 | M5 | reproducibility rerun | selected must-runs | clean env | hash/metric tolerance | MUST | DONE | `outputs/R505_reproducibility`（**确定性目录，`--exact`**；门禁产物不加时间戳，否则 tracker 引用与每次重跑的时间戳互相追尾）。**自动化部分 PASS**：合同哈希零漂移 10/10、13 个关键 run 目录完整且带 `DONE`、unittest 全绿、tracker 15 项全绿。**「干净环境重跑」未执行**（需仓库外新建 venv + 联网装依赖），命令与判据写进 `RUNBOOK.md`，报告里列在 `not_verified`，**不声称已完成** |

## 状态与证据等级（读表前先读这段）

状态列只有五个取值，互斥：

| 状态 | 定义 | 判据 |
|---|---|---|
| `DONE` | 该 run 的预注册问题已有**可解析的产物**回答 | 索引能指到具体文件，且 `scripts/check_tracker.py` 通过 |
| `DONE-conditional` | 结论已定稿，但挂在一条**重跑消除不了**的数据边界条件上 | 引用时必须同时引用披露文字（见文末同名小节） |
| `PARTIAL` | 已产出，但至少一项预注册条件未满足且仍可补救 | — |
| `TODO` | 未执行 | — |
| `SUPERSEDED` | 已被后一批次取代，仅留档 | 不进入结论引用 |

证据等级与状态**正交**：`DONE` 只回答「跑完了、产物在库」，不回答「能不能进正文」。

| 等级 | 含义 | 用法 |
|---|---|---|
| `formal` | 正式协议（5 折 × 20 重复或全合同），产物完整 | 可进正文 |
| `formal_conditional` | 正式协议 + 已声明的数据边界 | 可进正文，须带披露 |
| `sensitivity` | 单因素扫描，方向可信、绝对水平受限于规模 | 只报方向与排序 |
| `structural` | 机制诊断 / 审计 | 只支撑解释，不作结论证据 |
| `smoke` | 连通性 / 装配验证 | 不进正文 |

> **为什么不能直接读 `metrics.json.evidence_status`**：42 个目录里该字段共有 6 种取值
> （`plumbing_only`、`structural`、`diagnostic_only`、`masking_protocol`、`None`、缺省），
> 没有统一词表，**不能当证据等级使用**。上表是人工判定，逐条写在索引里，可被 review；
> `metrics.json` 的字段只作参考。
>
> 最容易被误读的一处：**R300–R303 状态是 `DONE`，但证据等级是 `smoke`**。
> 它们回答的是「网格跑得通、方向单调」，不是「成本轴数字可进论文」。

## 产物索引（46 run ↔ 44 目录）

> 44 个目录 = 22 个批次目录（含 R401 可得性报告、M4 四批、M5 两批）+ 20 个 `DIAG_*`
> + 1 个遗留 `R307_binding` + 1 个附录 `APPENDIX_shanghai_k4_official`。
> 「未产出」两行对应 M4 / M5 的 TODO，留作交付清单。
> 本表的目录与文件路径由 `scripts/check_tracker.py` 逐条核对。

| run | 目录 | 关键产物 | 证据等级 |
|---|---|---|---|
| R000 | —（`python -m unittest`，无批次目录） | `tests/test_smoke.py`、`tests/test_b2.py` | formal |
| R001 | —（审计结论已并入本表与 `EXPERIMENT_PLAN.md`） | `data/processed/model_manifest.json` | formal |
| R002 | `outputs/R002_group_freeze_20261027_232440` | `contract_gate_report.json`、`metrics.json` | formal |
| R003–R006 | —（toy fixtures，无批次目录） | `tests/test_lp_fixture.py`、`tests/test_smoke.py` | formal |
| R100–R102、R106 | `outputs/B1_formal_withmice_20261023_124906` | `calibration_summary.csv`、`cell_predictions.csv`、`coverage_curve_summary.csv` | formal |
| R103–R105 | `outputs/R103_105_consumption_formal_20261026_174725` | `calibration_summary.csv`、`cell_predictions.csv` | formal |
| R106（消费面板） | 同上 | `coverage_curve_summary.csv`、`coverage_curve_by_fold.csv` | formal |
| R107 | `outputs/R107_interaction_gate` | `interaction_gate.json`、`interaction_gate.csv` | sensitivity |
| R108–R109 | `outputs/R108_109_price_formal_20261026_175443` | `mar_summary.csv`、`mnar_delta_summary.csv`、`mnar_rank_stability.csv` | formal |
| R200–R203 | `outputs/R200_203_b2_formal_20261027_222841`（EAR）、`outputs/R200_203_b2_formal_20261027_224315`（RNI） | `b2_results.csv`、`metrics.json`、`protocol_shift.csv` | formal_conditional |
| R300–R303 | `outputs/M3_all_smoke_20261026_181618` | `m3_grid_results.csv`、`m3_grid_summary.csv`、`r303_weight_stability.csv` | smoke |
| R304 | `outputs/R304_weight_uncertainty_20261027_143003` | `weight_uncertainty_summary.csv`、`weight_uncertainty_draws.csv` | sensitivity |
| R305 | `outputs/R305_chance_mode_20261027_142626`、`outputs/R305_high_eps_20261027_143744` | `chance_mode_summary.csv`、`chance_mode_results.csv` | sensitivity |
| R306 | `outputs/R306_big_m_20261026_181747` | `big_m_summary.csv`、`big_m_spread.csv`、`big_m_agreement.csv` | structural |
| R307 | `outputs/R307_gate_20261027_142902` | `gate_sensitivity.csv`、`common_group_compare.csv` | sensitivity |
| R307b | `outputs/R307b_gate_factorial_20261027_145412` | `gate_factorial.csv`、`common_group_compare.csv` | sensitivity |
| R401 | `outputs/R401_shanghai_availability_20261028_180508` | `report.md`、`coverage_matrix.csv`、`scope_gap.csv` | structural |
| R400、R402–R406 | `outputs/R400_406_provinces_20261028_183104` | `m4_direction_labels.csv`、`m4_province_scenario.csv` | formal |
| R407 | `outputs/R407_looro_20261028_183054` | `m4_looro.csv` | sensitivity |
| R408 | `outputs/R408_delta_20261028_183131` | `m4_delta.csv` | sensitivity |
| R409 | `outputs/R409_bounds_20261028_183421` | `m4_bounds.csv` | sensitivity |
| R500–R504 | `outputs/R500_504_paper_artifacts` | `table1_price.csv`、`table2_decision.csv`、`figure1.svg`、`figure2.svg`、`artifact_manifest.json` | formal |
| R505 | `outputs/R505_reproducibility` | `reproducibility_report.json`、`RUNBOOK.md` | formal |

### 结构诊断目录（`DIAG_*` 20 个 + 遗留 1 个）

| 目录 | 支撑的结论 | 出处 |
|---|---|---|
| `outputs/DIAG_decision_sensitivity_20261026_181347` | 使解移动所需的扰动幅度（价格 20%–100%、脂肪系数 10%） | §14 |
| `outputs/DIAG_binding_20261026_193238` | 约束紧性三态；§14 的因果解释一半被推翻 | §18 |
| `outputs/DIAG_objective_20261026_193437` | 顶点枚举 + 极端权重下的换解情况 | §18 |
| `outputs/DIAG_scope_activation_20261027_151305` | K=4 下 10 条约束被 `non_actionable` 静默排除 | §21 |
| `outputs/DIAG_heal_bound_scale_20261027_151753` | HEAL_base 上界倍数与钙耦合；`hard_feasible` 判据非单调 | §22 |
| `outputs/DIAG_calcium_gap_20261027_163714` | 钙缺口来自基线本身，不是优化压低 | §23 |
| `outputs/DIAG_cvar_channel_20261027_163855` | CVaR 通道在 CDG 上零位移 | §24 |
| `outputs/DIAG_cvar_angle_spike_20261027_164753` | CVaR 对目标方向的旋转角 | §24 |
| `outputs/DIAG_vertex_stability_20261027_164615` | 顶点稳定性 | §24 |
| `outputs/DIAG_vertex_radius_20261027_164952` | 顶点稳定半径 `θ*` | §24 |
| `outputs/DIAG_feasible_width_20261027_164140` | 可行域宽度；EAR 下 D1≡D0 | §24 |
| `outputs/DIAG_price_radius_20261027_174014` | 单组价格半径 20%–100%，H1「真稳健」成立 | §26 |
| `outputs/DIAG_price_panel_20261027_180334` | 换价格构造救不回 EAR 的对比度（③-a 否证） | §28 |
| `outputs/DIAG_tail_angle_20261027_192248` | `θ_tail` vs `θ*` 预注册判定（1 无效 / 3 边界 / 5 须报曲线） | §29 |
| `outputs/DIAG_lambda_curve_20261027_191751` | CDG 六省 λ∈[0,1] 全程 Δq=1e-9；EAT 三省阶跃 | §29 |
| `outputs/DIAG_lambda_curve_fine_20261027_191956` | 同上，细网格确认阶跃点随样本移动 | §29 |
| `outputs/DIAG_price_coverage_20261027_193323` | 36 单元覆盖率审计；G3 的 `collapsed` 全由 G06 缺陷构成 | §30 |
| `outputs/DIAG_d0_bistability_20261027_231703` | D0 是二值开关，省份名单不可引用 | §31.8 |
| `outputs/DIAG_price_panel_20261027_232721` | G06 下界低估「修前」版（返回假 0.0%，**留档不引用**） | §32 |
| `outputs/DIAG_price_panel_20261027_232756` | 同一指标的「修后」当前版（54.1%、带 `ref_source`） | §32 |
| `outputs/R307_binding_20261026_193215` | §15 的实测依据（编号曾误编为 R307，见 `CLEANUP_2026-10-28.md` §二） | §15 |

### 附录产物（**不计入** 46 run 计数）

| 目录 | 内容 | 使用约束 |
|---|---|---|
| `outputs/APPENDIX_shanghai_k4_official_20261028_181254` | 上海在 `k4_official` 下的单点对照（CDG 情景、smoke、EAR）。实测 D0≡D1≡D3（`\|Δq\|`=0.00）、仅 D2 位移 85.05 g/day | **仅附录**：口径与 K=6 不同，**不得与 6 省主结果并列比较**。目录内有 `APPENDIX_ONLY.json` 标记，说明用途与禁止用法 |

> 附录单点存在的唯一目的，是说明「口径决定样本」——同一套数据下上海能进 K=4、进不了 K=6。
> 它**不是**第 7 个地区的决策结果，结论门（direction agreement ≥ 90%）不把它计入分母。

## 进度总览（2026-10-28 第十八轮快照）

> 判定基线是「产物是否在库且可被解析」，不是「论文是否已写」。
> 计数由 `scripts/check_tracker.py` 与上表逐行核对，**改表必须同步改计数**。

| 里程碑 | DONE | DONE-conditional | PARTIAL | TODO | 说明 |
|---|---|---|---|---|---|
| M0 数据审计与冻结 | 7 | 0 | 0 | 0 | **完成**（R000–R006，含 5 条手算 LP fixture） |
| M1 插补方法比较 | 10 | 0 | 0 | 0 | **完成**（价格 + 消费两个面板，R108/R109 正式批次） |
| M2 决策可靠性主实验 | 0 | 4 | 0 | 0 | **定稿为零结果报告**，带数据边界条件（见文末「R200–R203 的定稿条件」） |
| M3 敏感性网格 | 9 | 0 | 0 | 0 | **完成**（R300–R307 + R307b）；R300–R303 证据等级为 `smoke` |
| M4 分省情景 | 10 | 0 | 0 | 0 | **完成**（R400/R402–R406 合并批次 + R401 可得性 + R407/R408/R409） |
| M5 图表与交付 | 6 | 0 | 0 | 0 | **完成**（R500–R504 产物 + R505 可复现性报告；干净环境重跑仍待人工） |
| **合计** | **42** | **4** | **0** | **0** | 46 个预注册 run 全部结案；另有 20 个 `DIAG_*` 结构诊断 + 1 个遗留目录，不计入 |

**M1 全部完成的含义**：插补方法的比较证据链已闭合，且是在正式协议
（5 折 × 20 重复 × 3 种遮蔽几何）下闭合的，不是 smoke。

**M2 为什么曾经卡在 PARTIAL（第十轮—第十七轮推导，保留作过程记录）：两处接线已完成，但接线后暴露出一个更大的问题。**

> **结案提示**：本节及以下到「第十六轮已把……」为止，记录的是
> 「EAR 让对比度归零 → 换指标 → 否证换面板 → 查真值」这条查证链。
> **结论已在 2026-10-28 结案**：EAR 零结果是干净的零结果，R200–R203 标 `DONE-conditional`，
> 条件写在文末「R200–R203 的定稿条件」。本节数字仍然有效，但「仍是 PARTIAL」的措辞已过期。

> 第九轮说的两处接线（场景源、重复结构）**已全部实现并通过回归验证**
> （旧路径逐位 diff 全 0，CHANGELOG §25.4）。正式批次已跑：
> `R200_203_b2_formal_20261027_170542`（EAR）/ `..._171718`（RNI 对照）。

**但 EAR 口径下 M2 的对比度归零**（CHANGELOG §25.6，归因见 §25.9 / §26）：

| 口径 | D0 \|Δq\| | D1 \|Δq\| | D3 \|Δq\| | D3 翻转率 | D1 跨单元唯一解数 |
|---|---|---|---|---|---|
| **EAR（主口径）** | 0.000 | 0.000 | 0.000 | 0.000 | 6 省全部 **1** |
| RNI（对照） | 38.771 | 1.049 | 10.906 | 0.028 | 3/6 省为 **2** |

即 EAR 下 D0 ≡ D1 ≡ D3，flips 与 regret 恒为 0，**预注册指标全部退化**。
只有 D2（无营养约束）还不同：`|Δq|` 128.65、gap −0.80、翻转率 0.194。

**第十二轮已换主指标**（CHANGELOG §27，预注册偏离已声明）：

| 口径 | 主指标 `\|Δq\|` 变化率 | p95 (g/day) | 辅助 `flip_rate` |
|---|---|---|---|
| EAR | **0.000** | 0.00 | 0.000 |
| RNI / D0 | **0.498** | **110.97** | 0.000 |
| RNI / D1 | 0.013 | 0.00 | 0.000 |
| RNI / D3 | 0.333 | 36.41 | 0.028 |

换成对幅度敏感的指标后，**EAR 的零结果依然是 0**——所以它是干净的零结果，
不是指标退化造成的假象。RNI 下同一批数据有 49.8% 的单元会变。

**这需要作者在四者之间裁定**（CHANGELOG §25.8 + §26.8）：

1. **接受 EAR 的代价**——M2 改写成「决策对价格信息稳健」的零结果报告；
2. **M2 决策层回退 RNI**——与 M1 的评估层解耦，保住对比度；
3. ~~**改合同价格口径**——用年度价或 `price_cny_kg_full`，让插补与价格差异不被 9 年平均掉；~~
   **已拆成两条（CHANGELOG §28.6）**：
   * **③-a 改价格口径以恢复对比度** → **否证**。组价改到中位 2.6%/最大 21.6%，
     EAR 下 6 省 dq 仍全为 0（`DIAG_price_panel_20261027_180334`）；
   * **③-b 修 G06 部分结构聚合的 21.7% 低估** → **待裁定**（数据质量，独立问题）；
4. ~~**只改指标，不动模型**~~——**已执行**（§27）。

> **另一个新查清的缺口（比「真值仍是占位」更优先）**：
> `Contract.price_panel()` 用的是 `price_cny_kg`（303/756 非空），
> `price_cny_kg_full`（473/756）**从未被调用**。453 个缺失格不是被插补填上，
> 而是被年份平均直接跳过；G07 只有 23/63 格有价，合同组价实为 **3 年均值**。
> 即 B1 的插补目前只通过**残差分布**进入 B2，**没有通过点估计进入**。
> 见 CHANGELOG §25.7。

> **明日续接入口**：`docs/archive/DECISIONS_2026-10-27.md`（一页裁定书）+
> `docs/CHANGELOG_2026-10-26.md` §23/§24/§25（推导与 run ID）。

> **run 引用约定**：R306 有两个目录，`..._181722` 已被 `..._181747` 取代
> （前者缺 M 跨度自检，无法证明对照有效），已写 `SUPERSEDED` 标记。

> **2026-10-26 晚追加两个结构诊断**（不计入上表 run 数，属 `DIAG_*` 而非预注册实验）：
> `DIAG_binding_*`（约束紧性三态）与 `DIAG_objective_*`（顶点枚举 + 极端权重）。
> 结论：§14 的因果解释一半成立一半被推翻，见 CHANGELOG §18。
> **R307 仍是 TODO**（它是 boundary gate，不是这两个诊断）。

> **2026-10-27 追加第三个结构诊断**（同样不计入 run 数）：
> `DIAG_scope_activation_20261027_151305`（`scripts/diagnose_scope_activation.py`，纯装配无求解）。
> 产出「K=4 被 `non_actionable` 静默排除、K=6 才生效」的 **10 条**约束清单，
> 以及四口径 × 三情景的硬可行矩阵。结论：**可行率不可跨口径比较**，见 CHANGELOG §21.4。
> 另有两个量纲错误的早期版本已标 `SUPERSEDED`（`_151224` / `_151242`）。

> **2026-10-27 追加第四个结构诊断**：
> `DIAG_heal_bound_scale_20261027_151753`（`scripts/diagnose_heal_bound_scale.py`）。
> HEAL_base 上界倍数 × 钙的耦合分析。**关键教训：只用 `hard_feasible` 判会得到非单调结果**
> （m=2.5 4/6、m=3.0 3/6），因为 `active_mask` 随边界变化；改用
> `full_feasible`（11 营养素全强制纳入）后才单调。见 CHANGELOG §22。
> 早期两版 `_151648` / `_151734` 已标 `SUPERSEDED`。

> **2026-10-27 追加第五个结构诊断**：
> `DIAG_price_radius_20261027_174014`（`scripts/diagnose_price_radius.py`，纯 LP 价格扫描）。
> 判「EAR 下 D0≡D1 是真稳健还是没踩到阈值」。三度量：单组价格半径、
> 省际价差放大倍数、最优解绑定约束。
> 结论：**H1（真稳健）成立**——EAR 下 60/90 格在 ±200% 内不动，真实价差（15–65%）下 0/6 省翻转；
> RNI 下 3/6 省翻转。两种口径的实例**只差 7 个营养下界**，绑定约束由「能量·脂肪」
> 换成「脂肪·硒」。见 CHANGELOG §26。
> **教训：合并价在三处各算一遍（`price_mode="pooled"` 用 7 省、D0 用 6 省、诊断用 7 省），
> 口径不一致让安徽的 t 差 4 倍。已收敛到 `Contract.pooled_price(provinces)` 单一入口。**
> 早期三版 `_173136`（7 省）/ `_173521`（未含度量 C）/ `_173709`（等价）已标 `SUPERSEDED`。

> **2026-10-27 第十二轮：M2 主指标改为决策位移**（CHANGELOG §27）。
> 新增 `scripts/summarize_dq.py`（按省拆位移 + 容差聚类数唯一解，非实验 run）。
> 重跑正式批次 `R200_203_b2_formal_20261027_174710`（EAR）/ `..._174714`（RNI），
> 与 `..._170542` / `..._171718` **逐元素 diff 全 0**，仅汇总层不同。
> **旧两个批次不再引用**（数字相同，但缺 `dq_ref_*` 指标）。
> `_170542` / `_171718` / `_174710` / `_174714` **四个目录已于 2026-10-28 清理**
> （`docs/archive/CLEANUP_2026-10-28.md` B 组）。当前唯一应引用的是
> `R200_203_b2_formal_20261027_222841`（EAR）/ `_224315`（RNI）。
> 若需复现「`_174710` → `_222841` 逐元素 diff 全 0」，用 `scripts/run_b2.py` 在 v2 面板重跑。

> **2026-10-27 追加第六个结构诊断**：
> `DIAG_price_panel_20261027_180334`（`scripts/diagnose_price_panel.py`）。
> 对比观测口径与「观测+桥接」口径的组价，测换面板后决策是否改变。
> 结论：组价变动中位 2.6%、最大 21.6%，**EAR 下 6 省 dq 全为 0**（RNI 下仅安徽翻 49.0）。
> 即**换价格口径救不回 EAR 的对比度**（选项 ③-a 否证）。
> 另查出 G06 的 24 行部分结构组价**低估中位 21.7%、最大 36.6%**（独立数据缺陷，③-b）。
> 见 CHANGELOG §28。

> **2026-10-27 追加第七、第八个结构诊断**（执行 §24.8 预注册判定）：
> `DIAG_tail_angle_20261027_192248`（`scripts/diagnose_tail_angle.py`）——
> 用 B1 经验残差后验算 `θ_tail`，与 `DIAG_vertex_radius_20261027_164952` 的 `θ*` 逐省比对，
> 200 场景 × 20 seed。结果：9 格中 **1 格可证明无效（CDG/江苏，0.51×）**、
> **3 格边界不稳**（福建 0.87× 翻转率 0.25、浙江 1.16× 0.95、安徽 1.32× 0.95）、
> **5 格须报 λ 曲线**。
> `DIAG_lambda_curve_20261027_191751` + `_fine_20261027_191956`
> （`scripts/diagnose_lambda_curve.py`）——把「须报曲线」真算出来：
> **CDG 六省 λ∈[0,1] 全程 Δq = 1e-9（决策逐位不变）**，
> **EAT 三省跳 128–252 g/day**，且曲线是**阶跃**、跳变 λ 随样本在 0.40–0.90 间移动。
> 即 §24.8 的保守判定在 CDG 上被实测推翻（`θ*` 是充分非必要条件）。
> 结论：**CDG 不需要 CVaR，EAT 依赖 λ 且无自然取值**。见 CHANGELOG §29。

> **2026-10-27 追加第九个结构诊断**（纯数据审计，无求解）：
> `DIAG_price_coverage_20261027_193323`（`scripts/diagnose_price_coverage.py`）。
> 逐 (省,组) 单元统计年份覆盖，并拆解 G3 的 `collapsed` 指标构成。
> 结论三条：
> ① 权重归一化缺陷**只在 G06**（唯一的多品类组），24 行，权重质量损失 21.2%/7.6%；
> ② **36 个单元只有 2 个是 9 年全观测**，3 个只有 1 年（山东/G05、山东/G07、浙江/G07），
>    1 个零观测全靠桥接（浙江/G05），≤2 年的占 17%，中位 5 年；
> ③ **G3 的 `collapsed = 0.451` 完全由这 24 行构成**（23/23 来自 `pork=1.000`），
>    排除后为 **0.000**——gate 通过是因为缺陷恰好只影响 45.1%，差 5 个百分点就 FAIL。
> 即 G3 的 PASS 是**假通过**。见 CHANGELOG §30，处置见 `TO_DECIDE.md` 决定 5。

> **2026-10-27 追加第十个结构诊断**（纯读 CSV，无求解）：
> `DIAG_d0_bistability_20261027_231703`（`scripts/diagnose_d0_bistability.py`）。
> 起因：按修正后面板重跑 RNI 批次后，**D0 的决策变了 50–111 g/day**，而 D1/D2/D3 逐位不变。
> 结论：**D0 是二值开关**——
> ① RNI 下 D0 的 `q_G08` 在每个省**只有 2 个取值**，间距是 6 个固定常数
>    （29.03 / 36.41 / 48.99 / 54.00 / 74.87 / 110.97）；
> ② **EAR 下只有 1 个取值**，且新旧面板完全相同（极差 0.00e+00）；
> ③ D1 也是二值开关，但分布（97/3）**跨面板完全不变**；D0 的分布从 98/2 变成 73/27；
> ④ 因此「D0≠D1 的省份」**整套翻转**（安徽/山东/浙江 → 江苏/江西/福建），
>    而 `D0 变化率` 从 0.498 变成 0.460 —— 这个数是**开关侧占比，不是效应量**。
> 处置：论文**不得引用「3/6 省」的具体名单**；RNI 附录只报机制与区间。
> 见 CHANGELOG §31.8。

---

## B2 data contract status（EXPERIMENT_PLAN.md §3）

七个合同文件全部落地，且每条 gate 条件已由 `scripts/check_contract_gates.py` 实测通过。
复现方式：`python scripts/build_contract_files.py`（构建 + 验收 + 回写 manifest 一条命令完成）。

| # | File | Gate condition | Result |
|---|---|---|---|
| G1 | `group_audit.csv` | include=1 的组通过全部覆盖规则 | PASS — 4 组四门全通过（G02/G05/G06/G08） |
| G2 | `baseline_consumption.csv` | 无负值；主结论组有可识别基线 | PASS — 630 行零负值，4/4 组有基线 |
| G3 | `group_prices.csv` | 只有定义匹配的最终组单位价格 | **PASS（2026-10-27 第十六轮已修 gate）** — 零非正值、零 observed 缺价、多品类组零退化；**`collapsed` 已从 45.1% 降到 0%**（分母 48 行完整结构，排除 3 行下界）；`thin` 已加**单元级**门槛 `MIN_CELL_PRICE_YEARS=5`，覆盖率不足转为 **WARN 不 FAIL**：K=4 口径 7/28 个单元、**决策口径 k6_price 13/36 个单元**有价年份 <5（最薄 山东/G05、山东/G07、浙江/G07 各 1 年）。**论文数据节必须披露覆盖率。** 见 CHANGELOG §30 / §31.2 |
| G4 | `nutrients.csv` | 所有硬营养素覆盖率 100% | PASS — 4 组 × 11 营养素零缺口 |
| G5 | `environment.csv` | 主目标覆盖率 100%，系统边界统一 | PASS — 48 行全满，边界唯一（farm-to-retail） |
| G6 | `decision_bounds.csv` | 有限、冻结、lower ≤ upper | PASS — 259 行（单组 252 + 联合 7），3 情景 × 7 省全覆盖 12 组 |
| G7 | `model_manifest.json` | hashes / units / version / timestamp 齐备 | PASS — 9 个产物 hash 与磁盘一致，零漂移 |

> **合同口径 vs 决策口径（2026-10-27）**：上表七条 gate 针对的是**合同文件**
> `group_audit.csv`（K=4），它仍是 Plan 第 3 节定义的七个文件之一，未变。
> 但**模型实际用哪个 K** 由 `configs/default.yaml` 的
> `optimization.decision_scope` 决定，当前为 `k6_price`（K=6）。
> 切换口径只换审计表（其余六个文件逐字节相同），manifest 的
> `decision_scope` 段记录 K、组集合、可用省（6）、跳过省（上海缺 G07）
> 与联合约束核对结果（6 省 CDG 全部 applied）。
> **引用「合同 7/7 通过」时必须说明它验的是 K=4 那张表。**

### 待人工复核的口径决策

1. **G06 价格聚合改为消费结构加权**（权重 猪 0.788 / 牛 0.136 / 羊 0.076）。
   此前取主导品类猪肉，等于取三品类最低价（`price_min` 与猪肉价在 G06 全部观测行相等），
   会系统性低估组价，使优化器高估红肉可负担量；随后一度改为可用品类等权（54.43 元/kg），
   但等权等价于假设"三分之二是牛羊肉"，同样不对。现为结构加权 43.92 元/kg，
   落在最低价 38.80 与严格等权 67.45 之间，符合预期。
   `price_structure_weighted` / `price_equal_weight` / `price_complete_equal` / `price_min`
   四列并存，供 B2/B4 做口径敏感性。
2. **痕量处理**：G06 羊肉碳水化合物为痕量，严格口径判 10/11 而排除红肉；若 `trace_as_valid=True` 则 K=4。
   一个痕量格决定红肉能否进入优化，需在论文显式报告并做敏感性。
3. **决策边界不再硬拆指南类别**。CDG「畜禽肉 40–75 g」不区分畜肉与禽肉，
   此前按假设的消费结构（猪肉六成、禽肉两成半）拆成红肉 25–45 / 禽肉 15–30，
   该比例在仓库内无任何数据支撑。现改为联合约束 `G05+G06 ∈ [40, 75]`（`bound_type=joint`），
   组间分配由模型在成本/营养/环境目标下决定。
   **代价：CDG 情景的红肉结果不能解读为「指南推荐的红肉量」，必须随结果报告。**
   **施加规则**：联合约束只在全部成员组都进入模型时才施加；成员不全时必须整条跳过，
   绝不能退化成对单个成员的约束（那会把「畜禽肉合计」误读成「禽肉单独」，把 G05 下界从 15 抬到 40）。
   决策口径 `k6_price` 同时含 G05 与 G06，联合约束生效（实测 6 省 CDG 全部 applied，
   见 `model_manifest.json` 的 `decision_bounds.joint_constraint_check`）。
   原 K=3 口径下该约束只能整条跳过，且禽肉剩余区间为负（上海 [-46.5,-11.5]），CDG 情景不可满足。
4. **仍有三处类别错配无法用联合约束消除**：CDG 谷类 200–300 与 EAT whole grains 均不含豆类，
   而 G04 是谷物+豆类，两个上界对 G04 偏紧；EAT 的 legumes 与 nuts 是两类而 G12 合并。
5. **environment 主口径**：用 OWID / Poore & Nemecek (2018) 全球表（边界统一、零缺失）；
   china_lca 因边界各异且大量依赖组均值代理，仅作区域对照，不进入主目标。
   **组内聚合为品类内平均 + 品类间结构加权**（与价格、营养共用同一套权重）。
   演进路径：4 实体扁平等权（ghg 46.20）→ 层级等权（39.47）→ 结构加权（**21.75**）。
   子结构已写入 `ontology.csv` 的 `global_env_subgroups` 列，
   `environment.csv` 的 `aggregation` 列逐行标注实际方法。

### 组内聚合口径（四维度一致性）

决策变量是组级摄入量，因此组级系数应当是组内各品类的**加权平均**，
权重等于消费结构（恒等式 `p̄ = Σ p_i·q_i / T`）。
消费表本身只到「肉类」合计、权重不可观测，但权重可以从外部数据独立构造。

**权重来源**（`data/input/external/meat_consumption_structure.csv`）：

| 品类 | 产量(万吨) | 进口(万吨) | 表观消费(万吨) | 份额 |
|---|---|---|---|---|
| 猪肉 | 5794 | 155.00 | 5949.00 | **0.7879** |
| 牛肉 | 753 | 274.00 | 1027.00 | **0.1360** |
| 羊肉 | 531 | 43.36 | 574.36 | **0.0761** |

表观消费 = 产量 + 进口（忽略出口与库存变化）。产量取国家统计局 2023 年统计公报，
进口取海关总署 2023 年数据（不含杂碎）。不按省取权重：分省可得的是产量而非消费量，
产量反映生产布局（山东产猪外调、上海不产猪但消费量大），按省套用会把结构算反。

**接入状态**（三个维度共用 `src/component_weights.py` 的同一套权重）：

| 维度 | 聚合方式 | 权重 | 状态 |
|---|---|---|---|
| 价格 | 结构加权，缺失品类按已观测品类归一 | 猪 0.788 / 牛 0.136 / 羊 0.076 | 已接入 |
| 营养 | 结构加权，缺失食物按已观测食物归一 | 同上 | 已接入 |
| 环境 | 品类内先平均，品类间结构加权 | 同上 | 已接入 |
| 消费 | 无需聚合（本身是组级） | — | — |

**口径变更的实测影响**（G06，等权 → 结构加权）：

| 维度/指标 | 等权 | 结构加权 | 变化 |
|---|---|---|---|
| 价格 (元/kg) | 54.43 | **43.92** | −19.3% |
| 环境 ghg (kg CO2e/kg) | 39.47 | **21.75** | −44.9% |
| 环境 land (m²/kg) | 190.63 | **66.94** | −64.9% |
| 环境 eutrophication (g PO4e/kg) | 168.95 | **112.91** | −33.2% |
| 环境 freshwater (L/kg) | 1893.78 | **1835.36** | −3.1% |
| 营养 能量 (kJ/kg) | 10023 | **14235** | +42.0% |
| 营养 脂肪 (g/kg) | 184.3 | **308.0** | +67.1% |
| 营养 蛋白质 (g/kg) | 173.7 | **145.5** | −16.2% |
| 营养 铁 (mg/kg) | 24.00 | **18.84** | −21.5% |

方向解释：猪肉占近八成且是三品类中最便宜、排放最低、脂肪最高的，
所以结构加权让红肉在**成本与环境**上更便宜、在**能量与脂肪**上更"重"。
等权并不是中性先验——它等价于假设"中国人吃的红肉有三分之二是牛羊肉"，
与事实差得很远。此前"等权偏高、方向偏保守"的说法只对成本与环境成立，
对营养维度是**反方向**的（等权低估了能量与脂肪 42%/67%）。

**已知残余偏差**：

1. **价格面板覆盖缺口**：G06 的 51 个省-年观测中仅 27 行三品类齐全，
   23 行只有猪肉单品类。这 23 行归一后组价仍等于猪肉价，
   故 G3 的「等于最低价比例」实测 **45.1%（23/51）**，阈值 50% 已贴近。
   这不是聚合方法缺陷，只能靠插补解决（用户已有两份 MICE 插补表，登记为补充来源）。
2. **G07 水产仍为实体扁平等权**：Fish (farmed) 13.63 与 Prawns (farmed) 26.87
   平均成 20.25 kg CO2e/kg。水产消费结构缺可靠公开依据，不编造权重。
3. **权重为全国口径、2023 单年**：2019–2020 非洲猪瘟为异常年已排除；
   2016 与 2023 产量结构接近（猪肉 82.2% vs 81.9%），年际稳定性可接受。
4. **表观消费含流通损耗、不含在外就餐**：作为结构比例的代理可用，
   但餐饮中牛肉占比更高，故真实牛肉权重可能略高于 13.6%，本权重偏保守。



### 计划内部不一致（需作者裁定）

`EXPERIMENT_PLAN.md` §6 里程碑表声明 M1 覆盖 `R100–R112`、M4 覆盖 `R400–R423`，
但计划全文仅逐条定义了 R100–R109 与 R400–R409。
即 M1 有 3 个、M4 有 14 个 run 槽位被声明却无任何定义（用途/变体/指标均缺失）。
本 tracker 不为这些空槽位编造内容——需要先回到 Plan 补齐定义，否则属于预注册缺口。

## 审计发现（2026-10-26）

完整报告见 `docs/archive/AUDIT_2026-10-26.md`。以下三项影响结论正确性，必须处理：

| 编号 | 问题 | 后果 |
|---|---|---|
| P0-1 | ~~C1 按 Plan §4 标准不成立~~ **已处理**：改写为「以点精度换区间校准 + 证明基线不稳健」，记为 Plan 修订 R-2026-10-26-a | 已解决 |
| P0-2 | ~~CDG 情景在主口径下禽肉无指南约束~~ **已处理**：根因是 7 省红肉单独已达 82.9–94.4 g/天、畜禽肉合计全部超 75，K=3 下 CDG 约束不可满足而非缺失。主口径改为 K=4 纳入 G06（修订 R-2026-10-26-b） | 已解决；新增代价见下 |
| P0-3 | **B1 只验证价格面板**：config 无 consumption 路径，R103–R105 无法执行 | C1 关于数据层可靠性的证据只覆盖一半 |

已完成的卫生处理：7 个缺元数据的 run 目录写入 `INCOMPLETE.json`；
`outputs/decision_space_20261023_134000` 写入 `STALE_ONTOLOGY.json`（含 6 个废弃组名）。

## M2 框架状态（2026-10-26 搭建）

已建成 `scripts/run_b2.py` + `src/b2_problem.py` / `b2_scenarios.py` / `b2_evaluate.py`，
19 个测试通过（`python -m unittest discover -s tests`）。
但 **当时 R200–R203 是 PARTIAL，不是 DONE**（本节是 2026-10-26 的状态快照，
结案见 §32 与文末「R200–R203 的定稿条件」）：三处占位未替换，且装配过程暴露出四个
问题——其中浙江缺数（第 4 条）已解决，营养边界口径（第 1 条）已备好 EAR 分支，
钙的结构性不可达（第 2 条）与 D0/D1 退化（第 3 条）仍未解决。

### 三处占位（metrics.json 的 `placeholder_components` 已列明）

| 占位项 | 当前实现 | 正式要求 |
|---|---|---|
| 真值 | 冻结合同点估计 | 遮蔽前保留的伪完整面板 |
| 场景 | 点估计上的对数正态扰动（CV=5%） | B1 层级随机游走后验 |
| 重复 | 换种子重抽场景 | 5 折 × 20 重复的遮蔽协议 |

`metrics.json` 的 `evidence_status` 固定为 `plumbing_only`，防止被误当论文证据。

### 四个阻塞问题（2026-10-27 第九轮更新）

> **第九轮状态（作者已裁定全部四项）**
>
> | # | 阻塞 | 状态 | 裁定 |
> |---|---|---|---|
> | 1 | 营养边界 RNI vs EAR | **RESOLVED** | 切 **EAR** |
> | 2 | 钙的处置 | **RESOLVED** | 按**可达上限**报告，不硬不软（§23） |
> | 3 | 价格不确定性零传导 | **RESOLVED 为模型性质** | 主线用 D1 + 零传导论证；CVaR 进附录（§24） |
> | 4 | 浙江入模 | **RESOLVED** | K=6 已含浙江 |
>
> 剩余待办全部落在数据层（B1 后验、遮蔽协议），不再是口径决策。

> **2026-10-27 口径层更新（重要，先读这段）**
>
> 作者已裁定「要价格传导」，决策口径定为 **`k6_price`**（K=6，+G04 +G07，
> 6 省，上海出局）。该口径已写入 `configs/default.yaml` 的
> `optimization.decision_scope`，并由 `build_contract_files.py` 交叉校验后
> 记入 `model_manifest.json`，契约 7/7 gate 通过。
>
> 随之出现三条必须同时记住的结构事实（详见 CHANGELOG §21）：
>
> 1. **可行率不可跨口径比较**：K 变大后，部分营养素从 `non_actionable`
>    变为 `active`，约束才开始被施加。K=4 下实测有 **10 条**约束被静默排除。
>    `k3_prereg` 在 HEAL_base 上「5/7 可行」是四口径最好，正因为它丢掉了 14 条约束。
> 2. **价格不确定性结构性不传导**：目标对 `q` 线性、价格只进目标不进约束，
>    故 `min E[c]·q = min c̄·q`，D3 ≡ D1（max\|Δq\| ≤ 1e-6）。
>    这与第 3 条的旧表述冲突，旧表述已作废。
> 3. **HEAL_base 在 K=6 + RNI 下 0/6 硬不可行**（脂肪/碳水/硫胺素三重冲突）。
>    **但切到 EAR 后 6/6 全部硬可行，2× 上界不用改**（CHANGELOG §22.8）。
>    即这条阻塞的根源是**下界口径**，不是上界倍数——我此前只测了下界固定时的
>    上界敏感性，把原因错归给上界。**先定 RNI/EAR，上界问题自动消失。**

**1. 营养边界口径错位 —— 已裁定切 EAR（RESOLVED，2026-10-27）**

RNI 的设计目标是覆盖 97.5% 个体，把它当作「人均摄入应达到的下界」是口径错位。

EAR 数值已从国标取到（WS/T 578.2-2018 / 578.3-2017 / 578.5-2018，18 岁～）：

| 营养素 | EAR（本模型用） | RNI（本模型用） | 差 |
|---|---|---|---|
| 钙 | **650** | 800 | −150 |
| 铁 | **12** | 16 | −4 |
| 锌 | **8.25** | 10 | −1.75 |
| 硒 | **50** | 60 | −10 |
| 硫胺素 | **1.1** | 1.3 | −0.2 |
| 核黄素 | **1.1** | 1.3 | −0.2 |
| 烟酸 | **11** | 13.5 | −2.5 |

已实现 `--bounds-basis {rni,ear}`（默认 `rni`，预注册口径不变）。
实测：**EAR 解除了硫胺素的不可达，但解不了钙**——见第 2 条。

> 同时更正了一处溯源错误：`nutrient_bounds.csv` 原先标注来源为「DRIs 2023」，
> 但数值实际对应 **2013 版**。现已改为国标编号，并新增 `verified_against` 列。

**2. 部分营养素结构性不可达（RESOLVED：钙按可达上限报告，见下）**

若某营养素在决策箱内无法进入 `[ℓ,u]`，则每个场景必然违反，`z` 全为 1，
`z_sum ≤ floor(εS)` 直接不可行——这与决策质量无关。

| 口径 | 不可达营养素 | 不可达省数 | 缺口倍数 |
|---|---|---|---|
| RNI | 钙 | 7/7 | 1.64 |
| RNI | 硫胺素 | 6/7 | 1.00（差 0.1%，纯临界） |
| EAR | 钙 | 7/7 | **1.33** |
| EAR | 硫胺素 | — | **已解除** |

另有两处非营养需求本身的问题，属基线或边界设置：

| 省份/情景 | 被排除的营养素 | 原因 |
|---|---|---|
| 安徽/江西（CDG） | 碳水化合物 | 最小可达 41.5 g，上界仅 8.5–18.5 g（基线本身超标） |
| 各省 EAT | 脂肪 | 最大可达 25.3 g，下界 25.7–27.8 g |

**钙的缺口是结构性的，不是门槛松紧能解决的**：决策箱（蛋/禽/红肉/蔬菜）
最多提供 168 mg，非决策组基线只贡献约 321 mg，合计 489 mg，
而 EAR 要 650。中国膳食钙约 60% 来自乳制品与豆制品，而 G01（乳制品）
不在决策集内。**唯一真正的解法是把 G01 纳入决策箱，或把钙改成软约束/惩罚项。**
这是 K 值设定的直接后果，不是数据缺陷。

> **2026-10-27 第九轮裁定（CHANGELOG §23）：按「可达上限」报告，不做硬约束、不做软约束。**
> 理由：钙在 **18/18 个 (情景, 省) 单元格**里都已被 `non_actionable` 排除
> （最大可达 < EAR；CDG 上限仅 407–451 mg = EAR 的 63%–69%）；
> 且 `optimal_vs_baseline` = **0.871–1.087**，优化前后持平，
> **缺口不是优化压低的**，是基线本身就只在 EAR 的 48%–58%。
> 硬约束会直接不可行；软约束需要一个惩罚系数，而该系数没有任何数据依据，
> 只会把「结构不可达」伪装成「成本权衡」。**故不引入软约束。**
> 要真正补上钙，必须扩充决策集（乳制品/豆制品单列），属数据层工作。

处理方式保持：这类营养素**不进入机会约束**（`active_mask=False`），
但**仍参与真值评估**（`feasible_all`），两个口径都报。

> **2026-10-26 晚间补正（重要）**：上面「不可达」的判定原先有 bug——预检用 box 角点
> 算可达范围，忽略了 `G05+G06 ∈ [40,75]` 这条联合约束，因此**高估**了可达上界。
> 浙江的硫胺素就是这样被误判为「可操作」：box 下 0.83 mg ≥ 需 0.82，实际加联合约束
> 后只有 0.60 mg。它进入机会约束后每个场景必然违反，整个实例被判 INFEASIBLE，
> 而失败原因被记成「优化器解不出来」。
>
> 已改为在 `box ∩ 联合约束` 上解 LP 求可达区间（`reachable_bounds`）。修正后：
> 浙江的 `non_actionable` 变为 `[碳水化合物, 钙, 硫胺素]` 且**硬可行**；
> 7 省中只剩**山东**真正硬不可行，冲突集 `{碳水化合物, 硒}`。
> 详见 `docs/CHANGELOG_2026-10-26.md` §13。

> **2026-10-27 R307 补正（重要）：山东的「硬不可行」也是门限产物。**
> 把边界门放宽到覆盖率 0.90（K=6，多进 G04 谷物豆类、G07 水产品）后，
> 山东 `hard_feasible` 由 **False 变 True**。机制：K=4 把 G04 固定在观测基线，
> 其碳水贡献（约 236 g）进入 offset，碳水有效区间被压到 `[−25.75, 49.25]`；
> 而凑够 39.53 g 硒必然把碳水顶穿上界。G04 成为决策变量后 offset 降到 39.55，
> 区间变成 `[210.45, 285.45]`，冲突消失。
> **结论：这不是「营养需求与食物供给的真实冲突」，而是「把最大碳水来源钉死」的建模产物。**
> 原先列的三条处置（踢出主表 / 单独报告 / 放宽碳水上界）都不必执行。
> 见 `CHANGELOG_2026-10-26.md` §19.1(b)。

**3. 价格不确定性对决策零传导 —— 根因是线性目标，不是「脂肪下界 + G11 缺位」（RESOLVED 为「模型性质」，不再是待查 bug）**

> **2026-10-27 更正（CHANGELOG §21.5b）**：本条的旧归因（脂肪下界钉死 + G11 缺位）
> 解释的是「价格**水平**位移为什么不翻转」，**不是**「价格**不确定性**为什么不传导」。
> 后者有解析原因：目标对 `q` 线性、价格只进目标不进约束，于是
> `min_q E_s[c_s·q] = min_q (E_s c_s)·q`，场景平均不改变 argmin，D3 ≡ D1。
>
> 因此这条不再是「待查的 bug」，而是**模型形式决定的性质**。要让它传导，
> 必须改目标（mean-CVaR / min-max regret / 价格进约束），属建模变更，需作者裁定。
>
> 价格**水平**（省内 vs 合并，D1 vs D0）在 `k6_price` 下**确实传导**：
> 3/6 省移动，江苏 54.00 / 福建 36.41 / 江西 29.03 g/day
> （`outputs/R200_203_b2_smoke_20261027_151138`，与 R307b 独立吻合）。

> ⚠️ **2026-10-28 清理说明**：上句引用的 smoke 目录已删除，该组数字
> （江苏 54.00 / 福建 36.41 / 江西 29.03）**不可现场复算**，且下面第九轮更正已
> 说明它本身作废。需要现场证据时用 `scripts/run_b2.py --profile smoke` 重跑。
> 见 `docs/archive/CLEANUP_2026-10-28.md` 三节「风险提示」。
>
> ⚠️ **2026-10-27 第九轮更正：上面这组「3/6 省」是 RNI 下界下测的。**
> 切到 EAR 后同一对比变为 **0/6 省全部 0.0000 g**
> （`outputs/DIAG_feasible_width_20261027_164140/d1_vs_d0.csv`）。
> 即**切 EAR 把价格水平传导一起掐掉了**——这是选 EAR 的一个此前未预见的代价。
> 机制：EAR 让更多营养素变为可操作（`active_mask` 变大 → 约束变多 → 顶点更稳），
> 详见 §24.4 的顶点稳定半径。**引用「3/6 省」时必须注明是 RNI 口径。**
>
> **CVaR 通道（第九轮新增，CHANGELOG §24）**：λ 0→1 在 CDG 六省 `max|Δq|` 精确为
> 0.0000，但**不是**因为可行域被钉死（0/6 组被钉死，总宽度 236–373 g）。
> 真机制是「CVaR 对目标方向的旋转量 < 该省顶点稳定半径」：
> 旋转角 i.i.d. 下 0.44–1.12°，组特异性冲击下 8.3–16.3°；
> 稳定半径 CDG 中位 8–15°、EAT 安徽/江西/福建仅 0.5–1.0°。
> 因此**不确定性进不进决策是分省的**，判据 `θ_tail vs θ*` 已写入 §24.8 预注册规则。

以下为原始记录（**归因已作废，仅保留实测数字**）：

实测 D0（跨省合并价）与 D1（省内价）的 `q` **逐元素相同**，gap 均为 0。
此前归因为「可行域被压成近似单点」，**不准确**——顶点处恰好 K 条约束紧是 LP 常态。
真正的问题是**解对价格系数的敏感度极低**。

`scripts/diagnose_decision_sensitivity.py` 量化结果
（`outputs/DIAG_decision_sensitivity_20261026_181347`）：

| 扰动对象 | 使解移动所需幅度 |
|---|---|
| 蛋类 / 蔬菜价格 | **±50%–100% 内完全不移动** |
| 禽肉 / 红肉价格 | 20%–100% |
| 省内价 → 合并价 | **0.0 g（6 省全部）** |
| **脂肪系数** | **±10% 即移动（6/6 省）** |
| 锌 / 硒 / 能量系数 | ±10% 移动 25%–33% 的省 |

**机制（2026-10-26 晚已修正，见 CHANGELOG §18）**：

原先的解释是「脂肪下界钉死红肉量，模型退化为一个等式」。
正面检验后**只有前半成立**：

- ✅ 脂肪下界在 **6/6 省都紧**（`rel_slack` 精确为 0）；
- ❌ 「红肉量被钉住」**不成立**：红肉量省际差 26.4 g（31.5 上海 ↔ 52.2 福建），
  纯环境权重下浙江红肉 39.8 → 30.4 g，纯成本权重下江西禽肉 30.4 → 0；
- 实际卡的是**畜禽合计上界 75**（不是下界 40），六省全部顶格。

真实结构：可行域有 **12–14 个顶点**，基线解是其中**孤立顶点**（紧约束矩阵秩 = K = 4，
零空间 0 维）。三条约束在 6/6 省同时紧——**脂肪下界 + 蛋类上界 50 + 畜禽合计上界 75**，
第四条因省而异（上海=能量下界，安徽/江西=硒下界，江苏=锌下界，浙江/福建=蔬菜下界）。

所以价格传导弱的原因是**顶点间的成本排序对 ±5% 扰动稳健**（要 20%–100% 才翻转），
不是「解被唯一钉死」。一句话：**不是模型坏了，是决策空间太窄**
（K=4 且三条约束同时顶格 → 只剩少数「营养等价、成本略差」的顶点可选）。

附带更正：多目标权重**确实起作用**。纯营养权重 6/6 省复现原始解，
但纯成本在 3/6 省换解（原始解在原权重下优 1.4%–3.7%），纯环境在 6/6 省换解（22–200 g）。

**根因**：烹调油 G11 不在决策集。中国人膳食脂肪约三分之一来自烹调油，
G11 缺位后脂肪只能从肉蛋来，AMDR 下界因此变成「红肉最低摄入量」约束。

G11 被挡的直接原因：`nutrition_gate=False`，11 个营养素全部 `n_foods=0`
——**食用油在 `food_crosswalk.csv` 里根本没有映射到任何食物条目**。
（注意：不是「有食物但含量为 0」。我一度以为是 gate 把「没有这一行」误判成
「含量为零」，核对 `nutrients.csv` 后确认**不是**，gate 的判断是对的。）

**可选处置**（需作者裁定，代价从低到高）：

1. ~~补一条 crosswalk~~ **—— 不可行，已核实**（CHANGELOG §18.6）。
   `nutrition.csv` 的 50 个食物里**没有任何油**，crosswalk 无对象可映射。
   价格（`食用油(升)`，7 省 × 9 年）与消费量（`oils` 组 70 行）都在，
   **唯独营养系数缺失**。要纳入 G11 必须新增一条外部营养记录
   （如《中国食物成分表》大豆油：脂肪 ≈99.9 g/100g）+ 升→kg 密度换算（≈0.92），
   两步都引入仓库外假设，需显式标注来源并做敏感性。
   因此「最省事的选项」并不省事；
2. 重新考虑脂肪下界——AMDR 20% 是长期指导值，在 4 组模型里当硬下界等于强制红肉；
3. 场景生成器改押营养系数（`nutrients.csv` 的 `sd_per_kg`，红肉中位 CV 0.53、蔬菜 1.49），
   而不是价格 5% CV；
4. 都不动，则诚实结论是「本设计下价格不确定性对决策无影响」，需改叙事。

> **2026-10-27 R307 补正：选项 4 可以划掉了——价格传导不是「无」，是被 K=4 挡住。**
> 放宽边界门到 K=6 后，同一个 D1/D0 价差（单组最大 36%）从「6 省全部 0.00 g」
> 变成「3 省有位移，最大 54.0 g（江苏）」。
> 也就是说：**价格信号在数据里是有的，是决策维度太少把它挡在门外**。
> 这条与 §18 的「决策空间太窄」是同一件事的两个侧面，现在有了因果证据。
> 见 `CHANGELOG_2026-10-26.md` §19.1(a)。

详见 `docs/CHANGELOG_2026-10-26.md` §14。

**4. 浙江无法进入 K=4 模型 —— 已解决（RESOLVED）**

浙江禽类（G05）在零售源表整块缺失（「浙江」工作表根本没有这一行）。
已用批发价 × **品类专属**零售/批发比价桥接补齐（禽类比价中位数 1.558，
n=21 省-年）。接入采用**组级整体缺失才回退**的规则，保证其他省份系数逐位不变。

实测：K=4 齐全省份 **6 → 7**；浙江 G05 组价 31.25 元/kg
（落在江西 36.07 与福建 27.23 之间）；G06 主口径 43.92 与等权 54.43 **均未变**。

代价：浙江 G05 的 9 年价格全部是换算值（`price_source=bridged`、
`truth_eligible=False`），且比价省间跨度 1.362–2.020，需在 B4 做桥接敏感性。
详见 `docs/CHANGELOG_2026-10-26.md` §10。

### smoke 实测（预检修复后，`outputs/R200_203_b2_smoke_20261026_180400`）

> ⚠️ **2026-10-28 清理说明**：该 smoke 目录已删除，下表数字**仅存于本文档记载**，
> 不能现场复算。它描述的是 K=4 口径下"预检修复后"的中间状态，**不是当前主结果**
> （当前主结果见 `R200_203_b2_formal_20261027_222841`）。保留此表只为记录
> "K=4 → K=6 换口径"的动因。见 `docs/archive/CLEANUP_2026-10-28.md`。

| 方法 | 可行(全) | 可行(活跃) | 翻转率 | gap 均值 | 失败 |
|---|---|---|---|---|---|
| D0 | 0.000 | **1.000** | 0.000 | 0.000 | 0（山东 2 行标 `hard_infeasible`） |
| D1 | 0.000 | **1.000** | 0.000 | 0.000 | 同上 |
| D2 | 0.000 | 0.000 | 0.500 | −0.715 | 同上 |
| D3 | 0.000 | **0.833** | 0.167 | 0.109 | 江苏 2 行真失败 |

与修复前（D3 0.667 < D0/D1 0.833，方向反转）相比，**异常消失**。
现在只有江苏在 ε=0.05、S=20 下机会约束不可行：`floor(0.05×20)=1`，
只允许 1 个场景违反，容错极窄，属 S 过小的取整效应，由 R301/R302 验证。

修复前的两组数据（`_172536` RNI / `_172539` EAR）**已作废**，不应再引用：
它们的失败里有浙江的假失败（bug）与山东的真失败（结构冲突）混在一起，
无法区分。EAR 分支本身没有错，但「EAR 让失败数上升」这个观察需要重跑才能成立。

**D3 在修复后高于 D0/D1 的假设方向一致，但仍不能下结论**：场景仍是占位噪声。
D0 与 D1 仍逐元素相同（`flips=0.000`、`gap=0.000`），第 3 条结构问题未解决。

### 下一步的最小闭环

1. ~~营养边界改 EAR~~ → **已由作者裁定切 EAR**（`configs/default.yaml` 的
   `optimization.bounds_basis: ear`，`run_b2.py` 默认值同步）；
2. ~~决定钙的处置~~ → **已裁定（CHANGELOG §23）**：按可达上限报告，
   不做硬约束、不做软约束。**不再需要定惩罚系数**；
3. ~~决定山东的口径~~ → **已解决**：K=6 纳入 G04 后碳水 offset 从 275.75 降到 39.55，
   山东 CDG 硬可行（CHANGELOG §20.3）。「7 省变 6 省」的原因是上海缺 G07，与山东无关；
4. ~~决定是否放宽 K 或减少 J，让不确定性有作用空间~~ → **该前提不成立**：
   不确定性不传导的原因是**线性目标**（`min E[c]·q = min c̄·q`），与 K/J 无关。
   **第九轮已把 CVaR 这条替代路径走完**（CHANGELOG §24）：CDG 零位移，
   机制是旋转角 < 顶点稳定半径，不是 CVaR 实现有问题。
   结论：**主线用 D1 确定性 + 「零传导」的结构性论证；CVaR 放附录做稳健性**；
   **第十四轮把它钉死了**（§29.3）：λ 从 0 扫到 1，CDG 六省 Δq = 1e-9、
   均值成本与 CVaR 全部不变——**CVaR 在 CDG 是实测无效，不是「未能证明有效」**。
   附录可写成一句「已验证 λ∈[0,1] 全程不敏感」，无需曲线；
5. ~~把场景生成替换为 B1 后验~~ → **已完成（第十轮，CHANGELOG §25.1）**：
   `src/b2_scenarios.py` 的 `posterior_scenarios` 从 `cell_predictions.csv` 抽
   中心化经验残差，`E[cost]` 相对点估计偏差 8.9e-16。只扰动价格，符合裁定。
   **遗留**：后验到位后仍要按 §24.8 逐省算 `θ_tail` 与 `θ*` 比较，决定是否报告 λ 曲线；
6. ~~接入遮蔽协议（5 折 × 20 重复）替换换种子重抽~~ → **已完成（第十轮，CHANGELOG §25.2）**：
   `src/b2_protocol.py` 把 100 个协议单元转成价格位移，经 `price_overrides` 装配。
   旧路径（`--protocol reseed --scenario-source placeholder`）逐位可复现（diff 全 0）。
7. **【部分完成】裁定 EAR 让 M2 对比度归零怎么办**（CHANGELOG §25.8 + §26.8 四选一）：
   * ~~选项 4「只改指标」~~ → **已执行（第十二轮，§27）**：主指标改为 `|Δq|` 变化率，
     `flips` 降为辅助，预注册偏离已声明。换成对幅度敏感的指标后 **EAR 的零结果仍是 0**，
     说明它是干净的零结果，不是指标退化造成的假象；
   * ~~仍需裁定：①接受 EAR 零结果 ②回退 RNI ③改价格口径~~
     → **①已裁定（第十六轮，§31.6）：保留 EAR，M2 写成零结果报告**。
     依据扩到 **5 条独立证据**（前四条是扰动，第五条是真实数据修正，见 §31.3）；
   * ~~选项 3「改价格口径」~~ → **已否证（第十三轮，§28.6）**：组价改动到 21.6%
     量级，EAR 下 6 省决策一步都没动。换价格口径救不回对比度，③ 只剩数据质量含义；
   * ~~遗留「后验到位后算 θ_tail」~~ → **已完成（第十四轮，§29）**：
     9 格判定为 1 无效 / 3 边界 / 5 须报曲线；把曲线真算出来后
     **CDG 六省 λ∈[0,1] 全程 Δq=1e-9**（CVaR 实测无效），EAT 跳 128–252 g/day。
     **新增结论：CDG 不需要 CVaR，主结果用 λ=0 即可**；
8. **【新增】决定合同价格是否改用插补面板**（CHANGELOG §25.7 + §28.1）：
   现在 `price_cny_kg_full` 从未被调用，453 个缺失格靠「跳过年份」处理。
   **注意（§28.1 更正）**：`price_cny_kg_full` 是**批发价桥接**、不是 MICE 插补，
   换它不会把 B1 的点估计接进决策。要接通 B1 必须用根目录的 MICE 品类级结果
   （567 行省×品类×年）重新聚合组价，属建模变更。
   ~~另有一个独立缺陷待修~~ → **已修（第十六轮，§31.1）**：G06 三态标签，
   21 行桥接补全（+1.95%~+36.57%，中位 +25.05%），**3 行福建仍为下界**（标签显式声明，
   摊薄后只影响福建面板均值 +2.4%）。
   ~~决定合同价格是否改用插补面板~~ → **已裁定（§31.6）：不接 B1 点估计**（避免循环）。
9. **【新增】EAT 情景保留还是删掉**（CHANGELOG §29.4）：
   正式批次 `R200_203` **只有 CDG**（2400 行，无 EAT），EAT 仅用于机制说明。
   但 EAT 下 CVaR 权重从 0 拉到 1 决策跳 128–252 g/day，且跳变 λ 随样本在
   0.40–0.90 间移动、**无自然取值**。若报 EAT 点估计，必须回答「λ 为何取该值」。
   **已裁定（§31.6）：保留作定性机制对照，不报点估计。**
10. **【新增】G3 gate 要不要修——修了会从 PASS 变 FAIL**（CHANGELOG §30.3）：
    `thin` 是组级不是单元级（36 单元只有 2 个 9 年全观测、3 个只有 1 年、
    1 个零观测全靠桥接）；`collapsed` 的 45.1% 完全由 G06 缺陷构成，排除后 0.000。
    即现在的 PASS 是**用被污染 45% 的指标去检查污染**，属假通过。
    ~~需作者确认~~ → **已修（第十六轮，§31.2）**：`collapsed` 45.1%→0%，
    `thin` 加单元级门槛（覆盖率转 WARN 不 FAIL）。gate 仍 **7/7 PASS**。

**第十六轮已把 7（①②）、8、9、10 全部执行完。但当时仍不能标 DONE。**

原因是本清单漏了一条：`metrics.json` 里 `evidence_status` **仍是 `plumbing_only`**，
`placeholder_components` 还留着一条——**「真值 = 冻结合同点估计，不是遮蔽前伪完整面板」**。
这条在 §25.8 / §27 的「证据等级」表里一直写着「仍是占位」，但**没有进 DONE 清单**，
所以按清单走会误判成可以标 DONE。**这是清单本身的缺陷，本轮补上：**

> **R200–R203 标 DONE 的第 11 个条件（2026-10-27 第十七轮修订，CHANGELOG §32）：**
> 原写作「真值换成遮蔽前伪完整面板」。**查完后这条要改**——那个面板不存在可用的版本：
> 唯一的候选 `price_cny_kg_full` 是批发价桥接（278 行全部 `truth_eligible=False`），
> 且有 30%–39% 的水平断点；「只用实测」则让浙江 G05/G06 无数据、整省不可评估。
> 三条路径的**决策完全相同**（六省 `max|Δq*| = 0.00`），成本差 −10%~+4%。
> 所以真值占位是**数据边界**，不是待修缺陷。条件改为：
> **论文数据节写入 §32.5 那段披露（基准口径 + 浙江两格无实测 + 三口径不变性检验），
> 然后标 DONE-conditional。**

> **2026-10-28 结案（第十八轮，CHANGELOG §33）**：作者已裁定按建议 A 执行——
> R200–R203 标 `DONE-conditional`。`metrics.json` 的 `evidence_status: plumbing_only`
> **保持不动**：改元数据会让 hash 与内容对不上，而 `plumbing_only` 指的正是
> 「真值占位」这条已知边界，与 `DONE-conditional` 说的是同一件事，只是措辞不同。
> 放行条件写死在下节，**引用这两个批次时必须同时引用下节**。

M3 网格（R300–R303）已全部跑完，且在**旧 G06 价格**下跑；因为决策不动（§31.3），
「结构性冲突」与「单调性方向」两类结论不受影响，但成本轴绝对水平会差 0.2–2.6%。
**不重跑**（按 `TO_DECIDE.md` 第三节建议 A 执行；作者可随时否证）：论文中标注「M3 成本轴基于
G06 修正前面板，决策结论不受影响」。理由是重跑约 30 min 而结论不会变（§31.3 已证）。

---

## R200–R203 的定稿条件（`DONE-conditional`）

**状态**：`DONE-conditional`；证据等级 `formal_conditional`。
**产物**：EAR `outputs/R200_203_b2_formal_20261027_222841`、RNI `outputs/R200_203_b2_formal_20261027_224315`
（各 2400 行 = 4 方法 × 600 协议重复，`DONE` 齐备）。

**放行条件（三条，缺一不可）**：

1. **基准口径披露**——数据节写明「基准是省内**可获得年份**的观测均价（中位 5 年、范围 1–9 年），
   不是 9 年均价」；36 个 (省,组) 单元里只有 2 个是 9 年全观测。
   依据 `DIAG_price_coverage_20261027_193323` 与 §30.8。
2. **真值边界披露**——写明「浙江 G05/G06 无实测、价格来自批发价桥接」，并报告三口径不变性检验：
   主口径 / `price_cny_kg_full` / 仅 `truth_eligible` 下六省 `max|Δq*| = 0.00`，成本带 −10%~+4%。
   依据 §32。
3. **不引用开关读数**——RNI 附录只报机制与区间（`D0 变化率` 0.460–0.498），
   **不得报「D0≠D1 的省份名单」**：D0 是二值开关，名单随价格构造整套翻转。依据 §31.8。

**为什么不是 `DONE`**：第 1、2 条边界不可能通过重跑消除（缺的是统计年鉴的分品类价），
它们是**披露义务**而不是待修缺陷。标 `DONE` 会让「可无条件引用」的语义失真。

**为什么不是 `PARTIAL`**：`PARTIAL` 的语义是「还有可补救的预注册条件未满足」。
§32 已证明三条候选真值口径下决策完全相同，补救不存在；继续挂 `PARTIAL`
只会让 M4/M5 无限期阻塞。

**回退方式**：把 R200–R203 四行状态改回 `PARTIAL`、删除本节的放行结论即可；
**本轮未改任何 run 产物**，`metrics.json` 与 `b2_results.csv` 无需回滚。



