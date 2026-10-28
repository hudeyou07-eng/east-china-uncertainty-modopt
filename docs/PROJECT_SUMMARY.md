# 项目总结与重要改动（2026-10-28）

> **这是给共创者的唯一入口文档。** 它把 2026-10-23 至 10-28 的全部重要改动、
> 最终结论、关键决定、已知限制与复现方式收在一处。
> 更细的逐轮推导在 `CHANGELOG_2026-10-26.md`（按 § 号反查），逐 run 状态在
> `EXPERIMENT_TRACKER.md`（唯一台账，46 run 全结案）。
>
> **English abstract.** This repository studies whether dietary-optimization advice for East China
> stays directionally stable when price, consumption, nutrient and environmental data are incomplete
> or misaligned in granularity. All 46 pre-registered runs are closed (42 `DONE`, 4
> `DONE-conditional`). Under the EAR nutrition lower bounds the main result is a **clean null result**:
> five independent perturbations of the price layer move **none** of the six decision provinces.
> What does move decisions is the *feasible region* (boundary variants), not uncertainty.

---

## 1. 项目在做什么

**问题**：在价格、消费、营养、环境四类数据都不完整、且粒度互相错位时，华东地区的膳食优化建议
（哪个食物组该多吃、哪个该少吃）**会不会因为补数据的方式不同而翻转**？

**主张**：后验场景 + 逐地区联合营养机会约束，能降低确定性填充造成的建议翻转。
**实际结论**：在最关键的 EAR 口径下，价格侧的不确定性**推不动顶点**，因此得到的是
「稳健」而不是「更优」——这个结论本身是论文的正面产出，但必须按零结果来写。

## 2. 三层口径（混了就会读错）

| 层 | 取值 | 用途 | 定义在哪 |
|---|---|---|---|
| 合同口径 | **K=4**（G02 蛋 / G05 禽肉 / G06 红肉 / G08 蔬菜） | 七个合同文件与 7 条 gate 验的就是这张表 | `data/processed/group_audit.csv`，`EXPERIMENT_PLAN.md` §3 |
| **决策口径（主）** | **`k6_price`，K=6**（+G04 谷物豆类 +G07 水产），**6 省** | 模型实际用的 | `configs/default.yaml: optimization.decision_scope` |
| 营养下界口径（主） | **EAR** | 决策约束 | `configs/default.yaml: bounds_basis` |

上海在 `k6_price` 下出局（G07 水产品整块缺失），所以决策是 6 省不是 7 省。
报「几省」「K 多少」之前，先确认说的是哪一层。

## 3. 最终结果

### 3.1 B0 数据与求解器自检（R000–R006）

7 项全部通过：69 项自动化测试、7 地区/14 组/882 格的审计、`onto-v1.0.0` 冻结、
合同 gate **7/7**、5 条可手算的 LP fixture（内点/双紧/上界紧/不可行/无营养约束语义）、
同 seed 结果哈希一致（`ab9e5ed14ce2ad36`）、非法输入显式失败。

### 3.2 B1 插补标定（R100–R109）

两个面板（价格、消费）× 3 种遮蔽几何 × 5 折 × 20 重复 × 4 方法。核心结论三条：

| 结论 | 证据 |
|---|---|
| **点精度与区间标定不是同一件事** | 价格面板 consecutive_years：MICE sMAE 0.127 最低，但 cov95 0.840；`hierarchical_rw` sMAE 0.168 更差、cov95 **0.955** 最接近名义值 |
| **MICE 在整块缺失下崩溃** | province_group：价格 sMAE **1.182** / cov95 **0.733**；消费 sMAE **1.000** / cov95 **0.079**。这是 B1 最硬的一条 |
| **覆盖好 ≠ 无偏** | MAR 敏感性 12 个 (遮蔽 × 方法) 的 bias slope **全为负**；主方法 single_cell −0.455，Q5 平均低估 8.66 元/kg（≈11%） |

一个反复出现的陷阱：`interpolation` 与 `group_mean` 在 province_group 遮蔽下**逐格同值**
（1200/1200，差 < 1e-9），所以「interp 欠覆盖」实为「组均值欠覆盖」，不能读作方法差异。

### 3.3 B2 决策可靠性（R200–R203，`DONE-conditional`）

**主结果是干净的零结果。** EAR 下 D0 ≡ D1 ≡ D3（逐位相同），只有 D2（无营养约束）不同：

| 口径 | 方法 | 可行(活跃) | `dq_change_rate`（主指标） | gap 均值 |
|---|---|---|---|---|
| EAR | D0 / D1 / D3 | 1.000 / 1.000 / 1.000 | **0.000 / 0.000 / 0.000** | ≈0 |
| EAR | D2 | 0.000 | 1.000 | −0.8035 |
| RNI | D0 | 1.000 | **0.460**（开关读数） | 0.00347 |
| RNI | D1 / D3 | 1.000 | 0.013 / **0.333** | 0.00018 / 0.00044 |
| RNI | D2 | 0.000 | 1.000 | −0.8085 |

五条独立证据都指向「0/6 省」：遮蔽协议位移（0.298%）、合并价 vs 省内价（15–65%）、
观测 vs 桥接口径（中位 2.6%、最大 21.6%）、CVaR 权重 λ 0→1（Δq = 1e-9）、
**真实数据修正（组价 +1.95%~+36.57%，中位 +25.05%）**。

机制：**顶点稳定半径 ≫ 扰动幅度**。价格只进目标不进约束，`min E[c]·q = min c̄·q`，
且解被边界 + 营养约束钉在顶点上（CDG 单组价格半径最小 20%，是协议位移的 67 倍）。

**为什么标 `DONE-conditional` 而不是 `DONE`**：真值仍是冻结点估计（浙江两格无实测）。
§32 已证明三条候选真值口径下决策**完全相同**（`max|Δq*| = 0.00`），差别只在成本 ±10%——
这是**数据边界**而非待修缺陷，因此以「三条披露义务」放行，`metrics.json` 一字未改。

### 3.4 M3 敏感性网格（R300–R307b）

| 结论 | 数 |
|---|---|
| 机会约束的净贡献 | 可行率 0% → 100%，代价是 17% 实例（江苏）不可行 |
| 场景数平台 | 可行率 **S=25 起恒定 83%**，S=200 是拐点（原假设「S 太小」被推翻） |
| ε 网格 | 成功率 56→72→**83→83%**（0.05 后饱和）；江苏需 ε≈0.30（硒余量仅 6.0%） |
| 目标权重 | 原权/等权 可行率 83%/83%，最大 `|Δq|` 18.23 g/day，无「按结果挑权重」风险 |
| 权重不确定性 | κ=20 平均遗憾 0.06%；κ=5 为 0.28%。**权重不是主要不确定性来源** |
| joint vs marginal | joint 实测违反率**精确等于 ε**；marginal 是 1.5–1.8 倍，且 1800 个二元变量算不动 |
| Big-M | tight 与 global 解逐位相同、耗时差 <2%（toy 规模无收益，保留作防御默认） |
| 边界门 | 放宽到覆盖率 0.90 → K=6：G04 解决山东硬不可行，**G07 恢复价格传导**，两者都与 K 大小无关 |

### 3.5 M4 分省与三层敏感性（R400–R409）

| run | 内容 | 结果 |
|---|---|---|
| R400/R402–R406 | 6 省 × 3 情景方向标签 | 18 格 15 解（EAT 的山东/江苏/浙江硬不可行）；**一致率均值 0.956**；90 个组格 = up 36 / down 49 / neutral 1 / **data-sensitive 4** |
| R401 | 上海可得性报告 | G07 **0/9 年**、桥接表 9 品类**无水产品** → `k6_price` 不可装配；`k4_official` 可装配，仅作附录 |
| R407 | 逐省留一（只重算池化价） | 75 格全解；**6 格翻向，全在 EAT**（安徽/江西/福建），339.3–341.7 g/day；其余 69 格 0 |
| R408 | δ 作用于残差对数域 | δ=±0.5 vs δ=0：`max|Δq|` 中位 **1.4e-11**、最大 **2.3e-9** |
| R409 | 边界网格 low/mid/high/worst | 24 格：12 解（mid+high）、**low 6 格求解不可行（HiGHS Status 8）**、**worst 6 格空盒**；high 位移 43.7–92.05 g/day |

**三条可直接进 B4 的结论**：

1. **价格类扰动不改变决策**（R408 位移 ~1e-9；R407 仅 EAT 局部翻向）；
2. **EAT 是唯一不稳的情景**（全部 4 个 `data-sensitive` 与 6 个翻向格都在 EAT），
   只能作定性对照，**不进结论门**；
3. **边界变体改的是可行域本身**（low/worst 6 省全不可行），与「稳健性」不是同一类证据，
   必须分开报。

### 3.6 M5 交付与可复现性（R500–R505）

- 表 1（双面板标定）、表 2（双口径决策）、图 1（标签分布）、图 2（CDG 地区热图）、附录清单；
- 图 1/图 2 为**英文标注的纯 SVG**（不引入 matplotlib），数据另存 CSV 供重绘；
- R505 自动化部分 **PASS**：合同哈希 10/10 零漂移、13 个关键目录完整、69 tests OK、tracker 15/15。
  **干净环境复跑未执行**（需仓库外 clone + 新建 venv + 联网），命令与判据在
  `outputs/R505_reproducibility/RUNBOOK.md`，报告中列为 `not_verified`。

## 4. 关键决定（12 条）

| # | 决定 | 取值 | 主要依据 |
|---|---|---|---|
| 1 | 营养下界口径 | **EAR**（钙 650 / 铁 12 / 锌 8.25 / 硒 50 / 硫胺素 1.1 / 核黄素 1.1 / 烟酸 11） | RNI 是「覆盖 97.5% 个体」，不是人均应达下界 |
| 2 | 钙的处置 | 按**可达上限**报告，不做硬/软约束 | 18/18 格钙均不可达（结构问题）；`optimal_vs_baseline` 0.871–1.087，缺口非优化造成 |
| 3 | 不确定性是否进决策 | **分省判定**（`θ_tail` vs `θ*`） | CDG 六省 λ∈[0,1] 全程 Δq=1e-9；EAT 三省阶跃 128–252 g/day 且无自然 λ |
| 4 | 场景扰动对象 | **只扰动价格**（`cv_nutrient: 0.0`） | 食物成分表是物理常数 |
| 5 | M2 指标主次 | `\|Δq\|` 变化率为主，`flips` 降辅助 | 预注册偏离，须专节声明 |
| 6 | 价格口径能否救回对比度 | **否证** | 组价改动到 21.6% 量级，EAR 下 6 省决策一步没动 |
| 7 | CDG 要不要 CVaR | **不要** | λ 扫满决策逐位不变（实测无效，不是「未能证明有效」） |
| 8 | G06 部分结构聚合 | **桥接补全 + 完整结构加权**，三态标签 | 24 行权重质量损失 21.2%/7.6%，低估中位 21.7% |
| 9 | G3 的 thin / collapsed | **单元级门槛 + 排除部分结构**，覆盖率转 WARN | collapsed 45.1% 全由 G06 缺陷构成，排除后 0.000（原为假通过） |
| 10 | EAT 的定位 | **只作定性机制对照，不报点估计** | 跳变 λ 随样本在 0.40–0.90 间移动 |
| 11 | 真值口径 | **不换**，标 `DONE-conditional` + 三条披露 | 三条候选真值决策完全相同；唯一「伪完整」面板 278 行全部 `truth_eligible=False` |
| 12 | 上海口径 | **不进决策层**，改可得性报告；`k4_official` 单点仅作附录 | 加入上海会改变其余 6 省 D0 池化价，作废 RNI 附录全部读数 |

## 5. 五条必须带进论文的陷阱

1. `interpolation ≡ group_mean`（province_group 下 1200/1200 同值）——那是组均值的欠覆盖。
2. RNI 下 **D0 是二值开关**，「哪几省不同」的名单会随价格构造整套翻转；只报率（0.460–0.498），不报名单。
3. `objective_gap` 用逐目标 payoff 区间归一化，**不可跨价格面板版本比较**。
4. `use_chance_constraint=False` 会**连营养约束一起删掉**（那正是 D2 的定义）；
   确定性解必须 `use_chance_constraint=True, epsilon=0`，否则静默得到「全 0」最优解。
5. 主指标是 `|Δq|` 变化率，不是 `flips`（预注册偏离）。

## 6. 产物、复现与校验

### 6.1 目录约定

```
data/processed/     合同文件（7 件）+ 审计表 + manifest
outputs/            运行产物（44 个目录 / 747 个文件 / 约 9 MB）—— **已纳入版本控制**
artifacts/          小体量、人工复核过的证据与修复前备份
docs/               方案 / 台账 / 总结 / 证据（archive/ 为历史留痕）
scripts/ src/ tests/ 代码
```

> **`outputs/` 现在随仓库交付**（2026-10-28 决定）。克隆后即可直接复核 tracker、
> 数值断言与论文图表，不必先重跑约 1.5 小时的实验；
> 需要复算时按 6.2 重跑即可，产物可重建、不构成唯一副本。

### 6.2 复现命令

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python -m unittest discover -s tests            # 期望 69 tests OK
python scripts/check_contract_gates.py          # 期望 7/7 PASS
python scripts/check_tracker.py                 # 期望 15 项（需 outputs 存在）
python scripts/verify_tracker_numbers.py        # 27 条数值断言
python scripts/run_b2.py --bounds-basis ear     # B2 主批次（约 25 min）
python scripts/run_m4.py --block provinces      # M4 主批次
python scripts/build_paper_artifacts.py --exact # 表/图
python scripts/verify_reproducibility.py --exact --force
```

### 6.3 三道门禁

| 门禁 | 验什么 | 不验什么 |
|---|---|---|
| `check_tracker.py [--file]` | 引用可解析、目录无遗漏、计数自洽、证据等级词表 | 数字对不对 |
| `verify_tracker_numbers.py` | 27 个关键数字逐条对回产物 | 结构 |
| `verify_reproducibility.py` | 合同哈希零漂移、关键目录完整、测试、tracker | 干净环境复跑（人工） |

## 7. 数据边界与已知限制

1. **价格覆盖率**：36 个 (省,组) 单元只有 2 个是 9 年全观测，中位 5 年，3 个只有 1 年，
   1 个零观测全靠桥接。**论文数据节必须披露**。
2. **真值口径**：浙江 G05/G06 无实测；三条候选真值口径决策相同、成本带 −10%~+4%。
3. **G06 福建 3 行仍是下界**（`structure_weighted_partial_lowerbound`），桥接表对福建零覆盖。
4. **EAT 三省硬不可行**（山东/江苏/浙江，冲突集「碳水化合物+硫胺素」）——既有结构问题。
5. **R409 只覆盖 box**，联合约束 `G05+G06∈[40,75]` 未做变体。
6. **`feasible_all` 恒为 0**：钙在 18 个格子全部不可达，可行性只报 `feasible_active`。
7. **G11 食用油不在决策集**（无营养系数），脂肪下界因此等价于「红肉最低摄入量」约束。
8. **权重为全国口径、2023 单年**（猪 0.788 / 牛 0.136 / 羊 0.076），表观消费含流通损耗。

## 8. 仍未完成

| 项 | 状态 | 说明 |
|---|---|---|
| 干净环境复跑（R505 人工部分） | 未做 | 需仓库外 clone + 新 venv；命令在 `RUNBOOK.md` |
| 论文正文与「预注册偏离」专节 | 未写 | 指标换轨、K 3→4→6 都需声明 |
| B4 价格口径敏感性（商务预报批发价） | 未开工 | 唯一未动的预注册外延伸项 |
| 图 1 / 图 2 人工视觉核对 | 未做 | 机器只能验「不越界、无中文」，排版美观需人眼 |

## 9. 变更大事记（2026-10-23 → 10-28）

| 阶段 | 做了什么 | 关键产出 |
|---|---|---|
| 10-23 ~ 10-25 | 仓库骨架、数据合同、B0/B1 首轮 | 7 件合同文件、7 条 gate、MICE 对照 |
| 10-26 审计 | 全项目审计，P0/P1/P2 分级 | `AUDIT_2026-10-26.md`（已归档）；C1 改写、CDG 口径修订 |
| 10-26 晚 | 结构诊断：紧约束、顶点、目标退化 | §18 推翻「脂肪下界钉死红肉」的一半解释 |
| 10-27 上午 | 口径落地：K=6、EAR、钙按可达上限 | §20–§24；可行率不可跨口径比较 |
| 10-27 下午 | B1→B2 接线、主指标换轨、价格面板审计 | §25–§30；零结果 + 五条证据 |
| 10-27 夜 | 真值口径查证、D0 二值开关 | §31–§32；M2 定稿条件成型 |
| 10-28 | 清理 163 个中间目录；tracker 变可核对账本；M2 定稿；M4 全部结案；M5 交付 | §33–§37；46 run 全部 `DONE`/`DONE-conditional` |
| 10-28 晚 | 英文图 + 数值门禁；图 1 图例越界修复；台账收敛为单一中文版 | §38–§39；`verify_tracker_numbers.py` |

## 10. 文档地图

| 想知道 | 看 |
|---|---|
| 现在到哪了 | 本文 §3（结果）+ §8（未完成） |
| 逐 run 状态与产物 | `EXPERIMENT_TRACKER.md`（唯一台账） |
| 为什么这么设计 | `EXPERIMENT_PLAN.md`（含修订 R-2026-10-26-a/b、R-2026-10-28-c/d） |
| 某个数字怎么来的 | `CHANGELOG_2026-10-26.md` §1–§39（按 § 号反查） |
| 价格面板哪一版 | `PANEL_LEDGER.md` |
| 历史审计 / 裁定 / 清理台账 | `archive/`（正文仍按原文件名引用） |

---

**维护约定**：改 tracker 或数字后，依次跑
`check_tracker.py` → `verify_tracker_numbers.py` → `unittest`；
三门全绿才提交。

---

## 11. 文档整理记录（2026-10-28，为对外交付）

整理原则：**删内容已被吸收的重复件，归档有独立证据价值的历史件，绝不动被正文引用的证据链。**

| 处理 | 文件 | 理由 |
|---|---|---|
| **新建** | `PROJECT_SUMMARY.md`（本文）、`docs/README.md` | 前者是唯一入口，后者是文档地图 |
| **删除** | `HANDOVER_2026-10-28.md` | 交接内容已全部并入本文 §2–§8；全文无其他文档引用它 |
| **删除** | `.Rhistory` ×2 | 0 字节会话残留 |
| **归档** | `AUDIT_2026-10-26.md`、`DECISIONS_2026-10-27.md`、`CLEANUP_2026-10-28.md`、`TO_DECIDE.md` → `archive/` | 历史留痕：正文仍以原文件名引用（尤其 4000 行 CHANGELOG 的 § 引用），改名或删除会让历史引用失效 |
| **保留** | `CHANGELOG_2026-10-26.md` | 逐轮证据链本体，被正文以 § 号引用 ~100 处 |
| **清理** | 583 个 `__pycache__`、一次性脚本 | 运行时缓存与本次整理用的临时脚本 |

整理后 `docs/` 结构：

```
docs/
├── README.md                  文档地图
├── PROJECT_SUMMARY.md         唯一入口（本文）
├── EXPERIMENT_PLAN.md         预注册方案 + 4 条修订
├── EXPERIMENT_TRACKER.md      逐 run 台账（唯一版本）
├── CHANGELOG_2026-10-26.md    逐轮证据链 §1–§39
├── PANEL_LEDGER.md            价格面板版本台账
├── Research_Proposal.docx
└── archive/                   4 份历史文档（AUDIT / DECISIONS / CLEANUP / TO_DECIDE）
```

> **上传说明**：为便于协作者直接复核，`.gitignore` 已放行 `outputs/`
> （44 个运行目录、747 个文件、约 9 MB），仅排除 `.venv/`、缓存与会话残留。
> 克隆后 `check_tracker.py`、`verify_tracker_numbers.py`、`verify_reproducibility.py`
> 三门应直接全绿，无需先重跑实验。
