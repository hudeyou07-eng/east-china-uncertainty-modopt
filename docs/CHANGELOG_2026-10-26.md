# 变更记录 · 2026-10-26

> 本文件逐条标注 2026-10-26 当日的全部改动，供代码审阅与 GitHub 共创。  
> 每条都写明：**改了什么、为什么改、审阅时该看哪里**。  
> 涉及预注册条款的改动不在本文覆盖，见 `docs/EXPERIMENT_PLAN.md` §1.1 的两条修订记录。

## 一、一句话摘要

把 B2 数据合同从「文档里写了」变成「磁盘上可验证」：  
补齐 7 个冻结文件 + 2 个附属产物，把 Plan §3 的七条 gate 翻译成可执行断言（实测 **7/7 通过**），  
并把 G06 红肉的组内聚合从「三品类等权」改为**按消费结构加权**（猪 0.788 / 牛 0.136 / 羊 0.076），  
三个维度共用同一套权重。

复现命令：

```bash
python scripts/build_contract_files.py   # 重建 + 验收 + 回写 manifest + 落 R002 run
python scripts/check_contract_gates.py   # 单独复跑七条 gate
```

最近一次 run：`outputs/R002_group_freeze_20261026_164944`（gate 7/7）

---

## 二、新增文件


### 2.1 代码

| 文件                                 | 行数  | 作用                                                                      | 审阅要点                                                                                |
| ---------------------------------- | --- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `src/ontology.py`                  | 204 | **单一本体源**：12 组 × 五维度（价格/消费/营养/LCA/全球环境）映射 + 阈值常量 + `ONTOLOGY_VERSION`   | 这是全项目唯一的组定义来源。此前 `build_group_audit.py`、`scenario_decision_space.py` 各自内联了一份，且内容不一致 |
| `src/component_weights.py`         | 73  | 消费结构权重加载器：读外部 CSV、校验和 = 1、提供三个维度的标签映射                                   | `load_weights()` 有硬断言，权重和不为 1 直接抛错；`weights_for()` 对未声明的组返回 `None`（退化为等权）           |
| `scripts/build_contract_files.py`  | 644 | **一条命令闭环**：重建审计表 → 汇总 9 个产物 hash → 跑七条 gate → 回写 manifest → 落自包含 run 目录 | 三个口径（primary / preregistered_k3 / sensitivity_c0.90）在 `SCOPES` 常量里定义，改口径只改这里        |
| `scripts/check_contract_gates.py`  | 315 | Plan §3 七条 gate 的可执行断言                                                  | G3 的「等于最低价比例」、G6 的联合约束按 `bound_type` 展开校验，是最容易出错的两处                                 |
| `scripts/build_decision_bounds.py` | 251 | 决策边界，8 列 schema（含 `bound_type` / `source` / `note`）                     | 259 行 = 单组 252 + 联合 7；`validate()` 校验每个省×情景展开后覆盖全部 12 组                             |
| `scripts/build_environment.py`     | 229 | 环境系数，双数据集（`global_pn` 主口径 / `china_lca` 对照）                             | `_hierarchical_mean()` 的 `WEIGHTED_GROUPS` 分支；`aggregation` 列逐行标注实际方法               |
| `scripts/build_group_prices.py`    | 191 | 组级价格，结构加权 + 缺失品类归一                                                      | 四个敏感性列并存，见 §3.2                                                                     |
| `scripts/build_nutrients.py`       | 172 | 组级营养系数，结构加权                                                             | 痕量（`trace`）按 0 计入，与 `missing` 严格区分                                                  |

### 2.2 数据

| 文件                                                   | 作用                       | 审阅要点                                      |
| ---------------------------------------------------- | ------------------------ | ----------------------------------------- |
| `data/input/external/meat_consumption_structure.csv` | 2023 年猪/牛/羊产量、进口、表观消费与份额 | **新增的外部依据**。此前仓库内没有任何数据支撑品类权重，是本次最需要复核的一条 |

内容：

| 品类 | 产量(万吨) | 进口(万吨) | 表观消费(万吨) | 份额     |
| -- | ------ | ------ | -------- | ------ |
| 猪肉 | 5794   | 155.00 | 5949.00  | 0.7879 |
| 牛肉 | 753    | 274.00 | 1027.00  | 0.1360 |
| 羊肉 | 531    | 43.36  | 574.36   | 0.0761 |

来源：国家统计局 2023 年统计公报（产量）+ 海关总署 2023 年进口统计（不含杂碎）。  
表观消费 = 产量 + 进口，忽略出口与库存变化。

### 2.3 文档

| 文件                             | 作用                                                  |
| ------------------------------ | --------------------------------------------------- |
| `docs/AUDIT_2026-10-26.md`     | 全项目审计报告：进度 / P0 影响结论正确性 / P1 口径不一致 / P2 卫生问题 / 建议顺序 |
| `docs/CHANGELOG_2026-10-26.md` | 本文件                                                 |

### 2.4 冻结产物（`data/processed/`）

Plan §3 规定的 7 个 + 3 个附属：

```
group_audit.csv                    2910 B   a62fa3b44f9c3e4d
baseline_consumption.csv          25374 B   d6936e7fdddf3eaa
group_prices.csv                  83754 B   5357094356a8c410
nutrients.csv                     18197 B   9b302d6cb804ac51
environment.csv                   14322 B   c6437a46aab3b920
decision_bounds.csv               34991 B   a4e401dc8fb85488
model_manifest.json               473 行    （自哈希不适用）
ontology.csv                       1392 B   3af7394ebc4e3a1e
group_audit_k3_strict.csv          2961 B   6a316d077b2e844a
group_audit_sensitivity_c0.90.csv  2831 B   8a06727298a37a76
contract_gate_report.json          gate 报告
```

---

## 三、修改文件

### 3.1 本体统一（消除两套矛盾定义）

| 文件                                   | 改动              | 说明                                                                                                                                             |
| ------------------------------------ | --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/build_group_audit.py`       | **−136 行**（净删除） | 删掉内联的 `ONTOLOGY`、`HARD_NUTRIENTS`、`ENV_METRICS`、`MIN_*` 常量副本，改为 `from src.ontology import ...`。此前这份副本与 `src/ontology.py` 内容不一致，是「同一份数据两套定义」的根源 |
| `scripts/scenario_decision_space.py` | ±32 行           | 同上，去掉硬编码的 `HARD_ALL` 与 `ONTOLOGY` 列表，改为 import；补 `sys.path` 注入                                                                                 |
| `data/processed/ontology.csv`        | 26 行变更          | 新增 `global_env_subgroups` 列，使 `environment.csv` 的组内聚合规则可从产物反查                                                                                  |
| `data/processed/group_audit.csv`     | 26 行变更          | 同上                                                                                                                                             |

**审阅要点**：`ontology.csv` 的 hash 从 `de66ae4b` 变为 `3af7394e`，是因为加了列。  
第一次改 `ontology.py` 时 hash 没变——原因是 `build_group_audit.py` 的 DataFrame 构造没导出新字段，  
这个坑已在本次修复。


### 3.2 G06 组内聚合：等权 → 消费结构加权

三个维度**共用** `src/component_weights.py` 的同一套权重。理由：  
组级系数应满足 `p̄ = Σ p_i·q_i / T`，即权重等于消费份额。

| 文件                              | 改动                                                                                   |
| ------------------------------- | ------------------------------------------------------------------------------------ |
| `scripts/build_group_prices.py` | 主口径从「可用品类等权」改为结构加权；缺失品类按已观测品类**重新归一**（条件期望），不丢数据也不退化。新增 `price_structure_weighted` 列 |
| `scripts/build_nutrients.py`    | 组内聚合从等权改为结构加权；新增 `aggregation` 列逐行标注                                                 |
| `scripts/build_environment.py`  | `_hierarchical_mean()` 加 `group_id` 参数，`WEIGHTED_GROUPS` 命中时按结构加权，否则层级等权             |

**实测影响**（G06，等权 → 结构加权）：

| 维度/指标                         | 等权      | 结构加权        | 变化     |
| ----------------------------- | ------- | ----------- | ------ |
| 价格 (元/kg)                     | 54.43   | **43.92**   | −19.3% |
| 环境 ghg (kg CO2e/kg)           | 39.47   | **21.75**   | −44.9% |
| 环境 land (m²/kg)               | 190.63  | **66.94**   | −64.9% |
| 环境 eutrophication (g PO4e/kg) | 168.95  | **112.91**  | −33.2% |
| 环境 freshwater (L/kg)          | 1893.78 | **1835.36** | −3.1%  |
| 营养 能量 (kJ/kg)                 | 10023   | **14235**   | +42.0% |
| 营养 脂肪 (g/kg)                  | 184.3   | **308.0**   | +67.1% |
| 营养 蛋白质 (g/kg)                 | 173.7   | **145.5**   | −16.2% |
| 营养 铁 (mg/kg)                  | 24.00   | **18.84**   | −21.5% |

**这是本次最需要复核的结论**：等权并不是中性先验，它等价于假设  
"中国人吃的红肉有三分之二是牛羊肉"。此前文档里写的"等权偏高、方向偏保守"  
只对成本与环境成立，**对营养维度是反方向的**——等权把能量与脂肪低估了 42% / 67%。

价格演进路径：38.80（主导品类=猪肉=最低价）→ 54.43（等权）→ **43.92**（结构加权），  
落在最低价与严格等权 67.45 之间，符合预期。

### 3.3 文档同步

| 文件                           | 改动                                                                                    |
| ---------------------------- | ------------------------------------------------------------------------------------- |
| `docs/EXPERIMENT_PLAN.md`    | **+60 行**，新增 §1.1 预注册修订记录，两条修订（见 §四）。原条款保留不删                                          |
| `docs/EXPERIMENT_TRACKER.md` | +146 行：R002 行更新为 K=4；B2 合同状态表 7 行全部更新为实测结果；「待人工复核的口径决策」5 条重写；「组内聚合口径」整节重写（含权重来源表与影响表） |
| `README.md`                  | 口径说明改为结构加权，附"等权不中性"的量化说明                                                              |
| `data/README.md`             | 三张表的聚合方式描述同步；登记外部权重文件                                                                 |
| `data/DATA_MANIFEST.json`    | 13 个输入（新增 `meat_consumption_structure.csv`），含字节数与 SHA256                              |

---

## 四、预注册修订（`docs/EXPERIMENT_PLAN.md` §1.1）

两条都**不覆盖原文**，而是并列记录「原文 / 修订后 / 依据 / 日期」。

### R-2026-10-26-a｜C1 最小可信证据的措辞

```
原文：层级模型的点误差不劣于强基线，且 80%/95% 区间覆盖接近名义覆盖；硬约束违反率为 0
修订后：层级模型的 80%/95% 区间覆盖接近名义覆盖；点误差在部分缺失几何下允许劣于强基线，
        但必须同时证明基线在该几何下不稳健。硬约束违反率为 0
```

依据：三种缺失几何的实测表（`single_cell` / `consecutive_years` / `province_group`）。  
在 `province_group` 下 MICE 的 sMAE 反而劣于均值填充，但覆盖率同时崩到 0.733——  
按原文措辞这条会被判为不成立，而实际发生的是「精度换校准」。

### R-2026-10-26-b｜主口径 K 从 3 改为 4

```
原文：trace_as_valid=False，痕量不算有效观测，G06 红肉因营养 10/11 被排除，K=3
修订后：trace_as_valid=True（痕量按真实近零计入），G06 纳入，K=4（G02/G05/G06/G08）
```

依据：CDG 情景约束对象是「畜禽肉合计 40–75 g」，7 省中 6 省红肉单独已达 82.9–94.4 g/天、  
畜禽肉合计 91.8–130.6 g/天全部超上限。若红肉不进模型，禽肉须满足的剩余区间为负  
（上海 [−46.5, −11.5]），**CDG 情景不可满足**——这不是缺数据，是 K=3 与 CDG 约束互斥。

代价：一个痕量格（羊肉碳水化合物）决定了红肉能否进入优化，必须在论文显式报告并做敏感性。  
原 K=3 口径保留为 `group_audit_k3_strict.csv`。

---


## 五、未解决的问题（留给协作者）

按严重性排序，均未在本次处理：

| # | 问题                                                                                                                                                 | 影响                                                                                                                                                   |
| - | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | **G3 断言余量只剩 4.9 个百分点**：G06 的 51 个省-年观测中 23 行只有猪肉单品类，归一后组价仍等于猪肉价，实测比例 45.1%（阈值 <50%）                                                                | 若面板覆盖恶化到 50% 以上，G06 组价实质退化为猪肉价，主结论不成立。只能靠插补解决                                                                                                        |
| 2 | **B1 只跑价格面板**：config 无 consumption 路径，R103–R105 无法执行                                                                                               | C1 关于数据层可靠性的证据只覆盖一半                                                                                                                                  |
| 3 | **G07 水产仍是实体扁平等权**：Fish (farmed) 13.63 与 Prawns (farmed) 26.87 平均成 20.25                                                                           | 虾排放高于鱼而鱼类消费更多，20.25 可能偏高。水产消费结构缺可靠公开依据，未编造权重                                                                                                         |
| 4 | **干净克隆缺 8 个文件，无法重建合同**：`src/ontology.py`、`src/component_weights.py`、6 个 `build_*` / `check_*` 脚本均未 `git add`                                       | 已用 `git archive HEAD` 模拟克隆验证：克隆里 `src/` 只有 8 个旧模块、`scripts/` 没有合同构建器，`python scripts/build_contract_files.py` 直接不存在。5 个冒烟测试在克隆里仍能通过                  |
| 5 | **`data/processed/` 有 27 个历史 `group_audit_*` 变体**（`_chk` / `_relax` / `_baseline_check` / `_notrace_c0.80~1.0` / `_trace_c0.80~1.0`），与 3 个正式产物命名撞车 | 审阅时极易误取。已核实这些变体的 `include` 决策与当前脚本**完全一致**（只是 schema 从 18/22 列变 23 列），属于合法的阈值敏感性证据，故不删；已在 `data/processed/README.md` 明确区分「当前合同产物 11 个」与「历史扫描产物 27 个」 |
| 6 | **7 个脚本硬编码输出目录**，违反 Plan §9                                                                                                                        | 换机器跑会写到固定路径                                                                                                                                          |
| 7 | **Plan §6 的 run 区间大于实际定义**：M1 声明到 R112 只定义到 R109；M4 到 R423 只到 R409                                                                                 | 15 个空槽位属于预注册缺口，需作者补定义                                                                                                                                |
| 8 | **G11 排除原因表述错误**：写"0/11 项达标"，实为 `nutrition_groups` 为空、根本没映射                                                                                        | 不影响结论，影响可读性                                                                                                                                          |
| 9 | **`price_observations` 口径未定义**（G06：审计表 106 vs 组价表 51）                                                                                              | 两个数都对，但含义不同，需在文档里说清                                                                                                                                  |

---

## 六、验证记录

```
$ python scripts/build_contract_files.py
[primary] K=4 ['G02', 'G05', 'G06', 'G08']
[preregistered_k3] K=3 ['G02', 'G05', 'G08']
[sensitivity_cell_coverage_090] K=6 ['G02', 'G04', 'G05', 'G06', 'G07', 'G08']
[baseline] 630 行 | 观测 630 | 省 7 | 组 10
[contract] 7/7 齐备
[gate] 7/7 通过 -> 回写 manifest
[run] wrote outputs/R002_group_freeze_20261026_164944
```

七条 gate 逐条：

| Gate | 断言                                      | 实测                                             |
| ---- | --------------------------------------- | ---------------------------------------------- |
| G1   | include=1 的组通过全部覆盖规则                    | 4 组四门全通过                                       |
| G2   | 无负值；主结论组有可识别基线                          | 630 行零负值，4/4 组有基线                              |
| G3   | 只有定义匹配的最终组单位价格                          | 零非正值、零 observed 缺价、零退化；**等于最低价 45.1%（阈值 50%）** |
| G4   | 所有硬营养素覆盖率 100%                          | 4 组 × 11 营养素零缺口                                |
| G5   | 主目标覆盖率 100%，系统边界统一                      | 48 行全满，边界唯一（farm-to-retail）                    |
| G6   | 有限、冻结、lower ≤ upper                     | 259 行，3 情景 × 7 省覆盖 12 组                        |
| G7   | hashes / units / version / timestamp 齐备 | 9 个产物 hash 与磁盘一致，零漂移                           |

---

## 七、建议的提交拆分

一次性提交 30 个文件不利于审阅，建议按依赖顺序拆成 5 个 commit：

1. `feat(ontology): 单一本体源 src/ontology.py，删除两处内联副本`  
   — `src/ontology.py`、`scripts/build_group_audit.py`、`scripts/scenario_decision_space.py`、两个 CSV
2. `feat(weights): 新增红肉消费结构权重与加载器`  
   — `data/input/external/meat_consumption_structure.csv`、`src/component_weights.py`、`data/DATA_MANIFEST.json`
3. `feat(contract): B2 七个冻结文件与七条 gate 断言`  
   — 四个 builder + `check_contract_gates.py` + `build_contract_files.py` + `data/processed/*`
4. `docs: 审计报告、预注册修订 R-2026-10-26-a/b、tracker 同步`  
   — `docs/AUDIT_2026-10-26.md`、`docs/EXPERIMENT_PLAN.md`、`docs/EXPERIMENT_TRACKER.md`、两个 README
5. `docs: 变更记录` — 本文件

提交前请确认 `.workbuddy-ai/` 与 `docs/.Rhistory` 不被纳入版本控制  
（前者是本地会话记忆，后者是 R 的历史文件，均与本项目无关）。

---

## 八、上传前检查清单

### 8.1 干净克隆验证结果

用 `git archive HEAD` 导出已跟踪内容到临时目录，模拟协作者克隆后的状态：

| 检查项                                          | 结果                                                                                                                  |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| 导出文件数                                        | 88                                                                                                                  |
| `src/` 是否存在                                  | **存在**（8 个模块：data_audit / imputation / io_utils / mapping_audit / masking / metrics / robust_modopt / \_\_init\_\_） |
| `data/input/` 是否可用                           | **可用**（clean_tables / price / workbook 都在）                                                                          |
| `python -m unittest tests.test_smoke`        | **5/5 通过**                                                                                                          |
| `python scripts/build_contract_files.py`     | **不存在** —— 该脚本尚未 `git add`                                                                                          |
| `src/ontology.py`、`src/component_weights.py` | **缺失** —— 尚未 `git add`                                                                                              |

结论：克隆下来**旧代码能跑**（测试全过），但**无法重建合同**，  
因为合同构建器与两个新模块还只在本地工作区。


### 8.2 必须 `git add` 的 31 个路径

```
# 新增代码（8）
src/ontology.py
src/component_weights.py
scripts/build_contract_files.py
scripts/check_contract_gates.py
scripts/build_decision_bounds.py
scripts/build_environment.py
scripts/build_group_prices.py
scripts/build_nutrients.py

# 新增数据与文档（4）
data/input/external/meat_consumption_structure.csv
data/processed/README.md
docs/AUDIT_2026-10-26.md
docs/CHANGELOG_2026-10-26.md

# 新增冻结产物（9）
data/processed/baseline_consumption.csv
data/processed/group_prices.csv
data/processed/nutrients.csv
data/processed/environment.csv
data/processed/decision_bounds.csv
data/processed/model_manifest.json
data/processed/contract_gate_report.json
data/processed/group_audit_k3_strict.csv
data/processed/group_audit_sensitivity_c0.90.csv

# 修改（10）
.gitignore
README.md
data/README.md
data/DATA_MANIFEST.json
data/processed/group_audit.csv
data/processed/ontology.csv
docs/EXPERIMENT_PLAN.md
docs/EXPERIMENT_TRACKER.md
scripts/build_group_audit.py
scripts/scenario_decision_space.py
```

一条命令：

```bash
git add -A src scripts data docs README.md .gitignore
git status --short   # 确认 .workbuddy-ai/ 与 .Rhistory 不在列表里
```

### 8.3 上传后立刻验证（在全新目录里）

```bash
git clone <repo> repo_check && cd repo_check
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
python -m unittest tests.test_smoke -v            # 应 5/5 通过
python scripts/build_contract_files.py            # 应 7/7 合同 + 7/7 gate
```

最后一条是关键：它证明冻结产物可以由输入重建，而不只是"文件被提交了"。

---

## 九、M2 框架（R200–R203）· 同日追加

### 9.1 新增文件

| 文件                                        | 行数    | 作用                                                |
| ----------------------------------------- | ----- | ------------------------------------------------- |
| `src/b2_problem.py`                       | 约 500 | 合同 → 求解器张量。K=4 组、L=3 目标、J=11 营养素；含非决策组基线偏移与可操作性预检 |
| `src/b2_scenarios.py`                     | 90    | **占位**场景生成（对数正态扰动）。正式版须换 B1 后验                    |
| `src/b2_evaluate.py`                      | 约 230 | 真值评估：联合可行率 + Wilson 区间、方向翻转率、目标间隙                 |
| `scripts/run_b2.py`                       | 约 340 | 驱动 D0–D3 × 省 × 重复，写标准 run 目录                      |
| `tests/test_b2.py`                        | 约 140 | 12 个机制测试（装配、偏移、联合约束、无约束语义、Wilson、gap 符号）          |
| `data/input/external/nutrient_bounds.csv` | 12    | 11 个硬营养素的每日上下界，**待作者确认口径**（见 9.3）                 |

### 9.2 修改 `src/robust_modopt.py`（向后兼容）

新增三个可选参数，默认值保持旧行为：

| 参数                      | 用途                                         |
| ----------------------- | ------------------------------------------ |
| `extra_constraints`     | 组间联合约束（`G05+G06 ∈ [40,75]`），box bound 表达不了 |
| `use_chance_constraint` | D2 语义：完全不施加营养约束                            |
| 放宽校验                    | 允许营养素上界为 `+inf`（"不设上限"是合法语义），仍拒绝 NaN       |

**兼容性已验证**：R005 的可复现哈希仍为 `ab9e5ed14ce2ad36`，5 个原测试全过。

### 9.3 装配过程中发现的四个问题（详见 tracker「M2 框架状态」）

1. **营养边界口径错位**：`nutrient_bounds.csv` 用 RNI，但实测基线膳食本身钙只有  
   419/800 mg、硫胺素 0.9/1.3 mg。RNI 覆盖 97.5% 个体，不能当人均硬下界，  
   应改 EAR。**这是待作者裁定的关键项。**
2. **部分营养素结构性不可达**（钙、硫胺素、部分省的碳水与脂肪），  
   会让机会约束整体不可行。已按「不进入机会约束但仍参与真值评估」处理，两个口径都报。
3. **决策由约束而非成本决定**：4 变量 + 9 约束 → 可行域近似单点，  
   D0 与 D1 的解逐元素相同，gap 均为 0。不确定性在本设计下无法通过目标函数起作用。
4. **浙江缺禽肉价格**（9 年零观测），K=4 口径下实际只有 6 省，M4 的"七省故事"需修正。

### 9.4 当前证据状态

`metrics.json` 的 `evidence_status = "plumbing_only"`，`placeholder_components` 列出  
真值/场景/重复三处占位。smoke 实测 D3 可行率（0.667）**低于** D0/D1（0.833），  
与假设方向相反；不做调参美化，原因分析见 tracker。

### 9.5 待提交文件数

从 31 增至 **37**（新增上述 6 个代码/测试文件，另 `nutrient_bounds.csv` 与  
`src/robust_modopt.py` 已包含在内）。

```bash
git add -A src scripts data docs tests README.md .gitignore
python -m unittest tests.test_smoke tests.test_b2 -v   # 应 17/17 通过
```

## 十、浙江回归七省 · 价格桥接（同日第二轮追加）

### 10.1 问题定性

浙江的禽类（G05）在零售源表里**整块缺失**：不是个别年份缺，而是「浙江」工作表  
根本没有这一行（`仍缺数据` 登记为 `整块缺失-品类`、P0、9 年）。  
`price_panel_clean.xlsx` 中浙江 108 个「组×年」格只有 17 格有观测，  
最佳年份（2023）也只有 7/12 组。因此浙江被 `complete_provinces()` 排除，  
K=4 口径下实际只有 6 省。

### 10.2 方法：批发价 × 品类比价（跨源换算，非插补）

批发价工作簿 `华东华中7省食品零售价_商务预报_分省批发价_mice插补.xlsx`  
有浙江 **9 个品类 × 9 年**的批发价，且仅 5 格是 MICE 插补  
（羊肉 2018/2019/2020/2023、牛肉 2023），其余为实测。

零售价与批发价不同源、不同环节（`口径说明` 明写「请勿直接混用」），  
所以用**品类专属**的零售/批发比价换算：

```
ratio_c = median( retail_kg / wholesale_kg )   # 在同时有两套价格的省-年上估计
零售价桥接值 = 批发价 × ratio_c
```

**必须按品类分层**，不能跨品类池化——比价有强品类效应：

| 品类        | 中位数   | 10% 分位 | 90% 分位 | 配对数 | 省数 |
| --------- | ----- | ------ | ------ | --- | -- |
| 鸡蛋        | 1.100 | 0.938  | 1.219  | 40  | 7  |
| 粮食(大米/面粉) | 1.181 | 1.020  | 1.423  | 22  | 6  |
| 牛肉(后腿)    | 1.220 | 1.105  | 1.529  | 23  | 5  |
| 羊肉(后腿)    | 1.224 | 1.081  | 1.532  | 22  | 5  |
| 食用油(升)    | 1.395 | 1.191  | 1.691  | 20  | 6  |
| 猪肉        | 1.415 | 1.106  | 1.808  | 51  | 7  |
| 蔬菜        | 1.506 | 1.112  | 1.944  | 35  | 7  |
| 禽类        | 1.558 | 1.368  | 2.091  | 21  | 5  |
| 薯类(马铃薯)   | 1.665 | 1.333  | 1.782  | 8   | 3  |

### 10.3 口径纠正（重要）

第一版桥接脚本读的是 `清洗长表` 的 `数值` 列，而主管线  
（`src.data_audit.load_clean_price_panel`）读的是 `年均值表` 的 `年均值` 列。  
两张表基准不同（`清洗长表` 里还有一列 `换算值`，对元/500g 行是 ÷2），  
混用会把比价系统性算错：**错误基准下禽类比价 1.693，正确基准下 1.558**。

现在桥接脚本直接调用 `load_clean_price_panel`，与管线共用同一读取路径，  
从结构上排除这类不一致。

### 10.4 接入方式：组级整体缺失才回退

桥接值**不进入**已有观测的省份-年份。理由：`price_panel()` 用的是  
「省 × 组」的跨年均值，若把桥接值混进某省某组的个别年份，  
会改变已冻结的省-组均值，扰动全部系数（实测江苏 G08 桥接值仅为观测均值的 0.61 倍）。

规则改为：**仅当某省某组 9 年全部零观测**时才回退到桥接值。

`data/processed/group_prices.csv` 新增三列：

| 列                      | 含义                                 |
| ---------------------- | ---------------------------------- |
| `price_source`         | `observed` / `bridged` / `missing` |
| `n_bridged_categories` | 该格用了几个桥接品类                         |
| `price_cny_kg_full`    | 观测+桥接混合的完整版本，仅供 B4 敏感性             |

`truth_eligible` 对桥接行一律为 `False`——桥接值不能当「真值」参照。

**实测结果**：45 行被回退，其中只有 **浙江 G05（9 行）** 属决策组；  
其余 36 行是 G10 薯类（山东/江苏/浙江/福建），非决策组、当前不参与目标函数。

### 10.5 效果

| 指标        | 接入前   | 接入后                             |
| --------- | ----- | ------------------------------- |
| K=4 齐全省份  | 6     | **7**                           |
| 浙江 G05 组价 | 无数据   | **31.25 元/kg**（9 年 25.48–36.36） |
| G06 主口径均值 | 43.92 | **43.92（未变）**                   |
| G06 等权均值  | 54.43 | **54.43（未变）**                   |

浙江禽肉 31.25 元/kg 落在江西 36.07 与福建 27.23 之间，量级合理。  
G06 两个口径逐位不变，证明回退规则确实做到了「不扰动」。

### 10.6 残余不确定性（必须随结果报告）

1. **桥接值不是实测值**，浙江 G05 的 9 年价格全部是换算来的。
2. **比价省间跨度大**：禽类从 1.362（某省）到 2.020，近 1.5 倍。  
   输出已带 `retail_low/high`（10%–90% 分位），B4 必须做桥接敏感性。
3. **7 格批发基座是 MICE 插补**（山东牛肉/羊肉 2016；浙江牛肉 2023、羊肉 2018/2019/2020/2023），  
   属「插补之上再换算」，误差会叠加。
4. 浙江其他组仍只有 1–5 年观测（G02 两年、G07 一年、G08 两年），  
   省均值的不确定性高于其他六省。这一点**没有**被桥接解决。

---

## 十一、营养边界：RNI vs EAR（同日第三轮追加）

### 11.1 两版 DRIs 的实际差异（已核实）

| 项目           | 2013 版        | 2023 版                                  | 来源                      |
| ------------ | ------------- | --------------------------------------- | ----------------------- |
| 钙 RNI（18–49） | 800           | 800（不变）                                 | WS/T 578.2-2018；澎湃/协和科普 |
| 钙 RNI（50+）   | 1000          | **800（下调）**                             | 同上                      |
| 孕期/哺乳期钙      | 有额外增加         | **不再增加**                                | 协和科普                    |
| 蛋白质 RNI（65+） | 0.98 g/(kg·d) | **1.17 g/(kg·d)**                       | 人民日报健康/协和科普             |
| 能量           | —             | **整体略微下调**                              | 协和科普                    |
| 铁            | —             | 修订（考虑更年期女性经期）                           | 协和科普                    |
| 锌            | —             | 男稍降、女稍升                                 | DRIs 2023 解读            |
| 新增膳食成分       | —             | 甜菜碱、牛磺酸、辅酶Q10、菊粉、谷物β-葡聚糖、枸杞多糖、海藻多糖（7 种） | 协和科普                    |
| 年龄分组         | —             | 细化（2023 版分组更细）                          | DRIs 2023               |

**重要更正**：`nutrient_bounds.csv` 原先标注来源为「中国居民膳食营养素参考摄入量（2023）」，  
但其数值实际对应 **2013 版**（经 WS/T 578.2/3/5-2018 逐项核对）。  
现已把 `source` 改为国标编号，并新增 `verified_against` 列。2023 版的 EAR 逐项数值  
尚未取得权威表格，故 EAR 列一律采用 2013 版国标值并明确标注。

### 11.2 EAR 与 RNI 的差别（已核实，逐项）

来源：WS/T 578.2-2018 表1、WS/T 578.3-2017 表1、WS/T 578.5-2018 表1（18 岁～）

| 营养素     | EAR 男 | EAR 女 | 本模型用 EAR | RNI 男 | RNI 女 | 本模型用 RNI | 变化    |
| ------- | ----- | ----- | -------- | ----- | ----- | -------- | ----- |
| 钙       | 650   | 650   | **650**  | 800   | 800   | 800      | −150  |
| 铁       | 9     | 15    | **12**   | 12    | 20    | 16       | −4    |
| 锌       | 10.4  | 6.1   | **8.25** | 12.5  | 7.5   | 10       | −1.75 |
| 硒       | 50    | 50    | **50**   | 60    | 60    | 60       | −10   |
| 硫胺素(B1) | 1.2   | 1.0   | **1.1**  | 1.4   | 1.2   | 1.3      | −0.2  |
| 核黄素(B2) | 1.2   | 1.0   | **1.1**  | 1.4   | 1.2   | 1.3      | −0.2  |
| 烟酸      | 12    | 10    | **11**   | 15    | 12    | 13.5     | −2.5  |

能量/蛋白质/脂肪/碳水**没有 EAR**（能量用 EER、脂肪碳水用 AMDR、蛋白质 EAR 待 WS/T 578.1 核对），  
`basis="ear"` 时自动回退到原下界，并在 `Contract.bounds_basis_fallback()` 中列出。


### 11.3 实测影响

**可达性诊断**（7 省 × 11 营养素，判定标准：决策箱内能否让摄入进入区间）：

| 口径  | 不可达营养素 | 不可达省数 | 缺口倍数            |
| --- | ------ | ----- | --------------- |
| RNI | 钙      | 7/7   | 1.64            |
| RNI | 硫胺素    | 6/7   | 1.00（临界，差 0.1%） |
| EAR | 钙      | 7/7   | **1.33**        |
| EAR | 硫胺素    | —     | **已解除**         |

**结论：EAR 能解硫胺素，解不了钙。**

以安徽为例，`non_actionable` 从  
`{钙: 最大可达 168.1 < 下界 587.1, 硫胺素: 0.8155 < 0.8495, 碳水化合物: …}`  
变为 `{钙: 最大可达 168.1 < 下界 437.1, 碳水化合物: …}`——硫胺素退出不可达集。

钙的缺口是**结构性的**：决策箱（蛋/禽/红肉/蔬菜）最多提供 168 mg，  
而非决策组基线只贡献约 321 mg，合计 489 mg，无论如何都到不了 650。  
因为中国膳食钙的 ~60% 来自乳制品与豆制品，而 G01（乳制品）不在决策集内。

**smoke 对比**（`scripts/run_b2.py --profile smoke`）：

| 口径  | 方法    | 可行(全) | 可行(活跃) | 翻转率   | 失败 |
| --- | ----- | ----- | ------ | ----- | -- |
| RNI | D0/D1 | 0.000 | 0.714  | 0.286 | 4  |
| RNI | D3    | 0.000 | 0.571  | 0.464 | 6  |
| EAR | D0/D1 | 0.000 | 0.000  | 1.000 | 14 |
| EAR | D3    | 0.000 | 0.000  | 1.000 | 14 |

EAR 口径下失败数**上升**（4→14），原因是硫胺素从「永远违反所以被剔除」  
变成「勉强可满足所以进入活跃集」，而它的余量只有约 10%  
（最大可达 1.21–1.30 vs EAR 1.1），在 5% 系数不确定性与 ε=0.05 下  
机会约束频繁不可行。这不是 bug，是真实的结构紧张。

**因此 `--bounds-basis` 默认仍为 `rni`**（预注册口径不变），  
EAR 作为显式实验分支，需作者签字后才切换为主口径。

### 11.4 新增/修改文件

| 文件                                               | 变更                                                                            |
| ------------------------------------------------ | ----------------------------------------------------------------------------- |
| `scripts/build_price_bridge.py`                  | 重写：改用 `load_clean_price_panel`、按品类比价、全 7 省、输出分位区间                             |
| `data/input/external/price_bridge_wholesale.csv` | 新增，278 格桥接值                                                                   |
| `scripts/build_group_prices.py`                  | 新增桥接回退（组级整体缺失才触发）+ 3 列                                                        |
| `src/b2_problem.py`                              | `nutrient_limits(basis=)`、`bounds_basis_fallback()`、`instance(bounds_basis=)` |
| `data/input/external/nutrient_bounds.csv`        | 新增 `ear_per_day`/`rni_per_day`/`sex_basis`/`verified_against`，来源改为国标编号        |
| `scripts/run_b2.py`                              | 新增 `--bounds-basis {rni,ear}`                                                 |
| `tests/test_b2.py`                               | 3 个测试替换/新增：七省齐全、桥接打标、不扰动已冻结系数                                                 |

测试：`python -m unittest discover -s tests` → **19/19 通过**。

## 十二、M1 收尾：R003 / R106 / R107 / R108 / R109（同日第四轮追加）

### 12.1 R003 手工可验算 LP fixture（PARTIAL → DONE）

原 toy 问题带 6 目标、20 场景、机会约束，能验证 MILP 机制，但**没人能手算最优解**，  
无法判断求解器是「算对了」还是「算出了一个自洽的错答案」。

新增 `tests/test_lp_fixture.py`（5 个测试）：

```
min  q1 + 3·q2
s.t. 2q1 + q2 ≥ 8 ,  q1 + 3q2 ≥ 9 ,  0 ≤ q ≤ 10
```

手算：两约束同时紧 ⇒ q = (3, 2)，成本 9；顶点比较 (10,0)→10、(0,10)→30 均更差。  
最优解**不在任何边界上**，因此能区分「真在解 LP」与「把变量推到 bound」。

| 测试     | 断言                                               |
| ------ | ------------------------------------------------ |
| 内点最优   | q = (3,2)，成本 9                                   |
| 两约束同时紧 | `A q = [8, 9]`                                   |
| 上界紧    | q_upper=(2.5,10) ⇒ q = (2.5, 3)，成本 11.5          |
| 不可行    | 下界 (100,100) ⇒ `success=False` 且 q 非有限           |
| 语义钉住   | `use_chance_constraint=False` ⇒ 无营养约束，解被推到 (0,0) |

最后一条尤其重要：`use_chance_constraint=False` **不是**「确定性硬约束」，  
而是「完全不加营养约束」（D2 的语义）。若不钉住，很容易误用而得出错误结论。


### 12.2 R106 覆盖率曲线（PARTIAL → DONE）

新增 `scripts/coverage_curve.py`，**只读** `cell_predictions.csv` 事后重算，  
不重跑（重跑 5×20 的 MICE 要二十分钟，只为多两列不划算）。

等效 SD 取 `(upper95 − lower95) / (2·z95)`，对所有方法统一。  
对数正态类方法区间不对称，为此同时输出 `asymmetry95` 让偏差可见  
（实测 hierarchical_rw 的 asymmetry95 约 13–20，确实右偏）。

价格面板正式结果（`B1_formal_withmice_20261023_124906`）：

| 遮蔽类型              | 方法                  | scaled_mae | cov50 | cov80 | cov90 | cov95 | 标定误差      | 斜率    |
| ----------------- | ------------------- | ---------- | ----- | ----- | ----- | ----- | --------- | ----- |
| single_cell       | group_mean          | 0.200      | 0.693 | 0.853 | 0.892 | 0.913 | 0.073     | 0.489 |
| single_cell       | **hierarchical_rw** | 0.172      | 0.610 | 0.897 | 0.920 | 0.940 | **0.059** | 0.733 |
| single_cell       | interpolation       | 0.159      | 0.710 | 0.847 | 0.873 | 0.887 | 0.087     | 0.393 |
| single_cell       | mice                | 0.140      | 0.582 | 0.773 | 0.828 | 0.865 | 0.066     | 0.630 |
| province_group    | **hierarchical_rw** | 0.169      | 0.542 | 0.870 | 0.932 | 0.946 | **0.037** | 0.898 |
| province_group    | mice                | 0.669      | 0.241 | 0.421 | 0.665 | 0.773 | 0.262     | 1.183 |
| consecutive_years | **hierarchical_rw** | 0.149      | 0.600 | 0.880 | 0.930 | 0.955 | **0.054** | 0.789 |

两条结论：

1. **`hierarchical_rw` 在三种遮蔽下标定误差都最低**（0.054 / 0.037 / 0.059），  
   与主方法选择一致——这不是选出来的，是 R106 独立测出来的。
2. **`coverage_slope` 全域 < 1**（0.39–1.18）：区间整体偏宽（50% 名义覆盖率实测  
   0.54–0.71），但 95% 端又略低于名义值。这是「中间过宽、尾部不足」的典型形状，  
   说明残差分布比正态更厚尾。**不能只报 cov95 就宣称标定良好。**

MICE 在 province_group 上 slope 1.18、标定误差 0.262，是**过度自信**的失败模式，  
与 R102 的崩溃一致。

### 12.3 R107 交互项门控（PARTIAL → DONE）

既有 `B1_interaction_sweep_20261023_141000` 已被审计标为 INCOMPLETE，  
**不能作为有效 run 引用**。但它的 `tuning.csv` / `heldout.csv` 足以回答 R107 的问题。  
新增 `scripts/interaction_gate.py` 只读复算，结论落盘 `outputs/R107_interaction_gate/`。

判定准则（预注册）：三种掩码在调参与留出两侧 **全部** 改善（比值 <1）才算 both improve；  
任一抹码比值 >1.05 记为退化。不采用「平均改善即可」的宽松口径。

| 配置         | consecutive_years | province_group | single_cell | 均值    |
| ---------- | ----------------- | -------------- | ----------- | ----- |
| ir10_k1 调参 | 0.897             | **1.006**      | 0.923       | 0.942 |
| ir10_k1 留出 | 0.858             | **1.017**      | 0.927       | 0.934 |

**结论：「both improve」不成立。** 交互项在年块（−10~~14%）与单格（−7~~8%）  
上一致改善，但在整块缺失（province_group）上轻微退化。

机制上说得通：**整块缺失时该省该组零观测，交互项无从估计**，  
ridge 收缩把它拉回主效应，反而增加了一点噪声。所以交互项不能无条件启用，  
只能按遮蔽几何分场景使用。


### 12.4 R108 / R109 MAR 诊断与 MNAR δ 网格（新增脚本，价格 smoke 已跑）

新增 `scripts/sensitivity_mar_mnar.py`。

**R109（MNAR δ 网格）**：δ-调整假设被遮蔽格真值系统性偏离 MAR 预测 δ 个残差 SD，  
δ ∈ {−0.5, 0, +0.5}（预注册网格）。σ 取组内残差 SD。

价格 smoke 的**排序稳定性**（每个 δ 下按标定误差排名）：

| 方法              | single_cell (−0.5/0/+0.5) | province_group | consecutive_years |
| --------------- | ------------------------- | -------------- | ----------------- |
| hierarchical_rw | **1 / 1 / 1**             | **1 / 1 / 1**  | 1 / 3 / 3         |
| group_mean      | 3 / 4 / 4                 | 2 / 2 / 2      | 2 / 1 / 1         |
| interpolation   | 2 / 3 / 2                 | 3 / 3 / 3      | 3 / 2 / 2         |
| mice            | 4 / 2 / 3                 | 4 / 4 / 4      | 4 / 4 / 4         |

**主方法在 single_cell 与 province_group 上排序完全稳定，在 consecutive_years 上不稳定**  
（δ=0 时 group_mean 更好）。这提示：年块缺失下不宜宣称主方法全面占优。

**R108（MAR 诊断）**：按真值五分位看 signed bias，并给出标准化 `bias_slope`。

| 遮蔽类型           | 方法              | bias_slope | 判读      |
| -------------- | --------------- | ---------- | ------- |
| single_cell    | hierarchical_rw | −0.55      | 高值系统性低估 |
| single_cell    | interpolation   | −0.31      | 同上，较轻   |
| province_group | hierarchical_rw | −0.77      | 明显低估高值  |
| province_group | mice            | −0.98      | 最严重     |

**这是本轮最重要的负面发现**：覆盖率看起来正常（cov95 0.89–0.95），  
但 `bias_slope` 显著为负——**高值被系统性低估**。  
即「标定好」不等于「无偏」。若真实缺失机制是「高值更易缺」，  
现有插补会向下偏，进而低估高价省份的成本与营养摄入。

必须在论文里明确写：95% 覆盖率不能当作无偏的证据。

### 12.5 修复一个潜伏 bug：`make_mask` 索引错位

`src/masking.py` 的 `make_mask` 用 `panel.index` 当作位置下标回写布尔数组。  
只要调用方**过滤过行**（索引不连续），标签 ≠ 位置，会静默错位甚至越界  
（实测抛 `IndexError: index 869 is out of bounds for axis 0 with size 863`）。

`run_calibration` 恰好只把值置 NaN、不删行，索引保持连续，所以一直没暴露。  
本轮的 `sensitivity_mar_mnar.py` 过滤了行，才把它踩出来。

修复：在 `make_mask` 内部 `panel.reset_index(drop=True)`，使标签与位置恒等，  
调用方无需关心自己传进来的索引形态。新增回归测试  
`test_mask_survives_non_contiguous_index` 钉住行为。


### 12.6 R103–R105 消费面板 B1（新增 `--panel`）

`run_experiments.py` 新增 `--panel {price,consumption}`，  
`src/data_audit.py` 新增 `load_consumption_panel()` 与 `normalise_province()`。

**关键事实：消费面板零缺失。** `clean_tables/consumption.csv` 是  
7 省 × 10 组 × 9 年 = 630 格**全观测**（2025 年 70 格标 `incomplete_2025`，排除）。

因此 R103–R105 做的是「**人造遮蔽 → 恢复**」的可恢复性测试，  
**不能用来推断真实缺失机制**——真实缺口只存在于价格面板。  
这一点必须随结果报告，否则会被误读为「消费数据缺失已处理」。

面板命名统一：源表「上海市」→ 面板「上海」，与价格面板 / B2 合同的  
`province` 键对齐；`data_nature` 把 `quality_flag == "ok"` 映射为「实测」，  
使 config 里 `training_data_natures: [实测]` 对两个面板语义一致。

正式结果（`outputs/R103_105_consumption_formal_20261026_174725`，  
20 分片 / 20 并发 / 377s；标定误差为**池化**口径，来自 `coverage_curve.py`）：

| 遮蔽                | 方法              | n    | sMAE      | cov50 | cov95     | 标定误差      | 斜率    |
| ----------------- | --------------- | ---- | --------- | ----- | --------- | --------- | ----- |
| single_cell       | mice            | 1300 | **0.036** | 0.611 | 0.901     | 0.050     | 0.644 |
| single_cell       | interpolation   | 1300 | 0.047     | 0.725 | 0.937     | 0.075     | 0.470 |
| single_cell       | group_mean      | 1300 | 0.138     | 0.696 | 0.931     | 0.069     | 0.521 |
| single_cell       | hierarchical_rw | 1300 | 0.147     | 0.504 | 0.949     | **0.009** | 0.990 |
| consecutive_years | interpolation   | 200  | **0.056** | 0.690 | 0.870     | 0.087     | 0.400 |
| consecutive_years | mice            | 200  | 0.059     | 0.575 | 0.825     | 0.098     | 0.556 |
| consecutive_years | hierarchical_rw | 200  | 0.137     | 0.590 | 0.960     | **0.034** | 0.822 |
| province_group    | group_mean      | 900  | 0.149     | 0.659 | 0.918     | 0.063     | 0.575 |
| province_group    | hierarchical_rw | 900  | 0.181     | 0.442 | 0.900     | 0.065     | 1.017 |
| province_group    | interpolation   | 900  | 0.149     | 0.428 | 0.691     | 0.199     | 0.585 |
| province_group    | **mice**        | 900  | **1.000** | 0.022 | **0.079** | **0.736** | 0.126 |

三条结论，与价格面板**方向一致**：

1. **MICE 在整块缺失下彻底崩溃**（sMAE 1.000、cov95 0.079）。价格面板是 0.669/0.773，  
   消费面板更糟。原因相同：整块缺失时该省该组的整列都是空的，  
   `IterativeImputer` 没有可用的行内信息，只能退化为常数，区间也随之塌缩。
2. **点精度与标定是两件事。** single_cell 上 MICE 点误差最低（0.036）但标定误差 0.050；  
   hierarchical_rw 点误差最差（0.147）但标定误差 **0.009**、斜率 0.990（近乎完美）。  
   只报 sMAE 会选错方法，只报覆盖率也会选错方法。
3. **interpolation 的区间在整块缺失下不可用**（cov95 0.691，比名义值低 26 个百分点），  
   虽然它的点误差与 group_mean 并列最优。这是「用点精度选方法」的典型陷阱。

### 12.6b 一个统计口径陷阱：逐块标定误差不能平均

`run_experiments` 原先在 summary 里汇总 `calibration_error`。但该指标是  
`|经验覆盖率 − 名义水平|` 的均值，而每个 fold-repeat 块的样本很小  
（consecutive_years 每块仅 8 格），小样本噪声把 `|cov − nominal|` 系统性抬高，  
再跨块平均得到虚高的数：**逐块平均 0.242，池化后仅 0.066**。

已从 `run_experiments.py` 与 `run_calibration_parallel.py` 的 summary 中**移除该列**  
（`calibration_results.csv` 仍保留逐块值），权威口径统一走  
`scripts/coverage_curve.py` 的池化计算。这是本轮第二个「看起来对、其实会误用」的口径问题。

### 12.7 新增/修改文件

| 文件                                | 变更                                                                                                                                      |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_lp_fixture.py`        | 新增，5 个手工可验算 LP 测试（R003）                                                                                                                 |
| `scripts/coverage_curve.py`       | 新增，R106 只读重算覆盖率曲线                                                                                                                       |
| `scripts/interaction_gate.py`     | 新增，R107 门控判定                                                                                                                            |
| `scripts/sensitivity_mar_mnar.py` | 新增，R108 诊断 + R109 δ 网格                                                                                                                  |
| `src/metrics.py`                  | 新增 `effective_sd` / `coverage_at` / `NOMINAL_LEVELS`，`calibration_metrics` 增出 cov50/cov90/width50/width90/calibration_error/asymmetry95 |
| `src/data_audit.py`               | 新增 `load_consumption_panel` / `normalise_province`                                                                                      |
| `src/masking.py`                  | **修 bug**：函数内 `reset_index`，消除非连续索引错位                                                                                                   |
| `run_experiments.py`              | 新增 `--panel`、`load_panel()`，summary 增出覆盖率列，写出 `coverage_curve.csv`                                                                      |
| `configs/*.yaml`                  | 新增 `paths.clean_consumption_table`                                                                                                      |
| `tests/test_smoke.py`             | 新增 `test_mask_survives_non_contiguous_index`                                                                                            |

测试：`python -m unittest discover -s tests` → **25/25 通过**。

---

## 十三、可操作性预检的口径 bug：box 角点 ≠ 可行域（同日第五轮）

### 13.1 症状

`scripts/run_b2.py --profile smoke` 一直报山东、浙江「求解失败」。我原先把它归因于  
「营养边界口径不对」（RNI 太严），并在 §11 里写进「四个阻塞问题」。**这个归因是错的。**

追下去发现两类完全不同的失败被混成了一个：

| 省份 | 真实原因                     | 旧口径下的表现         |
| -- | ------------------------ | --------------- |
| 浙江 | 硫胺素在**联合约束下**不可达，却被判为可操作 | 整个实例 INFEASIBLE |
| 山东 | 碳水化合物上界与硒下界**真的冲突**      | 整个实例 INFEASIBLE |

浙江那条是**代码 bug**，不是数据问题。

### 13.2 根因

可操作性预检用的是**角点公式**：

```python
q_at_max = np.where(n_mat >= 0, upper, lower)
feasible_hi = (n_mat * q_at_max).sum(axis=1)
```

只有 box 约束时这是精确的——线性函数的最值必在角点。但 CDG 情景有一条联合约束  
`q_G05 + q_G06 ∈ [40, 75]`，角点 `(q_G05=68.31, q_G06=181.74)` 根本不在可行域内。  
公式因此**高估**可达范围：

| 营养素（浙江） | box 角点给出的可达上界 | 加联合约束后的真实上界 | 需求      |
| ------- | ------------- | ----------- | ------- |
| 硫胺素     | 0.83 mg       | **0.60 mg** | 0.82 mg |

0.83 ≥ 0.82，于是硫胺素被判为「可操作」进入机会约束。但真实可行域里它最多 0.60，  
**每个场景都必然违反**，`z` 全为 1，`z_sum ≤ floor(εS)` 直接不可行。  
失败原因被记成「优化器解不出来」，实际是约束集自相矛盾。

### 13.3 修法

新增两个函数（`src/b2_problem.py`）：

```python
reachable_bounds(n_mat, q_lower, q_upper, extra)
    # 无联合约束 → 走角点公式（快路径，精确等价）
    # 有联合约束 → 逐营养素解 2 个 LP（min/max），用 HiGHS
    # LP 不可行 → 返回 nan，由调用方报「可行域为空」

minimal_conflict_set(n_mat, q_lower, q_upper, lower, upper, extra)
    # 硬约束整体不可行时，贪心求近似最小冲突集
```

`Instance` 新增两个字段：

| 字段              | 含义                         |
| --------------- | -------------------------- |
| `hard_feasible` | box ∩ 联合 ∩ active 营养素 是否自洽 |
| `conflict_set`  | 不可行时，造成冲突的营养素名             |

**判定范围只取 `active` 营养素**。第一版把全部 11 个都算进去，结果 7 省全报「硫胺素」——  
但硫胺素本来就被排除了，这个信息是重复的。要回答的是「送进求解器的这套约束是否自洽」。

`scripts/run_b2.py` 相应改为：硬不可行的实例**跳过求解**，直接写一行  
`instance_status="hard_infeasible"` 与 `solver_message="hard_infeasible: 碳水化合物+硒"`，  
不计入求解失败率。

性能代价：7 省装配从 0.05 s 升到 0.71 s（22 个 LP/省）。可接受。

### 13.4 修完之后

| 省份     | active 数 | 硬可行                  | 冲突集           |
| ------ | -------- | -------------------- | ------------- |
| 上海     | 9        | ✓                    | —             |
| 江苏     | 9        | ✓                    | —             |
| 安徽     | 8        | ✓                    | —             |
| 江西     | 8        | ✓                    | —             |
| **浙江** | 8        | **✓（此前 INFEASIBLE）** | —             |
| 福建     | 9        | ✓                    | —             |
| **山东** | 9        | **✗**                | **碳水化合物 + 硒** |

浙江的 `non_actionable` 现在是 `[碳水化合物, 钙, 硫胺素]`，与 13.2 的 LP 结果一致。

**山东的冲突是真的**：硒下界 39.5 μg 要求蔬菜接近上界 500 g（蔬菜硒 0.042 μg/g），  
而蔬菜 500 g 带来 67 g 碳水，超过碳水上界 49.3 g（AMDR 325 g 减去非决策组基线 275.7 g）。  
两者无法同时满足。这是**约束集本身的问题**，任何求解器、任何场景生成器都救不了，  
需要作者在「碳水上界是否当硬约束」与「硒下界是否用 RNI」之间做口径决策。

### 13.5 smoke 重跑（`outputs/R200_203_b2_smoke_20261026_180400`）

| 方法 | 可行(全) | 可行(活跃)    | 翻转率   | gap 均值 | 失败                         |
| -- | ----- | --------- | ----- | ------ | -------------------------- |
| D0 | 0.000 | **1.000** | 0.000 | 0.000  | 0（山东 2 行标 hard_infeasible） |
| D1 | 0.000 | **1.000** | 0.000 | 0.000  | 同上                         |
| D2 | 0.000 | 0.000     | 0.500 | −0.715 | 同上                         |
| D3 | 0.000 | **0.833** | 0.167 | 0.109  | 江苏 2 行真失败                  |

与修复前（D3 0.667 < D0/D1 0.833）相比，**方向反转的异常消失了**。  
现在只有江苏在 ε=0.05、S=20 下机会约束不可行——`floor(0.05×20)=1`，  
只允许 1 个场景违反，容错极窄。这属于 S 过小的取整效应，R301/R302 会验证。

D0 与 D1 仍逐元素相同（`flips=0.000`、`gap=0.000`），这个结构性问题**没有**被本次修复解决，  
仍是 §11 遗留的第 3 条。

### 13.6 新增 `scripts/run_m3_sensitivity.py`（R300–R303）

四个网格共用同一批实例与场景（场景按 `(S, seed)` 缓存），一条命令跑完：

| 网格   | 扫描量                       | 回答的问题                     |
| ---- | ------------------------- | ------------------------- |
| R300 | D3 vs D2                  | 机会约束本身贡献了多少可行性/遗憾         |
| R301 | S ∈ {25,50,100,200,400}   | 场景数平台期，S 太小时 ε·S 取整是否主导结果 |
| R302 | ε ∈ {0, 0.02, 0.05, 0.10} | 可行性对风险预算的响应（预注册网格）        |
| R303 | 权重 original vs equal      | 方向稳定性，禁止按结果挑权重            |

硬不可行的省份在网格里**直接跳过并记录原因**，不参与网格响应计算——  
否则山东的常数失败会把「ε 越小越难解」这类参数效应稀释掉。

`evidence_status` 仍为 `plumbing_only`。但两类结论与场景生成器无关、可直接采信：  
结构性冲突（山东）与单调性方向（ε↓ 是否更难解）。

### 13.7 本轮新增/修改文件

| 文件                              | 变更                                                                                                                |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `src/b2_problem.py`             | 新增 `reachable_bounds` / `minimal_conflict_set` / `_lp_rows`；`Instance` 增 `hard_feasible` / `conflict_set`；预检改走 LP |
| `scripts/run_b2.py`             | 硬不可行实例跳过求解并打标；诊断增 `hard_feasible` / `conflict_set`；结果增 `instance_status`                                          |
| `scripts/run_m3_sensitivity.py` | 新增，R300–R303 统一驱动                                                                                                 |
| `tests/test_b2.py`              | 新增 `ReachabilityTest`（3 个手算玩具用例）+ `B2FeasibilityTest`（3 个真实合同用例）                                                  |

测试：`python -m unittest discover -s tests` → **31/31 通过**。

---

## 十四、为什么 D0 与 D1 的解逐元素相同：决策被「脂肪下界」钉死（同日第六轮）

### 14.1 现象

R201 的记录里有一句「D0（跨省合并价）与 D1（省内价）的 `q` 逐元素相同」。  
之前把它归为「4 变量 + 9 约束，可行域被压成近似单点」。**这个解释不准确**——  
顶点处恰好 K 条约束紧是线性规划的常态，不是病态。真正要问的是：  
**解对目标系数的敏感度有多低**。

新增 `scripts/diagnose_decision_sensitivity.py` 做两件事：  
把某一组的价格乘子从 0.5 扫到 2.0，找出使解移动的最小乘子偏离；  
再把每个活跃营养素的系数乘子改成 0.9 / 1.1，做对称检查。

### 14.2 价格：需要 20%–100% 才能移动解

`outputs/DIAG_decision_sensitivity_20261026_181347`

| 省份 | G02 蛋 | G05 禽 | G06 红肉 | G08 蔬菜 | 省内 vs 合并价 |
| -- | ----- | ----- | ------ | ------ | --------- |
| 上海 | 未翻转   | 100%  | 50%    | 未翻转    | **0.0 g** |
| 安徽 | 未翻转   | 100%  | 未翻转    | 未翻转    | **0.0 g** |
| 江苏 | 未翻转   | 未翻转   | 未翻转    | 未翻转    | **0.0 g** |
| 江西 | 未翻转   | 50%   | 40%    | 未翻转    | **0.0 g** |
| 浙江 | 未翻转   | 30%   | 20%    | 未翻转    | **0.0 g** |
| 福建 | 未翻转   | 20%   | 20%    | 未翻转    | **0.0 g** |

「未翻转」= 乘子在 [0.5, 2.0] 内扫遍仍未变化。

**蛋与蔬菜的价格在 ±50%–100% 内完全不影响决策**；禽肉与红肉要 20%–100% 才动。  
而 B2 场景用的是 **5% CV**——落在平台内部，概率上几乎不可能跨界。

所以 D0 ≡ D1 不是「均值填充没用」，而是**价格这一维在本设计下根本没有传导通道**。  
把 5% 换成 20% 噪声也不会让它变得有意义，只会让平台边界附近出现随机跳变。

### 14.3 机制：脂肪下界在 6 省全部是紧约束

| 省份 | 紧约束（4 个变量恰好 4 条）            |
| -- | --------------------------- |
| 上海 | G02=上界、联合=上界、**脂肪↓**、能量↓    |
| 安徽 | G02=上界、联合=上界、**脂肪↓**、硒↓     |
| 江苏 | G02=上界、联合=上界、**脂肪↓**、锌↓     |
| 江西 | G02=上界、联合=上界、**脂肪↓**、硒↓     |
| 浙江 | G02=上界、G08=下界、联合=上界、**脂肪↓** |
| 福建 | G02=上界、G08=下界、联合=上界、**脂肪↓** |

**六省无一例外，脂肪下界都是紧的。** 因为决策集里脂肪密度最高的是红肉  
（0.308 g/g，禽肉 0.163、蛋 0.125、蔬菜 0.007），要达到 AMDR 的脂肪下界  
（44 g/天，扣除非决策组基线后剩 25.7–27.5 g），只能靠红肉。

于是模型实际上退化成一个等式：

> 「需要多少红肉才能满足脂肪下界？」

红肉量一旦被脂肪钉住，价格的相对变化就没有意义了。这解释了 14.2 的全部现象，  
也解释了为什么只有红肉/禽肉价格能移动解——它们是脂肪的两个来源。

> **⚠️ 上面这段因果解释已部分被推翻（2026-10-26 晚，见 §18）。**  
> 脂肪下界紧这一点**是事实**（6/6 省 `rel_slack = 0.0`），  
> 但「红肉量被钉住、模型退化成一个等式」**是错的**：可行域有 12–14 个顶点，  
> 红肉量省际差 26–64 g，纯环境权重下浙江红肉从 39.8 → 30.4 g。  
> 价格传导弱的真正原因是**顶点间的成本排序对 ±5% 扰动稳健**（要 20%–100% 才翻转），  
> 不是「解被唯一钉死」。正确表述见 §18。

### 14.4 根因：食用油 G11 不在决策集

现实里中国人的膳食脂肪约三分之一来自烹调油。**G11（食用油）被 gate 挡在决策集外**，  
于是脂肪只能从肉蛋里来，AMDR 下界就变成了「红肉最低摄入量」约束。

G11 被挡的原因：`nutrition_gate = False`，11 个营养素**全部**不达标（0/11）。

**这里我先写错了一次，必须更正。** 初稿写的是「食用油本来就是纯脂肪，  
蛋白质/碳水/钙/铁结构性为零，gate 把『没有这一行』与『含量为零』当成同一件事」——  
听起来像 gate 设计缺陷。核对 `nutrients.csv` 后发现**不是**：

```
group_id=G11  nutrient=脂肪  value_per_kg=NaN  n_foods=0  n_observed=0
（其余 10 个营养素同样 n_foods=0）
```

**`n_foods = 0` 意味着食用油在 `food_crosswalk.csv` 里根本没有映射到任何食物条目**，  
不是「有食物但含量为 0」。所以 gate 的判断是对的：G11 确实没有营养数据。

真正的修法不是放宽 gate，而是**补一条 crosswalk**（例如把「大豆油」映射进 G11），  
其成分是脂肪 ≈ 1000 g/kg、能量 ≈ 37 000 kJ/kg、其余 9 项为 0。  
补上之后 gate 自然通过，不需要改判据。

这与 `docs/CHANGELOG_2026-10-26.md` §5 第 8 条（「G11 排除原因表述错误：  
实为 `nutrition_groups` 为空、根本没映射」）一致——**那条原本就是对的，是我在 §14.4 里写错了**。

### 14.5 对称检查：营养系数只需 10% 就能移动解

| 营养素                     | ±10% 扰动下解发生变化的比例（6 省） |
| ----------------------- | --------------------- |
| **脂肪**                  | **100%**              |
| 锌                       | 33%                   |
| 硒                       | 25%                   |
| 能量                      | 25%                   |
| 核黄素 / 碳水 / 烟酸 / 蛋白质 / 铁 | 0%                    |

与价格需要 20%–100% 形成鲜明对比：**不确定性该加在营养系数上，不是价格上**。

而营养系数的真实不确定性远大于占位的 5%：`nutrients.csv` 的 `sd_per_kg`  
给出组内食物间变异系数（CV = sd / mean）：

| 组          | 中位数 CV    | 最大 CV     | 组内食物数 |
| ---------- | --------- | --------- | ----- |
| G02 蛋类     | 0.275     | 0.433     | 3     |
| G05 禽肉     | 0.237     | 1.400     | 3     |
| G06 红肉     | 0.533     | 1.181     | 3     |
| **G08 蔬菜** | **1.494** | **2.028** | 5     |

红肉中位 CV 0.53、蔬菜 1.49。**占位用的 5% 低了 10–30 倍。**  
蔬菜的 CV 超过 1 意味着这个组的营养系数基本不可识别（大白菜与胡萝卜被平均成一个数）。

### 14.6 对设计的含义（需要作者裁定）

按代价从低到高：

1. **把 G11 食用油纳入决策集**（修 gate：单一成分食物的缺失项按 0 处理）。  
   这是唯一能解开「脂肪 → 红肉」锁的改动，且顺带让成本目标有了真实替代关系。
2. **重新考虑脂肪下界**。AMDR 20% 是长期膳食指导，不是每日硬约束；  
   在只有 4 个组的模型里把它当硬下界，等价于强制红肉。
3. **场景生成器改押营养系数**，用 `sd_per_kg` 的组内 CV，而不是价格 5% CV。  
   这样 D3 的机会约束才可能真的被触发。
4. 若以上都不动，那么诚实的结论是：**在本设计下价格不确定性对决策无影响**。  
   这本身是一个可发表的结果，但它是「零效应」，与 C2 的预期方向相反，  
   必须改叙事，不能靠调参掩盖。

### 14.7 本轮新增文件

| 文件                                         | 说明                                                                                           |
| ------------------------------------------ | -------------------------------------------------------------------------------------------- |
| `scripts/diagnose_decision_sensitivity.py` | 新增，价格平台宽度 + 营养系数敏感度双向诊断                                                                      |
| `outputs/DIAG_decision_sensitivity_*/`     | `sensitivity_scan.csv` / `flip_thresholds.csv` / `nutrient_sensitivity.csv` / `metrics.json` |

`evidence_status = diagnostic_only`：本诊断不进入论文证据链，只用于支撑设计决策。

---

## 十五、M3 敏感性网格（R300–R303）与 Big-M 诊断（R306）

运行：`outputs/M3_all_smoke_20261026_181618`（smoke：3 重复 / 6 省可用 / 山东硬不可行跳过）  
与 `outputs/R306_big_m_20261026_181747`（toy 问题 5 个种子）。

**证据等级仍是 `plumbing_only`**（场景为占位噪声）。下面只采信两类结论：  
**单调性方向**与**结构性事实**——这两类不依赖噪声的具体分布形式。

### 15.1 R301 场景数：可行率在 S=25 就已达平台，我原先的假设被推翻

| S   | 求解成功率 | 翻转率  | gap 均值 | 平均耗时        |
| --- | ----- | ---- | ------ | ----------- |
| 25  | 83%   | 0.20 | 0.104  | **0.04 s**  |
| 50  | 83%   | 0.33 | 0.107  | 0.31 s      |
| 100 | 83%   | 0.33 | 0.105  | 1.03 s      |
| 200 | 83%   | 0.40 | 0.119  | 3.94 s      |
| 400 | 83%   | 0.33 | 0.119  | **20.15 s** |

**可行率从 S=25 到 S=400 完全不动（都是 83%）。**

这直接**推翻了我此前在 tracker 里写的假设**：「江苏在 ε=0.05、S=20 下失败是因为  
`floor(0.05×20)=1`，容错太窄，属 S 过小的取整效应」。若是取整效应，S 增大后  
可行率必须上升。实测完全不动 → **失败是结构性的，与场景数无关**。

耗时方面 S 从 25 增到 400（16 倍），时间从 0.04 s 增到 20.15 s（**500 倍**）。  
S=200 是性价比拐点：再往上翻倍只换来更慢，可行率与 gap 都不变。

### 15.2 R302 ε 网格：单调递增，在 0.05 饱和

| ε    | 求解成功率   | 翻转率  | gap 均值 | 平均耗时   |
| ---- | ------- | ---- | ------ | ------ |
| 0.00 | 56%     | 0.60 | 0.190  | 0.12 s |
| 0.02 | 72%     | 0.46 | 0.147  | 1.38 s |
| 0.05 | **83%** | 0.40 | 0.123  | 4.22 s |
| 0.10 | **83%** | 0.20 | 0.099  | 6.96 s |

方向正确且单调：ε↑ → 可行率↑、翻转率↓、遗憾↓。这是与噪声结构无关的结论，可采信。  
但 **0.05 之后饱和**，ε 再翻倍也救不了那 17%——即江苏。

**江苏为什么在任何 ε 下都失败？** 逐项查过它的约束余量：

| 省份     | 余量最小的营养约束 | 相对余量              |
| ------ | --------- | ----------------- |
| 安徽     | 硒         | 7.0%              |
| **江苏** | **硒**     | **6.0%**（锌 14.7%） |
| 江西     | 硒         | 12.9%             |
| 福建     | 脂肪        | 14.1%             |

江苏的硒只差 6% 的余量，而噪声 CV 是 5%。单看这一个营养素，违反概率约 10%，  
200 个场景里约 20 个违反，正好卡在 ε=0.10 的边界上。但机会约束是**联合**的  
（一个场景必须所有营养素都满足），9 个营养素各自几个百分点的违反概率会复合，  
实测把 ε 推到 **0.30** 才可行（允许 60/200 违反）。

**这是一个设计层面的结论，不是调参能解决的**：当 K=4、营养约束条条贴边时，  
联合机会约束要求 ε 大到失去「可靠性约束」的意义（30% 违反率）。  
要么增加决策维度让约束有真实余量，要么把「联合」改成逐营养素（R305 的范围），  
要么承认这套机会约束在本设计下不可用。

### 15.3 R300 机会约束删除：D2 的语义得到数值确认

| 设定         | 求解成功率 | 可行(活跃)   | 翻转率  | gap 均值 |
| ---------- | ----- | -------- | ---- | ------ |
| D3（联合机会约束） | 83%   | **100%** | 0.40 | +0.123 |
| D2（无营养约束）  | 100%  | **0%**   | 1.00 | −0.715 |

D2 永远「能解」（因为没有营养约束，任何 q 都可行），但解出来的 q  
在真值上 **0% 满足营养约束**，且 gap 为负（−0.715）——它靠违反约束换来了便宜。  
这正是 `objective_gap` 用有符号值的意义：负值不是「负遗憾」，是「违规套利」。

机会约束的净贡献因此可以量化：**把可行率从 0% 提到 100%**，代价是 17% 的实例  
（江苏）无解、平均目标变差 0.84（从 −0.715 到 +0.123）。

### 15.4 R303 目标权重：方向稳定

| 权重 | 求解成功率 | 翻转率 | gap 均值 | 最大 |Δq| |  
|---|---|---|---|--- | --- | --- |  
| original (0.5/.25/.25) | 83% | 0.40 | 0.123 | — |  
| equal (1/3 each) | 83% | 0.33 | 0.128 | **18.23 g/day** |

逐省最大差异：上海 18.23、福建 12.58、江西 0.95、安徽 0.00、浙江 0.00。

**权重换掉后可行率不变、翻转率与遗憾基本不变**，最大位移 18 g/day  
（相对蔬菜 400 g 的量级是 4.5%）。方向稳定，不构成「结果靠权重挑出来」的风险。

### 15.5 R306 Big-M：tight 与 global 完全等价，但对照本身有效

先确认这个对照不是空转——tight M 在 toy 问题上的跨度：

| S   | M 最大/最小 | global/逐项均值 |
| --- | ------- | ----------- |
| 20  | 2.38    | 1.55        |
| 50  | 2.53    | 1.65        |
| 100 | 2.58    | 1.67        |

M 有 2.4–2.6 倍跨度，global 比逐项均值大 1.6 倍——**不是同一个模型**。

| S   | 模式             | 求解成功率       | 平均耗时          | 目标均值                |
| --- | -------------- | ----------- | ------------- | ------------------- |
| 20  | tight / global | 100% / 100% | 0.053 / 0.052 | 0.134632 / 0.134632 |
| 50  | tight / global | 100% / 100% | 0.200 / 0.210 | 0.132556 / 0.132556 |
| 100 | tight / global | 100% / 100% | 0.674 / 0.687 | 0.125946 / 0.125946 |

**最优解逐位相同（Δq = 0.0000），耗时差 < 2%。**

诚实的结论是：**在这个 toy 规模上，tight Big-M 没有测出性能收益**。  
它仍应保留（默认值），因为它是「不裁剪可行解」的防御性选择，  
且 M 只有 1.6 倍差异时本来就不该期待显著加速。  
把这条写成「tight 显著更快」会是过度解读。

真实实例（S=200 × 9 营养素 = 3600 行）上的对照没有做——那已超出 R306  
「toy only」的范围，且 M 跨度会更小（营养系数乘子扰动只有 ±5%）。

### 15.6 本轮新增文件

| 文件                              | 说明                                            |
| ------------------------------- | --------------------------------------------- |
| `scripts/run_m3_sensitivity.py` | R300–R303 统一驱动，场景按 `(S, seed)` 缓存             |
| `scripts/big_m_diagnostic.py`   | R306，tight vs global，含 M 跨度自检                 |
| `src/robust_modopt.py`          | 新增 `big_m="tight"｜"global"` 参数（默认 tight，向后兼容） |

### 15.7 一处需要更正的旧记录

tracker 里 R201/R203 的备注写着「江苏 D3 失败属 S 过小的取整效应」。  
**这条已被 R301 推翻**：S 从 25 扫到 400 可行率不变。已改为「结构性的  
`slack/CV` 不足 + 联合机会约束的复合违反」。

---

## 十六、R108 / R109 正式批次（价格面板，5 折 × 20 重复）

运行：`outputs/R108_109_price_formal_20261026_175443`（**5493 s ≈ 1h 32min**，单进程）。

这是今日最后一个跑完的正式批次。**证据等级与 B2 不同**：R108/R109 的真值是  
**遮蔽前的实测价格**，不依赖 B2 的占位场景生成器，因此结论可用；  
但缺失机制是**人造的 MCAR 遮蔽**，不是真实缺失机制——这一点必须随结果报告。


### 16.1 R109 MNAR δ 网格：覆盖率对 δ 单调下降，主方法最稳

δ 表示「被遮蔽格真值系统性偏离 MAR 预测 δ 个残差 SD」。δ ∈ {−0.5, 0, +0.5}（预注册）。

**cov95**：

| 遮蔽                | 方法              | δ=−0.5 | δ=0       | δ=+0.5 |
| ----------------- | --------------- | ------ | --------- | ------ |
| single_cell       | hierarchical_rw | 0.955  | **0.940** | 0.937  |
| single_cell       | group_mean      | 0.933  | 0.913     | 0.903  |
| single_cell       | interpolation   | 0.883  | 0.887     | 0.878  |
| single_cell       | mice            | 0.778  | 0.865     | 0.793  |
| consecutive_years | hierarchical_rw | 0.980  | **0.955** | 0.925  |
| consecutive_years | group_mean      | 0.960  | 0.925     | 0.875  |
| consecutive_years | interpolation   | 0.855  | 0.865     | 0.850  |
| consecutive_years | mice            | 0.745  | 0.830     | 0.765  |
| province_group    | hierarchical_rw | 0.979  | **0.954** | 0.929  |
| province_group    | group_mean      | 0.936  | 0.919     | 0.897  |
| province_group    | interpolation   | 0.792  | 0.825     | 0.810  |
| province_group    | mice            | 0.745  | 0.751     | 0.730  |

三条读法：

1. **主方法在三种遮蔽、δ=0 处的 cov95 分别是 0.940 / 0.955 / 0.954**，与名义 0.95  
   相差不超过 1 个百分点——这是今天唯一一处「标定真的接近名义值」的证据。
2. **正向 MNAR（δ=+0.5，真值高于预测）会打穿区间**：主方法掉到 0.925–0.937。  
   方向合理——真值系统性偏高时，以预测为中心的区间自然欠覆盖。δ=−0.5 时反而过覆盖（0.955–0.980）。
3. **MICE 在 province_group 下崩溃到 0.730–0.751**，与 R102 一致；在 single_cell 下  
   反而 0.865，是「只在整块缺失时失效」的典型。

### 16.2 排序稳定性：主方法在 9 个格子里全部第 1

按 calibration_error 排名（1 = 最好）：

| 方法                  | consecutive_years (−/0/+) | province_group (−/0/+) | single_cell (−/0/+) |
| ------------------- | ------------------------- | ---------------------- | ------------------- |
| **hierarchical_rw** | **1 / 1 / 1**             | **1 / 1 / 1**          | **1 / 1 / 1**       |
| group_mean          | 2 / 2 / 2                 | 2 / 2 / 2              | 2 / 4 / 3           |
| interpolation       | 3 / 3 / 3                 | 3 / 3 / 3              | 3 / 3 / 2           |
| mice                | 4 / 4 / 4                 | 4 / 4 / 4              | 4 / 2 / 4           |

**主方法在全部 9 个 (遮蔽 × δ) 组合下都是第 1 名。** 这是方法选择最有力的证据——  
不是「在某个设定下赢」，而是「在敏感性网格的每个格子里都赢」。

注意 smoke 版本曾显示「consecutive_years 在 δ=0 时 group_mean 更好」，  
正式批次**没有复现**这个反转（group_mean 恒为第 2）。smoke 的样本量不足以支撑排序结论，  
这条已作废。


### 16.3 R108 MAR 诊断：所有方法都低估高值，主方法不是最轻的

`bias_slope` = 按真值五分位的标准化偏差对分位序号的斜率，0 表示无系统偏差。

| 遮蔽                | 方法              | bias_overall | bias_slope |
| ----------------- | --------------- | ------------ | ---------- |
| single_cell       | hierarchical_rw | −1.175       | **−0.455** |
| single_cell       | group_mean      | −0.239       | −0.332     |
| single_cell       | interpolation   | +0.308       | −0.188     |
| single_cell       | mice            | +0.449       | −0.227     |
| province_group    | hierarchical_rw | −0.887       | −0.341     |
| province_group    | mice            | **−4.818**   | **−0.991** |
| consecutive_years | hierarchical_rw | −0.867       | −0.264     |
| consecutive_years | group_mean      | −1.579       | −0.394     |

**所有 12 个 (遮蔽 × 方法) 组合的 bias_slope 都是负的，无一例外。**  
即：**高值被系统性低估**。

这是今天最重要的负面发现之一，必须写进论文限制：  
**cov95 接近 0.95 不等于无偏**。主方法在 single_cell 上的 slope（−0.455）  
甚至比 interpolation（−0.188）更差——它标定得好，但偏差更大。  
只报覆盖率会掩盖这一点。

单看五分位（single_cell / hierarchical_rw）：

| 分位 | 真值均值  | 偏差        | 标准化偏差  |
| -- | ----- | --------- | ------ |
| Q1 | 5.53  | +1.10     | +0.198 |
| Q2 | 9.79  | +0.45     | +0.046 |
| Q3 | 19.17 | +2.84     | +0.148 |
| Q4 | 36.14 | −1.60     | −0.044 |
| Q5 | 80.50 | **−8.66** | −0.108 |

低价被高估、高价被低估——典型的**向均值收缩**。Q5 平均低估 8.66 元/kg（约 11%）。

### 16.4 顺带发现：`interpolation` 在整块遮蔽下根本不是另一个方法

province_group 遮蔽下，`interpolation` 与 `group_mean` 的预测**逐格完全相同**  
（比对 `B1_formal_withmice_20261023_124906/cell_predictions.csv`，  
1200/1200 格差值 < 1e-9，比例 1.0000）。consecutive_years 下相同比例为 0.0000。

原因显然：整块缺失时该省该组**没有任何相邻年份**可插值，只能退化为组均值。

因此 R102 / R105 里「interpolation 在整块缺失下严重欠覆盖（cov95 0.691 / 0.825）」  
这句话**必须改写**：它不是「插值方法表现差」，而是「插值在这个遮蔽几何下  
等价于组均值，而组均值本身欠覆盖」。两者的方法论含义完全不同——  
前者说「别用插值」，后者说「这个遮蔽设计让一个对照组失效了」。

### 16.5 一处流程缺陷（已修）

`sensitivity_mar_mnar.py` 原先只写 `metrics.json`，**没有调用 `finalize_run`**，  
因此本次正式运行缺 `config.json` / `environment.json` / `DONE`，且 `metrics.json`  
里没有 `evidence_status` 字段。

- 脚本已补上 `finalize_run` 与 `evidence_status="masking_protocol"`；
- 本次运行的元数据**事后补齐**（只写 config/environment/DONE 与 evidence 字段，  
  **未改动任何结果 CSV**），并在 `metrics.json` 里留了 `bookkeeping_note` 说明。

同类问题在 `run_m3_sensitivity.py` 与 `diagnose_decision_sensitivity.py` 也各出现过一次  
（`finalize_run` 少传 `config` 参数）。三个脚本已统一修正。

**另一处**：`run_b2.py --dry-run` 原先也写 `DONE`，但 dry-run 只产出  
`diagnostics.json`，没有 `b2_results.csv` 与 `metrics.json`。下游按  
「DONE + metrics.json」扫描 run 时会把「只做了装配诊断」误当成「实验完成」。  
已改为写独立的 `DRY_RUN` 标记，并把 `R200_203_b2_smoke_20261026_181806`  
（本次 dry-run）的 `DONE` 换成 `DRY_RUN`。

**共同根因**：完成标记是脚本各自手写的，没有统一的「什么算完成」的定义。  
建议后续在 `src/io_utils.py` 里把「必产文件清单」变成 `finalize_run` 的必需参数，  
缺文件直接抛错，而不是靠人记住。

---

## 十七、收工快照（2026-10-26 19:40）

两个后台批次均正常结束，无残留进程，测试 31/31 通过。

| 批次                    | run                                          | 耗时               | 状态               |
| --------------------- | -------------------------------------------- | ---------------- | ---------------- |
| M3 敏感性网格 R300–R303    | `M3_all_smoke_20261026_181618`               | 15 min           | DONE（smoke）      |
| Big-M 诊断 R306         | `R306_big_m_20261026_181747`                 | < 1 min          | DONE（toy）        |
| MAR/MNAR 正式 R108–R109 | `R108_109_price_formal_20261026_175443`      | 5493 s ≈ 1h32min | DONE（**formal**） |
| R103–R105 消费面板        | `R103_105_consumption_formal_*`（1 主 + 20 分片） | —                | DONE（**formal**） |

**证据等级分布**（这点明天续接时最容易搞混，先钉住）：

- **formal**：R103–R105（消费面板）、R108–R109（价格面板）→ 可直接进论文
- **smoke / plumbing_only**：M3 全部（R300–R303）、M2 全部（R200–R203）→ 只能支撑方向性结论
- **toy**：R306 → 只支撑「tight 不劣于 global」，不能写成「显著更快」

**一处运行目录的归属已标注**：`R306_big_m_20261026_181722` 是被取代的首次运行  
（早于 M 跨度自检补丁），已写 `SUPERSEDED` 说明；结果与 181747 逐位相同，  
runtime 差 0.13–0.19 s 属计时抖动。引用时用 **181747**。

### 明天从哪开始

> **后续更新（2026-10-27）**：本节列的「之后才是 R304/R305/R307」已完成，  
> M3 现为 **8/8 DONE**。且 R307 的结论改写了下方第 1 条与第 3 条阻塞的定性——  
> 山东的硬不可行与价格零传导都被证明是 K=4 门限的产物。详见 **§19**。

不需要重跑任何东西。三件事按优先级：

1. **三个口径决策待作者签字**（这是 M2 的唯一硬阻塞，其余都在等它）：
   - 钙：纳入 G01 乳制品 / 改软约束 / 承认不可达并只报两口径；
   - 山东 `{碳水化合物, 硒}` 冲突：踢出主表 / 单独报告 / 放宽碳水上界；
   - 脂肪下界与 G11 缺位：补 crosswalk（最省事）/ 放开 AMDR 下界 / 改押营养系数不确定性。
2. **场景生成器仍是占位噪声**（`placeholder_scenarios`）。M3 的结论之所以只敢说  
   「方向」，就是因为噪声形式是我编的。要出正式 M2 结果，必须先接真实残差结构。
3. 之后才是 R304/R305/R307（均 NICE）与 M4/M5。

### 本轮修的流程缺陷（三条，同一根因）

`finalize_run` 缺 `config` 参数（3 个脚本）、`--dry-run` 误写 `DONE`、  
MAR 脚本不写 `evidence_status`。共同根因是「什么算完成」由各脚本手写。  
建议把必产文件清单变成 `finalize_run` 的必需参数——**这件事没做，留作 TODO**。

---

## 十八、诊断（DIAG\_*）：正面检验 §14 的因果解释 —— 一半成立，一半被推翻

运行：`outputs/DIAG_objective_20261026_193437`（`scripts/diagnose_objective_degeneracy.py`）、  
`outputs/DIAG_binding_20261026_193238`（`scripts/verify_binding_constraints.py`）。

§14 把「价格零传导」解释&#x4E3A;**「脂肪下界钉死红肉量，模型退化成一个等式」**。  
这个解释此前只有间接证据（脂肪系数 ±10% 会移动解、价格 ±50% 不动）。  
间接证据撑不起因果链——营养系数敏感也可能只是因为它是紧约束，  
价格不敏感也可能另有原因。本节点把最优点代回全部约束，正面检验。

### 18.1 成立的部分：脂肪下界确实在 6/6 省都紧

| 省份 | 脂肪下界  | 实际达成  | 相对余量 | 状态    |
| -- | ----- | ----- | ---- | ----- |
| 上海 | 25.66 | 25.66 | 0.0  | tight |
| 安徽 | 27.83 | 27.83 | 0.0  | tight |
| 江苏 | 27.06 | 27.06 | 0.0  | tight |
| 江西 | 27.59 | 27.59 | −0.0 | tight |
| 浙江 | 26.28 | 26.28 | 0.0  | tight |
| 福建 | 28.07 | 28.07 | 0.0  | tight |

**6/6 省、`rel_slack` 精确为 0。** 这一条事实成立。

顺带更正一处我自己的判定口径 bug：初版用 `slack/scale <= tol` 判「紧」，  
把**违反**（负余量）也算成了紧，于是钙（−0.79）、硫胺素（−0.40）被错误地  
列进「紧约束」。已改为三态 `violated / tight / slack`。  
改后可见：钙与硫胺素在 6/6 省都是 `violated`——这正是 §「四个阻塞问题」第 2 条  
的已知设计（`active_mask=False` 的不可达营养素不进机会约束），两者互相印证。

### 18.2 被推翻的部分：红肉量并没有被钉住

| 省份 | 蛋 G02 | 禽 G05 | 红肉 G06 | 蔬菜 G08 | 畜禽合计 |
| -- | ----- | ----- | ------ | ------ | ---- |
| 上海 | 50.0  | 43.5  | 31.5   | 385.1  | 75.0 |
| 安徽 | 50.0  | 31.0  | 44.0   | 437.9  | 75.0 |
| 江苏 | 50.0  | 30.5  | 44.5   | 314.1  | 75.0 |
| 江西 | 50.0  | 30.4  | 44.6   | 391.5  | 75.0 |
| 浙江 | 50.0  | 35.2  | 39.8   | 300.0  | 75.0 |
| 福建 | 50.0  | 22.8  | 52.2   | 300.0  | 75.0 |

三点事实与「钉住」相冲突：

1. **红肉量省际差 26.4 g**（31.5 上海 ↔ 52.2 福建），不是一个固定值；
2. **禽肉/红肉的分配由成本决定**——江西纯成本权重下禽肉从 30.4 直接归零、全换红肉；
3. **畜禽合计卡的是上界 75**，不是下界 40。我原先以为是「达到脂肪下界要顶到 40 下界」，  
   实际是六省全部顶到 **75 上界**。脂肪下界与合计上界同时紧，  
   意味着「总量给定、构成由脂肪需求决定」，而不是「红肉量给定」。

### 18.3 真实结构：12–14 个顶点的选择问题

穷举可行域全部顶点（`K=4`，组合数 6k–9k 量级，可精确枚举）：

| 省份 | 约束数 | 顶点数 | 基线解紧约束数 | 秩 | 零空间维数 |
| -- | --- | --- | ------- | - | ----- |
| 上海 | 23  | 12  | 4       | 4 | 0     |
| 安徽 | 21  | 13  | 4       | 4 | 0     |
| 江苏 | 23  | 14  | 4       | 4 | 0     |
| 江西 | 21  | 12  | 4       | 4 | 0     |
| 浙江 | 21  | 12  | 4       | 4 | 0     |
| 福建 | 23  | 12  | 4       | 4 | 0     |

**秩 = K、零空间 0 维**：基线解是**孤立顶点**，不是一条边或一个面。  
但可行域里有 **12–14 个**别的顶点，成本在这些顶点之间做选择。

六省共同的三条紧约束：

- **脂肪下界**（6/6）；
- **蛋类上界 50 g**（6/6，G02 顶格）；
- **畜禽肉合计上界 75 g**（6/6，联合约束顶格）。

第四条因省而异：上海是能量下界，安徽/江西是硒下界，江苏是锌下界，浙江/福建是蔬菜下界 300 g。  
**这一条决定了 G05/G06 怎么分配**——也解释了为什么江苏的失败与锌有关、安徽江西与硒有关。

### 18.4 目标函数确实在起作用（这一点我原先说轻了）

| 权重                 | 上海        | 安徽       | 江苏       | 江西        | 浙江        | 福建        |
| ------------------ | --------- | -------- | -------- | --------- | --------- | --------- |
| 原始 (0.5/0.25/0.25) | 0         | 0        | 0        | 0         | 0         | 0         |
| 纯营养 (0/1/0)        | **0**     | **0**    | **0**    | **0**     | **0**     | **0**     |
| 纯成本 (≈1/0/0)       | 0         | 0        | 0        | **54.8**  | **35.2**  | **22.8**  |
| 纯环境 (0/0/1)        | **115.0** | **62.1** | **44.2** | **108.5** | **200.0** | **101.1** |

（数值为 `max |Δq|`，单位 g/day）

- **纯营养 = 原始解，6/6 省逐位相同。** 当前权重下的解实质上是**营养目标的最优解**。
- **纯成本在 3/6 省给出不同解**（江西禽肉 30.4 → 0）。所以多目标加权**不是摆设**：  
  原始解在原权重下比纯成本解优 **1.4%–3.7%**（江西 3.69%、浙江 2.23%、福建 1.44%）。
- **纯环境在 6/6 省都换顶点**，位移 22–200 g，主要动作是把蔬菜推到 500 g 上限。
- 随机 Dirichlet 权重 500 组：最大位移恰好等于纯环境的位移——  
  说明**权重空间的最极端方向就是环境主导**，成本与营养这两个方向彼此接近。

### 18.5 修正后的因果链

> 价格传导弱的真正原因**不是「解被唯一钉死」**，而是：  
> 解在 12–14 个候选顶点之间由成本选择，而**这些顶点之间的成本排序对 ±5% 的价格扰动很稳健**。  
> 要让排序翻转，需要 20%–100% 的价格变动（见 `DIAG_decision_sensitivity`）。  
> 而省内价 → 合并价的差异只有几个百分点，落在稳健区里，所以「零传导」。
>
> 叠加的结构性原因是：脂肪下界 + 蛋类上限 + 畜禽合计上限三条约束在 6/6 省同时紧，  
> 可行域被压成少数几个「营养上几乎等价、成本上略有差别」的顶点。  
> 顶点少 → 切换门槛高 → 价格看起来无效。

**这不是「模型坏了」，是「决策空间太窄」**：K=4 且三条约束同时顶格时，  
任何价格信号都只能在这几个顶点间做选择。要恢复价格传导，需要增加决策维度  
（如纳入 G01 乳制品、G11 食用油），而不是改求解器或改权重。

### 18.6 一处必须更正的处置建议：G11「补一条 crosswalk」不可行

§14.4 与 tracker 阻塞 3 都建议「补一条 crosswalk（如大豆油 → G11）即可解锁」。  
**核对数据后，这个建议低估了难度。** 三个输入的实际状况：

| 输入       | 是否有食用油 | 位置                                                             |
| -------- | ------ | -------------------------------------------------------------- |
| 价格       | **有**  | `price_panel_clean.xlsx` 品类 `食用油(升)`，7 省 × 9 年                 |
| 消费量      | **有**  | `consumption.csv` 的 `oils` 组，70 行（7 省 × 10 年）                  |
| **营养系数** | **没有** | `nutrition.csv` 的 50 个食物里**没有任何油**，`food_crosswalk.csv` 也无对应条目 |

crosswalk 只能把**已有食物**映射到组。`nutrition.csv` 里根本没有「食用油」这一行，  
所以没有可映射的对象——补 crosswalk 无从补起。

要真正纳入 G11，需要**新增一条营养记录**（外部来源，如《中国食物成分表》大豆油：  
脂肪 ≈ 99.9 g/100 g、能量 ≈ 899 kcal/100 g），并把价格的「升」按密度（≈0.92 kg/L）  
换算成 kg。这两步都引入了**仓库之外的假设**，必须显式标注来源并做敏感性。

**结论**：G11 是一个**需要外部数据接入**的任务，不是一条 crosswalk 的补丁。  
这也意味着阻塞 3 的「最省事选项」并不省事，需要作者在  
「引入外部营养数据」与「放开 AMDR 下界」之间做取舍。

### 18.7 本轮新增文件

| 文件                                         | 说明                         |
| ------------------------------------------ | -------------------------- |
| `scripts/verify_binding_constraints.py`    | 把最优点代回全部约束，三态报余量           |
| `scripts/diagnose_objective_degeneracy.py` | 顶点枚举 + 秩 + 极端权重 + 随机权重四步检验 |

### 18.8 一处命名撞车（已修）

这两个诊断最初被我编成 `R307_binding` / `R307_objective`，但 tracker 里  
**R307 已被预注册为「boundary gate on/off」**，是另一个实验。同号不同事，  
将来引用必然串线。已改名为 `DIAG_binding_*` / `DIAG_objective_*`  
（沿用仓库既有的 `DIAG_decision_sensitivity_*` 约定），脚本默认 `run_id` 同步改。  
**R307 在 tracker 里仍是 TODO，没有被本次诊断占用。**

---

## 十九、M3 收尾：R304 / R305 / R307 三条 NICE 消融（2026-10-27）

三个 run：

| run                                                                          | 脚本                               | 耗时                  |
| ---------------------------------------------------------------------------- | -------------------------------- | ------------------- |
| `outputs/R304_weight_uncertainty_20261027_143003`                            | `run_r304_weight_uncertainty.py` | 3 min               |
| `outputs/R305_chance_mode_20261027_142626` + `R305_high_eps_20261027_143744` | `run_r305_chance_mode.py`        | 10.5 min + 13.8 min |
| `outputs/R307_gate_20261027_142902`                                          | `run_r307_gate_sensitivity.py`   | 1 min               |

**R307 的结论最重要，而且推翻了两个阻塞的定性**——放在最前面。


### 19.1 R307：边界门放开后，「价格零传导」和「山东硬不可行」同时消失

正式门是「营养硬系数**全或无**」（11 项缺 1 项即出局），K=4。  
放宽口径（`trace_as_valid=False` + 覆盖率 0.90）进组 **G04 谷物及豆类**、**G07 水产品**，K=6。

**正式门一个字节没动**：脚本把契约文件复制到 run 目录下的 `shadow_processed/`，  
只替换 `group_audit.csv`，`Contract.load(processed=shadow)` 装配。`data/processed/` 保持原样。

#### (a) 价格传导：K=4 下「零传导」是决策空间太窄的产物

先钉住一个此前没说清的事实：**D1（省内价）与 D0（合并价）的相对价差并不小**——

| 省  | G02   | G05        | G06   | G08        |
| -- | ----- | ---------- | ----- | ---------- |
| 安徽 | +0.9% | −13.0%     | +1.0% | **−28.7%** |
| 江苏 | −4.9% | −17.9%     | +4.5% | **+29.9%** |
| 江西 | +5.4% | **+36.3%** | +8.1% | −4.1%      |
| 浙江 | +9.5% | +18.0%     | +4.4% | **+26.1%** |

**单组相对价差最大到 36%。** 而 K=4 下这六个省的 `max|Δq|` **全部精确为 0.00 g**。  
所以「零传导」不是「价差太小看不出」，而是**真的完全不动**——§14 的定性因此更强，不是更弱。

K=6 下同一个价差开始起作用：

| 口径  | D1vsD0 均值   | 最大        | 有位移的省                          |
| --- | ----------- | --------- | ------------------------------ |
| K=4 | **0.00 g**  | 0.00      | 0 / 6                          |
| K=6 | **19.91 g** | 54.00（江苏） | 3 / 6（江苏 54.0、福建 36.4、江西 29.0） |

**结论：价格信息本身是有的，是 K=4 的决策空间把它挡在门外。**  
这不是「数据无价格信号」，也不是「求解器坏了」。

> **⚠️ 上面这段的归因已更正（见 §20）。** 本次放宽同时改了两个旋钮  
> （`trace_as_valid` 与 `min_cell_coverage`），且门限在 c=1.0 处存在**判据切换**。  
> 2×2 因子分解显示：**恢复价格传导的是 G07 水产品这一个组，不是「K 变大」**  
> ——K=5 且含 G04 的口径（D）价格传导仍为 0/7 省。G04 的作用是解决山东的硬不可行。

#### (b) 山东：硬不可行的根因是「把谷物钉在基线」，不是营养需求冲突

| 口径  | 山东 hard_feasible            | 碳水化合物有效区间        | 碳水 offset  |
| --- | --------------------------- | ---------------- | ---------- |
| K=4 | **False**（冲突集 `{碳水化合物, 硒}`） | [−25.75, 49.25]  | **275.75** |
| K=6 | **True**                    | [210.45, 285.45] | **39.55**  |

机制很直接：K=4 把 G04（谷物豆类）固定在观测基线，它的碳水贡献（约 236 g）  
被算进 offset，于是决策组只能再贡献 ≤49.25 g 碳水；而要从蛋/禽/红肉/蔬菜凑够  
39.53 g 硒，必然把碳水顶穿上界。G04 一旦成为决策变量，offset 降到 39.55，  
碳水区间变成「必须提供 210–285 g」——由谷物满足，硒由水产品满足，冲突消失。

**这改变了阻塞 2 的性质**：山东的 `{碳水化合物, 硒}` 不是「营养需求与食物供给的  
真实冲突」，而&#x662F;**「K=4 把最大碳水来源钉死」造成的建模产物**。  
原方案（踢出主表 / 单独报告 / 放宽碳水上界）都不必了。

#### (c) 代价：上海出局，共同组数值大幅位移

| 省  | 状态变化                                        |
| -- | ------------------------------------------- |
| 上海 | K=6 **不可用**（`complete_provinces` 报缺 G07 数据） |
| 山东 | K=4 不可行 → K=6 **可行**                        |

共同组（G02/G05/G06/G08）在两种口径下的位移：

| 省  | G02 | G05    | G06    | G08         | max    |
| -- | --- | ------ | ------ | ----------- | ------ |
| 安徽 | 0.0 | −13.78 | +13.78 | +39.52      | 39.52  |
| 江苏 | 0.0 | −5.49  | +5.49  | +99.65      | 99.65  |
| 江西 | 0.0 | −16.35 | +16.35 | +60.61      | 60.61  |
| 浙江 | 0.0 | −13.25 | +13.25 | **+171.58** | 171.58 |
| 福建 | 0.0 | −7.04  | +7.04  | +142.87     | 142.87 |

蛋类纹丝不动（两种口径都顶 50 g 上界）；禽/红肉按合计 75 g 互补地重分配；  
**蔬菜位移 39–172 g**。也就是说：**论文里关于蔬菜量与红肉/禽肉分配的数字，  
是 K 值依赖的，必须随门限口径一起报告。**


### 19.2 R305：联合 vs 逐营养素机会约束 —— 江苏的困难不是「联合」造成的

`src/robust_modopt.py` 新增 `chance_mode="joint"|"marginal"`（默认 joint，正式口径不变）。  
marginal 给每个 (场景, 营养素) 一个 `z_sj`，逐营养素预算 `Σ_s z_sj ≤ floor(εS)`。

**先验证 joint 的实现是对的**：实测联合违反率

| ε             | 0.02  | 0.05  | 0.10  | 0.20  | 0.30  |
| ------------- | ----- | ----- | ----- | ----- | ----- |
| joint 实测联合违反率 | 0.020 | 0.050 | 0.100 | 0.200 | 0.299 |

**精确等于 ε**，五个点全中。联合机会约束的标定是准的，这条可以写进方法可信度。

marginal 则如理论所料**不兑现 ε**：

| ε    | joint 联合违反 | marginal 联合违反 | 倍数   |
| ---- | ---------- | ------------- | ---- |
| 0.02 | 0.020      | 0.036         | 1.8× |
| 0.05 | 0.050      | 0.086         | 1.7× |
| 0.10 | 0.100      | 0.170         | 1.7× |
| 0.20 | 0.200      | 0.326         | 1.6× |
| 0.30 | 0.299      | 0.461         | 1.5× |

理论上界是 `J·ε = 9ε`，实测只有 **1.5–1.8 倍**——说明各营养素的违反场景高度重叠  
（同一批「极端场景」同时打穿多个营养素），不是相互独立的。这解释了为什么  
联合约束没有想象中那么苛刻。

**江苏到底需要多大 ε：**

| 模式       | ε=0.05 | 0.10 | 0.20   | 0.30   |
| -------- | ------ | ---- | ------ | ------ |
| joint    | 不可行    | 不可行  | 不可行    | **可行** |
| marginal | 不可行    | 不可行  | **可行** | 可行     |

marginal 把门槛从 0.30 降到 0.20，但**没有把江苏救回来**。

> **这修正了 §15.2 的解释。** 当时写的是「9 个营养素各自的违反概率复合，  
> 所以需要 ε≈0.30」。若复合是根因，逐营养素约束应当让小 ε 就可行。  
> 实测 ε=0.05 仍然不可行 → **根因是营养素本身的余量不足**（硒 6.0%、锌 14.7%），  
> 联合性只是把门槛从 0.20 放大到 0.30（约 1.5 倍），不是根因。

**计算代价**：marginal 的二元变量是 `S×J = 1800` 个（joint 是 200 个），  
高 ε 时严重退化——ε=0.30 平均 117 s，上海超过 240 s 仍未解出。  
这也是为什么正式口径必须留在 joint：**不是为了更严，而是 marginal 算不动**。

### 19.3 R304：目标权重的不确定性影响很小，浙江除外

权重按 `Dirichlet(κ·w0)` 抽样（均值恰为 `w0`），场景固定为点估计（S=1）以隔离权重效应。  
每省每档 200 次抽样，遗憾按 `normalized_cost_vector` 在真实权重 `w0` 下评估。

| 集中度 | κ | 平均遗憾 | p95 | 最大 | 至少一组翻转 | max|Δq| p95 |  
|---|---|---|---|---|---|--- | --- | --- |  
| tight | 100 | 0.0000 | 0.0000 | 0.16% | 0.0% | 0.00 |  
| medium | 20 | 0.06% | 0.52% | 0.91% | 1.2% | 9.67 |  
| loose | 5 | 0.28% | 0.54% | 6.60% | 4.3% | 10.19 |

即使把权重放到很松（κ=5，成本权重的标准差约 20 个百分点），  
**平均遗憾仍只有 0.28%、翻转率 4.3%**。权重不是主要不确定性来源。

例外是浙江：loose 档最大遗憾 **15.0%**、翻转率 **23.5%**、最大位移 35.2 g。  
原因是浙江有两个成本接近的顶点（与 DIAG_objective 里「纯成本解 vs 原始解差 35.2 g」一致）。  
**报告时应当点名浙江对权重最敏感，而不是笼统说「权重稳健」。**

### 19.4 本轮修的三个工程问题

1. **`write_json` 遇到 NaN 会让整个 run 崩掉**（`allow_nan=False`）。  
   `_finite` 已在 `sensitivity_mar_mnar.py` 与 `diagnose_decision_sensitivity.py` 各抄一份，  
   本轮没再抄第三份，而是把清洗放进 `io_utils.write_json`：  
   输入侧的 NaN 仍显式报错（`solve_chance_modopt` 的校验不变），  
   输出侧元数据记为 `null`，结果 CSV 保留原始值。
2. **`solve_chance_modopt` 的多目标归一化抽成 `normalized_cost_vector()`**。  
   原先 R304 需要在「求解器之外的代码」里重算加权目标值，口径容易漂；  
   现在求解与评估共用同一函数。
3. **R305 首轮把「超时」记成了「失败」**。`--time-limit 45` 下有 6 个格子撞上限，  
   求解率被低估（marginal ε=0.20 显示 0.667，实际 1.000）。  
   已加 `timed_out` 字段，并用 `--time-limit 240 --mip-rel-gap 0.01` 重算高 ε 格子。  
   **这类错误会直接把「算不完」写成「不可行」，是最容易骗过自己的一种。**

---

## 二十、R307b：边界门的 2×2 因子分解 —— §19.1(a) 的归因是错的

运行：`outputs/R307b_gate_factorial_20261027_145412`（`scripts/run_r307b_gate_factorial.py`，1 min）。

### 20.1 起因：§19.1 同时动了两个旋钮

§19.1 比较「正式 K=4」与「放宽 K=6」，但那次放宽同时改了两件事：

1. `trace_as_valid`：True → False；
2. `min_cell_coverage`：1.00 → 0.90。

两处同时动，把「K 变大导致价格传导恢复」当成了结论——**这是混淆**。  
更要紧的是，`scripts/build_group_audit.py` 的营养门是**双分支**：

```python
if min_cell_coverage >= 1.0:
    gate = 每个营养素的组内食物覆盖都 == 1.0        # 全或无
else:
    gate = 组内整体格子比例 >= min_cell_coverage     # 平均比例
```

**c=1.0 与 c=0.999 不是同一条规则的松紧，而是两条不同的规则。**  
所以现有的「门限敏感性」表（0.80/0.85/0.90/0.95/1.00）把一次**判据切换**  
混在了同一列阈值里，不能读作阈值敏感性。这一条本身就是设计缺陷，需在论文里说明。

具体到 G04/G07：两者都只缺**一个痕量格**（G04 是 44 格里缺 1，`cell_ratio=0.977`；  
G07 是 33 格里缺 1，`cell_ratio=0.970`）。在 c=1.0 分支下它们因「某个营养素没有  
覆盖全部食物」出局；切到 c=0.95 分支后按平均比例就过了。  
**一个痕量格，决定了 K 从 4 跳到 6。**

### 20.2 四口径结果

| 口径        | trace | c    | K | 组集合                   | 可用省        | 山东       | 价格传导    |
| --------- | ----- | ---- | - | --------------------- | ---------- | -------- | ------- |
| A 正式      | True  | 1.00 | 4 | G02 G05 G06 G08       | 7          | **硬不可行** | **0/6** |
| B         | True  | 0.95 | 6 | A + **G04** + **G07** | 6（上海缺 G07） | 可行       | **3/6** |
| C 预注册 K=3 | False | 1.00 | 3 | G02 G05 G08           | 7          | **硬不可行** | 0/6     |
| D         | False | 0.95 | 5 | A + **G04**           | 7          | **可行**   | **0/7** |

**关键对比是 A / D / B**：模型系数不随 trace 设定变化（`nutrients.csv` 只有一份），  
变的只是入组集合。所以：

- **A → D 只差 G04**：山东由不可行变可行，**价格传导仍为 0/7**；
- **D → B 只差 G07**：山东已可行，**价格传导由 0/7 变成 3/6**。

### 20.3 结论：两个效应各有各的原因，与「维度多少」无关

> **§19.1(a) 说的「K 从 4 变 6，决策维度变多，所以价格传导恢复」是错的。**  
> 正确的归因是：
>
> - **G04（谷物及豆类）→ 解决山东的硬不可行**（碳水 offset 275.75 → 39.55）；
> - **G07（水产品）→ 恢复价格传导**（0/7 → 3/6）；
> - **两者都与 K 的大小无关**。D 的 K=5 比 A 的 K=4 更大，价格传导照样是 0。

为什么是 G07：它提供了一条**低成本满足硒/蛋白质**的通道。B 口径下江苏的  
两个候选顶点在 D1 价格下的加权目标值只差 **0.999%**（江西 0.070%、福建 0.086%），  
属于近似平局，中等幅度的价格变动就能翻转；A/D 下同一价差（单组最大 36%）  
不发生任何翻转。**传导与否取决于竞争顶点的成本差有多近，不取决于维度数。**

顺带：C（K=3）与 A 一样是 0/6，但 C 下上海的共同组位移达 85.05 g  
——**K=3 会让上海的数字大幅变化**，而 K=3 正是原始预注册口径。这条对论文的  
「预注册 vs 主口径」偏离说明有用。

### 20.4 对 K 值决策的含义

原来我准备建议「先定 K 再跑 M2」。现在这个建议要改写成：

**K 的选择不是选一个维度数，而是选「哪些组必须进模型」**，且这两个组要分别论证：

| 组             | 进入的理由                   | 不进入的代价             |
| ------------- | ----------------------- | ------------------ |
| **G04 谷物及豆类** | 不进入则山东硬不可行（碳水被基线钉死）     | 山东只能踢出主表或单独报告      |
| **G07 水产品**   | 不进入则价格不确定性对决策无影响（0/7 省） | 「价格不确定性」这条研究问题无法回答 |

而 G07 进入的代价是**上海出局**（该省水产品数据不全），7 省变 6 省。  
这是真正的取舍点，需要作者裁定，但取舍内容比我上一轮说的清楚得多：  
**不是「要不要放宽门限」，而是「要上海还是要价格传导」**。

---

## 二十一、把「要价格传导」落地：`k6_price` 成为一等口径（2026-10-27 第七轮）

作者裁定：**要价格传导**，接受上海出局、7 省变 6 省。本轮把它从「影子目录里的  
诊断口径」提升为代码与合同层面的一等口径，并在此过程中发现三个必须先讲清的结构问题。

### 21.1 落地的五件事

| 位置                                   | 改动                                                                                                    | 验证                                          |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| `src/b2_problem.py`                  | 新增 `SCOPE_AUDITS` 注册表 + `Contract.load_scope()`                                                       | 四口径 K=4/6/3/5 全部装配成功                        |
| `scripts/build_contract_files.py`    | `SCOPES` 新增 `k6_price`；`CONTRACT_EXTRA` 加 `group_audit_trace_c0.95.csv`                               | 契约 **7/7 gate 通过**                          |
| `scripts/build_contract_files.py`    | 新增 `resolve_decision_scope()`，从 `configs/default.yaml` 读 `optimization.decision_scope`，并**交叉校验两张注册表** | 见 21.3                                      |
| `data/processed/model_manifest.json` | 新增 `decision_scope` 段：K、组集合、可用省、跳过省、联合约束核对结果                                                          | `outputs/R002_group_freeze_20261027_150751` |
| `scripts/run_b2.py`                  | 修 provenance bug：`contract_hashes` 原先把 `group_audit.csv` 硬编码                                          | 见 21.2                                      |

`configs/default.yaml` 里 `optimization.decision_scope: k6_price` 是**单一事实来源**，  
manifest 只记录、不定义。若配置里写的口径没在 `SCOPES` / `SCOPE_AUDITS` 中登记，  
或者两处指向不同审计表，构建**直接硬失败**——这类错误会静默跑出不同的 K，  
而日志里只显示一个 K，事后查不出来。

测试从 33 增至 **36**，新增三条都在守这个不变量：  
`test_scope_registries_agree` / `test_configured_decision_scope_is_registered` /  
`test_every_scope_audit_file_exists`。

### 21.2 顺手修掉两个溯源缺口

**(a) `run_b2.py` 记错了审计表的哈希。** 原代码把 `group_audit.csv` 写死在  
`contract_hashes` 里。在 `k6_price` 下模型实际读的是  
`group_audit_trace_c0.95.csv`，于是 run 的 config 会把 K=4 那张表的哈希  
记成 K=6 的证据——事后复核时「哈希对得上」但模型根本不是那个口径。  
现改为按 `SCOPE_AUDITS[args.scope]` 取实际文件，并在 config/metrics 里显式记  
`scope` / `audit_file` / `k_count`。

**(b) `group_audit_trace_c0.95.csv` 此前不是一等产物。** 磁盘上那张表是  
2026-10-23 由旧版脚本旁路生成的 **18 列**格式（缺 `baseline_source`、  
`mapping_*` 三列），**无法用当前代码复现**——R307b 的 B 口径正是用它跑的。

已用 `build_audit(trace_as_valid=True, min_cell_coverage=0.95)` 重算并对比：

| 对比项             | 结果                                                  |
| --------------- | --------------------------------------------------- |
| 入组集合            | **完全一致**：G02 G04 G05 G06 G07 G08                    |
| 11 个 gate 列逐组对比 | **逐格相同**                                            |
| schema          | 18 列 → **23 列**（补齐 `baseline_source` 与 `mapping_*`） |

**结论：R307b 的 B 口径数值不受影响，但此前那张表不能独立复现。** 现已由  
`build_contract_files.py` 正式产出，带 hash 与 manifest 记录。

### 21.3 联合约束在 K=6 下确实生效（不是只写在 CSV 里）

`manifest.decision_bounds.joint_constraint_check` 逐省逐情景实际核对：

| 项                      | 结果                        |
| ---------------------- | ------------------------- |
| 检查省份                   | 安徽、山东、江苏、江西、浙江、福建（6 省）    |
| `G05+G06 ∈ [40,75]` 施加 | **6/6 applied，0 skipped** |
| 上海                     | 在**省份层**出局（缺 G07），不是约束层跳过 |

两者的区别很重要：联合约束「成员不全就整条跳过」是针对**组**的规则，  
上海是整省进不了模型，原因完全不同，不能混在同一句里说。


### 21.4 新发现：K 变大不只是「多几个变量」，还会让被静默丢弃的约束复活

运行：`outputs/DIAG_scope_activation_20261027_151305`（`scripts/diagnose_scope_activation.py`，纯装配、无求解）。

`Instance.active_mask` 会把「在 `box ∩ 联合约束` 内不可达」的营养素排除出机会约束。  
排除是对的（否则 `Σz_s ≤ floor(εS)` 直接不可行），但它有个副作用：  
**被排除的约束在模型里等于不存在**。实测 K=4 有 **10 条**约束被这样丢掉，  
K=6 才真正进入：

| 情景        | 省            | 营养素   | K=4 被排除的原因                | K=6 有效上界  |
| --------- | ------------ | ----- | ------------------------- | --------- |
| CDG       | 安徽           | 碳水化合物 | 最小可达 41.68 > 上界 18.51     | 294.75    |
| CDG       | 江西           | 碳水化合物 | 最小可达 41.68 > 上界 8.51      | 297.70    |
| CDG       | 浙江           | 碳水化合物 | 最小可达 41.68 > 上界 25.63     | 290.97    |
| EAT       | 安徽 / 江西 / 浙江 | 碳水化合物 | 最小可达 26.88 > 上界 8.5–25.6  | 291–298   |
| EAT       | 山东 / 江苏 / 浙江 | 脂肪    | 最大可达 25.29 < 下界 26.3–27.5 | 60.2–61.3 |
| HEAL_base | 福建           | 硫胺素   | 最大可达 0.867 < 下界 0.882     | —         |

机制：**G04 是最大碳水来源**。K=4 把它钉在基线，其碳水进入 offset，  
把碳水有效上界压到 8.5–25.6 g；而决策集内其余组最小也能贡献 41.68 g，  
于是「不可达」→ 整条丢弃。K=6 让 G04 自由后 offset 降下来，  
有效上界升到 ~290–298 g，碳水约束才真正被施加。

**后果：K=4 与 K=6 的可行率不可直接比较。** 四个口径的硬可行省数：

| 情景        | k3_prereg | k4_official | k5_notrace | k6_price |
| --------- | --------- | ----------- | ---------- | -------- |
| HEAL_base | **5/7**   | 1/7         | 0/7        | **0/6**  |
| CDG       | 6/7       | 6/7         | 7/7        | **6/6**  |
| EAT       | 6/7       | 5/7         | 6/7        | 3/6      |
| 被排除约束数    | **14**    | 8           | 7          | 6        |

k3_prereg 在 HEAL_base 上「5/7 硬可行」是四个口径里最好的——恰恰因为它  
**丢掉 14 条约束**。可行率高是因为约束少，不是因为模型好。  
以后引用任何「可行率」必须同时报该口径被排除了几条约束。

### 21.5 价格传导的两种含义必须分开讲

这是本轮最要紧的一条，直接影响「价格不确定性」这条研究问题能不能答。

**(a) 价格水平（省内价 vs 跨省合并价，D1 vs D0）——有传导**

`outputs/R200_203_b2_smoke_20261027_151138`（S=200，仅价格扰动，6 省）：

| 省 | max|Δq| (g/day) |  
|---|--- | --- | --- |  
| 江苏 | **54.00** |  
| 福建 | **36.41** |  
| 江西 | **29.03** |  
| 安徽 / 山东 / 浙江 | 0.00 |

与 R307b 的 B 口径 **3/6 省**、江苏 54.0 完全吻合，属独立复现。

**(b) 价格不确定性（B1 后验散布）——结构性为零**

同一 run 里 **D3 ≡ D1**，逐元素 `max|Δq| ≤ 1e-6`（浙江 1e-6，其余 0）。

原因不是数据、不是 K、也不是 §14 说的脂肪下界，而是**目标函数形式**：  
目标对 `q` 线性，价格只进目标、不进约束，于是

```
min_q  E_s[ c_s · q ]  =  min_q  ( E_s[c_s] ) · q
```

**期望的最优解 = 最优解的期望**，场景平均根本不改变 argmin。

> **更正 §14 / §18 / 追踪表阻塞 3 的表述。**  
> 「价格不确定性对决策零传导」的真正原因是**线性目标 + 不确定性只出现在目标里**，  
> 与可行域被压成顶点、脂肪下界、G11 缺位都无关。那些机制解释的是  
> 「价格**水平**位移为什么不翻转」，不是「不确定性为什么不传导」。

要让不确定性真正进入决策，必须改目标函数（mean-CVaR、min-max regret、  
或把价格放进约束）。这是**建模变更，需作者裁定**，不在本轮范围内。

### 21.6 顺带查清：D3 在 K=6 + 5% 营养系数扰动下几乎不可行

`outputs/R200_203_b2_smoke_20261027_151113`（S=200，价格与营养系数各 5% 扰动）：  
**D3 失败 11/12**，唯一成功的一次 gap 0.453。S=20 时则是 5/12 失败、  
且失败全部集中在 repeat 0——说明这不是「S 太小」的取整效应，而是约束本身不可满足。

根因：确定性最优点落在营养下界上（零余量），系数 5% 扰动后  
**19/20 个场景都违反**（硒 13/20、脂肪 10–12/20、能量 6–8/20）。  
机会约束要求 190/200 场景可行，自然解不出来。

**这暴露了占位场景生成器的设计错误**：`placeholder_scenarios` 对  
`nutrient_coeff` 也施加 5% 对数正态扰动。但食物成分表是固定物理常数，  
把它当 5% 不确定，会让 D3 的可行性完全由这个**不该扰动的量**决定，  
而 B1 后验提供的价格不确定性反而被完全掩盖（见 21.5b）。

正式版应**只扰动价格**（B1 后验），或对营养系数给远小于 5% 的扰动并说明依据。

### 21.7 HEAL_base 在 K=6 下结构性不可行（0/6）

6 省全部冲突，冲突集为 `{脂肪, 碳水化合物, 硫胺素}`。K=4 时 1/7、K=3 时 5/7  
（同样是 21.4 的「约束丢弃多少」效应）。

HEAL_base 的设计是「0 到 2× 基线的可行域包络」。2× 基线不足以同时满足  
脂肪下界（AMDR 20%E）、碳水上下界与硫胺素下界——因为**模型里没有任何油**  
（G11 无营养数据，不在决策集），脂肪只能来自肉蛋，被各组上界封顶。

**含义：HEAL_base 在 K=6 下不能作为主情景报告。** 需作者裁定：  
改上界（如 3× 基线）、或把 HEAL_base 降级为敏感性情景。

### 21.8 仍未解决（全部需作者裁定）

| # | 问题            | 现状                                       | 可选处置              |
| - | ------------- | ---------------------------------------- | ----------------- |
| 1 | 钙结构性不可达       | K=6 下有效下界 703.5 mg，决策集最大可达 436.6 mg，仍被排除 | 纳入 G01 乳制品 / 改软约束 |
| 2 | 不确定性不进决策      | 线性目标下**结构性为零**（21.5b）                    | 改风险厌恶目标（建模变更）     |
| 3 | 上海 G07 缺失     | 源表整块缺失（P0），批发价源无水产品品类，仓库内无法桥接            | 外部补数 / 接受 6 省     |
| 4 | HEAL_base 不可行 | K=6 下 0/6                                | 改上界 / 降级为敏感性      |
| 5 | 场景生成器扰动对象错    | 营养系数被 5% 扰动，主导了 D3 可行性                   | 只扰动价格             |

### 21.9 证据等级

本轮全部结论为 `structural`（21.4，纯装配复算）或 `plumbing_only`  
（21.5–21.7，M2 框架仍是三处占位）。**没有任何一条可以进论文结果表。**  
可进论文的是方法学结论：口径注册表的不变量（21.1）、溯源修复（21.2）、  
以及 21.5 那条「线性目标下不确定性不传导」的解析事实——后者与数据无关，  
是模型性质，可以直接写进方法论章节。

---

## 二十二、HEAL_base 的上界倍数与钙是**耦合**的两个决策（2026-10-27 第八轮）

运行：`outputs/DIAG_heal_bound_scale_20261027_151753`（`scripts/diagnose_heal_bound_scale.py`，纯装配、无求解）。

### 22.1 起因

K=6 决策口径下 HEAL_base **6 省全部硬不可行**（CHANGELOG §21.7）。  
若照此写进论文，三个情景只剩两个。所以要把「不可行」变成一个可裁定的数字：  
**上界放到几倍，这个情景才可用？**

### 22.2 第一个判据失败：结果非单调

首版只读 `Instance.hard_feasible`，得到：

| m（× 基线） | 2.0 | 2.5     | 3.0     | 4.0 | 6.0 |
| ------- | --- | ------- | ------- | --- | --- |
| 模型硬可行   | 0/6 | **4/6** | **3/6** | 3/6 | 6/6 |

**放宽上界反而让可行省数下降**——这在数学上不可能。根因仍是 §21.4 的  
`active_mask`：钙在 m≥3 时从「不可达 → 被排除」变成「可达 → 进入约束」，  
于是 m=3 与 m=4 的「可行 3 省」根本不是同一批省：

| m   | 模型可行的省   | 钙的状态                |
| --- | -------- | ------------------- |
| 3.0 | 安徽、山东、江西 | 江苏/浙江/福建的钙**已进入**约束 |
| 4.0 | 江苏、浙江、福建 | 全部 6 省钙**都进入**约束    |

> **这是同一个机制第三次咬人**（§21.4 的碳水、§21.6 的脂肪、本节的钙）。  
> 只要 `active_mask` 由边界导出，任何「改边界」的敏感性分析都会同时改变  
> 「有几条约束存在」，结论就不可比。**这不是某一个情景的问题，是设计层面的问题。**

### 22.3 改用两个不受此影响的判据

1. **`full_feasible`**：把 11 个营养素**全部强制纳入**（直接调 `minimal_conflict_set`，  
   绕开 `active_mask`）。生效上下界与倍数无关，故该判据对 m **单调**。
2. **`feasible_without_calcium`**：摘掉钙后再判一次，用来区分  
   「钙是唯一阻塞」与「钙只是并列阻塞之一」。

### 22.4 结果

| m（× 基线） | 全约束可行   | 摘掉钙后可行  | 模型可行（含遮蔽） |
| ------- | ------- | ------- | --------- |
| 2.0（现状） | 0/6     | **0/6** | 0/6       |
| 2.5     | 0/6     | 4/6     | 4/6       |
| 3.0     | 0/6     | **6/6** | 3/6       |
| 4.0     | **3/6** | 6/6     | 3/6       |
| 6.0     | **6/6** | 6/6     | 6/6       |

冲突集（全约束口径）：

| m     | 2.0                  | 2.5           | 3.0      | 4.0                           | 6.0      |
| ----- | -------------------- | ------------- | -------- | ----------------------------- | -------- |
| 全 6 省 | 钙                    | 钙             | 钙        | 安徽/山东/江西：碳水+钙；江苏/浙江/福建：**可行** | **全部可行** |
| 摘钙后   | **脂肪+碳水+硫胺素**（全 6 省） | 浙江/福建仍冲突，其余可行 | **全部可行** | —                             | —        |

### 22.5 结论：两个决策不能分开裁定

> ⚠️ **本节结论只在 RNI 口径下成立。** 切到 EAR 后 2× 上界已足够，  
> 见 §22.8 的更正。
>
> **「改上界」单独解不了 HEAL_base，「处理钙」单独也解不了。**
>
> - **2× 基线的问题不是钙**：摘掉钙后 6 省仍然全部冲突，  
>   冲突集是 `{脂肪, 碳水化合物, 硫胺素}`。2× 这个数字本身就是太紧的。
> - **3× 基线之后，钙变成唯一阻塞**：摘掉钙即 6/6，含钙则 0/6。
> - 含钙全约束要 6× 才 6/6，其中江苏/浙江/福建 4× 即可（基线不同）。

所以可裁定的选项其实是三选一，不是两个独立问题：

| 方案           | 上界 | 钙            | 结果                        |
| ------------ | -- | ------------ | ------------------------- |
| A 保持现状       | 2× | 排除           | 0/6，**HEAL_base 不可用**     |
| B 只改上界       | 6× | 排除           | 6/6，但 6× 基线已不是「包络」而是「无约束」 |
| C 上界 + 钙一起处理 | 3× | 纳入 G01 或改软约束 | 6/6，且上界仍属合理包络             |

**推荐 C**，理由：3× 基线作为「可行域包络」尚有解释力（一个人可以吃三倍于现状的量），  
6× 则基本等于没有上界；而钙这条约束在 K=6 下本来就需要单独裁定（§21.8 第 1 条），  
两件事一起做不额外增加决策负担。

但 **C 依赖「G01 乳制品能否进决策集」**——G01 的价格门未通过（`price_gate=False`），  
当前不能作决策变量。所以 C 实际只能走「钙改软约束/惩罚项」这条路，  
需要先定义惩罚系数，这又是一个口径决策。

### 22.6 顺带确认：2× 时的不可行**不是**遮蔽产物

m=2.0 下 `active_mask` 只排除了钙，其余 10 个营养素全部参与，  
冲突集 `{脂肪, 碳水化合物, 硫胺素}` 是真实的约束冲突，不是被丢出来的。  
这一点很重要：§21.7 说「HEAL_base 0/6」时，那个 0 是**真不可行**，  
不像 CDG 的碳水那样属于「约束被静默丢弃」。两者不能混为一谈。

### 22.7 证据等级

`structural`：不含求解，只读约束装配与 `minimal_conflict_set`。  
可逐行复核 `heal_bound_scale.csv`。正式契约未改动（影子目录装配）。

### 22.8 更正（同日，作者追问「需要我定哪些」时复核发现）

§22.4–22.5 的全部结论都是在 **RNI 下界**下得到的。复核 `--bounds-basis ear` 时发现：

| 情景        | RNI 硬可行 | EAR 硬可行 | 平均被排除约束       | 平均活跃营养素       |
| --------- | ------- | ------- | ------------- | ------------- |
| HEAL_base | **0/6** | **6/6** | 1.0 / 1.0     | 10.0 / 10.0   |
| CDG       | 6/6     | 6/6     | 2.0 / 2.0     | 9.0 / 9.0     |
| EAT       | 3/6     | 3/6     | 2.5 / **2.0** | 8.5 / **9.0** |

**HEAL_base 的 6 省在 EAR 下全部硬可行，冲突集清空，2× 上界一个数字都不用改。**  
逐省核对：安徽/山东/江苏/江西/浙江/福建在 RNI 下冲突均为  
`{脂肪, 碳水化合物, 硫胺素}`，在 EAR 下均为 `()`；两口径下被排除的仍只有钙。

> **§22.5 的「2× 这个数字本身就是太紧的」是错的（在 EAR 口径下）。**  
> 2× 上界之所以不够，是因为 RNI 把硫胺素下界定得比可达上限还高；  
> 换成 EAR 后下界整体下移，2× 就够用了。**「上界太紧」与「下界太高」  
> 在这组数据上不可区分，我此前只测了下界固定（RNI）时的上界敏感性，  
> 就把原因归给了上界。这是单因素设计导致的错误归因。**

顺带：EAT 在 EAR 下仍是 3/6，但**冲突构成变了**——  
山东/江苏/浙江由 `{脂肪, 碳水化合物}` 变为 `{碳水化合物, 硫胺素}`，  
即 EAR 把脂肪救出来了，硫胺素却因另一个原因顶上来。EAT 的 3 省不可行  
是独立问题，与 HEAL_base 无关。

**修正后的决策结构**：不再需要「3× 上界 + 钙」这个组合。  
若切 EAR，HEAL_base 直接可用；若坚持 RNI，才需要 §22.5 的方案 C。  
&#x5373;**「RNI vs EAR」是比「上界倍数」更高一层的决策**，先定前者，后者自动消失。

---

## 二十三、第 2 点裁定：钙不是「缺口」，是「可达上限」（2026-10-27 第九轮）

作者要求「第 2 点（钙的处置）仔细分析确定一下」，不接受「建议」。  
本节把钙钉到可裁定的程度。数据来自 `DIAG_calcium_gap_20261027_163714`  
（`scripts/diagnose_calcium_gap.py`，6 省 × 3 情景，确定性硬约束口径）。

### 23.1 先纠正一个提问前提

「钙低于 EAR 是模型缺陷还是膳食结构事实」——这个二选一本身不成立，  
因为**钙在全部 18 个 (情景, 省) 单元格里都已经被判为不可操作**：

| 情景        | 安徽（其余 5 省同构） | 排除原因                    |
| --------- | ------------ | ----------------------- |
| CDG       | 钙被排除         | 最大可达 319.1 < 生效下界 553.5 |
| EAT       | 钙被排除         | 最大可达 385.5 < 生效下界 553.5 |
| HEAL_base | 钙被排除         | 最大可达 436.6 < 生效下界 553.5 |

（「生效下界」= 650 − 非决策组钙贡献偏移；加上偏移后即总钙可达上限。）

也就是说：**钙从来没有进入过约束集，模型的「可行」不以钙达标为前提。**  
这一点此前只在 §21.4 顺带提过，没有单独记账，容易让人误以为  
「钙被满足了」或「钙被优化压低了」。两个都不是。

### 23.2 三组数把「谁造成的」分开

| 量         | 区间（18 格）           | 占 EAR(650 mg) |
| --------- | ------------------ | ------------- |
| 观测基线钙     | 314.78 – 376.58 mg | 48.4% – 57.9% |
| 最优膳食钙     | 296.75 – 366.65 mg | 45.7% – 56.4% |
| 决策域内最大可达钙 | 407.49 – 642.57 mg | 62.7% – 98.9% |

关键比值 `optimal_vs_baseline` = **0.871 – 1.087**：  
优化后的钙与观测基线基本持平（±13% 以内）。  
**缺口不是优化造成的**——模型既没有把钙压低，也没有能力把它抬到 EAR。  
基线本身就只在 EAR 的 48%–58%，这是膳食结构事实。

第二组数同样重要：**即使把目标换成「不顾代价地顶钙」，上限也只有 EAR 的 63%–99%。**  
只有 HEAL_base/浙江（642.57 mg，98.9%）擦到边；CDG 六省上限仅 407–451 mg（63%–69%）。

### 23.3 顶钙的代价

以「顶到可达上限的 95%」为目标（`frac=0.95`）：


| 情景        | 可行性                        | 额外成本（元/人/天） | 目标恶化           |
| --------- | -------------------------- | ----------- | -------------- |
| CDG       | 6/6 可行                     | 0.63 – 2.17 | +7.6% – +14.3% |
| EAT       | **0/6 可行**（最优仅到 75%）       | —           | —              |
| HEAL_base | **0/6 可行**（75% 也只有 3/6 可行） | —           | —              |

边际价格 0.38 – 3.30 元 / 100 mg 钙，且**边际成本递增**  
（浙江 CDG：0.25→0.95 分位，3.30→2.85 元/100 mg 是少数例外，  
其余省份从 0.38 涨到 1.39、1.49 涨到 1.89）。

### 23.4 裁定结论

**钙按「可达上限」报告，不按「缺口」报告，也不作为硬约束。**

理由三条，全部可核查：

1. **硬约束会直接不可行**：18/18 格最大可达 < EAR，把钙写成 `q ≥ EAR` 无解；
2. **不是优化造成的**：`optimal_vs_baseline` 0.871–1.087，优化前后持平；
3. **要补上必须动数据层**：6 组决策集里没有乳制品/豆制品单列，  
   钙密度最高的组（G04 谷物豆类）已在上界，再加量会挤掉其他营养。  
   满足 EAR 需要**扩充决策集**，这是数据工作，不是模型参数工作。

论文写法建议：报告「决策域内钙可达上限为 EAR 的 63%–99%」，  
并明确这是**决策集粒度**的限制，不是优化器的失败。

### 23.5 证据等级

`formal`（结构 + 确定性求解，无随机场景）。18 格全部 `solver_success=True`  
（除 EAT 山东/江苏/浙江 三格本身硬不可行，与钙无关，见 §22.8）。

---

## 二十四、第 3 点裁定：不确定性进不进决策，是**分省**问题（2026-10-27 第九轮）

作者要求「第 3 点（不确定性是否进决策）仔细分析确定一下」。  
结论比预期复杂：**不能用一个「是/否」回答，但可以给出一条可判定的规则。**

### 24.1 第一层：期望目标下零传导是**精确**结论

目标对 `q` 线性、价格只进目标不进约束时：

```
min_q E_s[c_s·q] = min_q (E_s c_s)·q
```

argmin 与场景分布无关。这不是数值巧合，是代数恒等式，实测 `D3 ≡ D1`  
（`max|Δq| ≤ 1e-6`）。**这一层可以直接写进论文，不需要任何后验。**

### 24.2 第二层：CVaR 也动不了 CDG，但不是因为「域被钉死」

先纠正我自己上一轮的一个错误判断。此前我怀疑「可行域是单点」，  
并据此解释 CVaR 无效。**该判断是错的**，原因是宽度脚本的批量循环有 bug  
（`nz` 过滤把组全滤掉了），单实例调试时输出正常。

重写后（`DIAG_feasible_width_20261027_164140`）的真实几何：

| 口径/情景            | 总宽度（6 组合计，g/day） | 被钉死的组     |
| ---------------- | ---------------- | --------- |
| EAR / CDG        | 236.0 – 373.0    | **0 / 6** |
| EAR / EAT（3 省可行） | 719.9 – 722.8    | 0 / 6     |
| EAR / HEAL_base  | 506.2 – 781.2    | 0 / 6     |
| RNI / HEAL_base  | **不可行**          | —         |

**可行域有真实体积，没有任何一组被钉死。**「单点」解释作废。

那 CVaR 为什么还是零位移？`DIAG_cvar_channel_20261027_163855` 的实测是：

| λ | max|Δq| | E_cost | CVaR_0.9 |  
|---|---|---|--- | --- | --- |  
| 0.25 / 0.50 / 0.75 / 1.00 | **0.0000**（6 省全部） | 不变 | 不变 |

### 24.3 第三层：机制是「目标方向旋转量太小」

CVaR 对线性规划的唯一作用是**旋转成本方向**。`DIAG_cvar_angle_spike_20261027_164753`  
把旋转角直接量了出来（`cvar_dir` = 尾部 10% 场景成本向量均值的方向）：

| 扰动结构                        | cv=0.05           | cv=0.20       | cv=0.50       |
| --------------------------- | ----------------- | ------------- | ------------- |
| 逐组独立对数正态（占位）                | 0.44 – 1.12°      | 1.87 – 3.62°  | 4.73 – 9.90°  |
| 组特异性冲击（单品类 ×1.5–3.0，p=0.15） | **8.29 – 16.29°** | 7.28 – 16.21° | 6.78 – 16.29° |

原因很清楚：场景扰动逐组独立时，单个场景的总成本主要由**共同分量**  
（整体价格水平）决定，逐组特异性分量在求和时相互抵消。  
于是「最差 10% 场景」恰好是「整体价格最贵的场景」，其成本方向与均值方向  
几乎一致——CVaR 重加权只是把一个方向微微放大，几乎不旋转。

**把 i.i.d. 波动放大 10 倍（cv 0.05→0.50）只把角度从 1.1° 推到 9.9°，  
换成组特异性冲击才推到 16.3°。瓶颈是扰动的结构，不是幅度。**

### 24.4 第四层：顶点稳定半径——为什么同样是 16°，CDG 不动而 EAT 动

`DIAG_vertex_radius_20261027_164952` 给出可行域的**几何常数**  
（不依赖场景分布）：把成本方向从 `c̄` 转过多少度，最优解首次改变  
（40 个随机方向，`θ ∈ {0.5 … 30}°`）：

| 情景        | 省                 | 半径最小值                  | 中位数                        | 30° 内**已切换**方向数                   |
| --------- | ----------------- | ---------------------- | -------------------------- | --------------------------------- |
| CDG       | 安徽/山东/江苏/江西/浙江/福建 | 4 / 6 / 8 / 4 / 8 / 8° | 10 / 8 / 15 / 9 / 10 / 12° | 15 / 15 / 14 / 20 / 17 / 17（共 40） |
| EAT       | 安徽 / 江西 / 福建      | **0.5 / 1.0 / 0.5°**   | 2 / 2 / 1°                 | 36 / 37 / 18                      |
| HEAL_base | 六省                | 0.5 – 15°              | 2 – 20°                    | 6 – 21                            |

全局：**中位半径 9°，最小 0.5°。**

这就把「为什么 CDG 零位移、EAT 福建位移 339 g」解释清楚了：

- CDG 六省里 20–26 个方向在 30° 内**根本不切换**，会切换的那部分中位半径 8–15°；  
  CVaR 给的方向（+16.3°）恰好落在一个稳定的面上 → 位移 0；
- EAT 福建的顶点在 **0.5°** 就切换（40 个方向中 18 个在 30° 内切换，  
  且最敏感的 0.5° 就翻），任何扰动都会移动它 → 位移 125→339 g。

对照实验（`DIAG_vertex_stability_20261027_164615`）：随机价格方向（σ=0.6，  
逐组独立）下 CDG 有 **5–7 个不同顶点**、位移 43–131 g。  
说明**决策对目标方向本身是敏感的**，只是 CVaR 不往敏感方向转。

### 24.5 被否证的两个替代解释

| 假说                 | 检验              | 结果                                     |
| ------------------ | --------------- | -------------------------------------- |
| 可行域是单点             | 逐组 LP 求宽度       | **否证**：0/6 组被钉死，总宽度 236–373 g          |
| 存在分量最小点（任何正价格下都最优） | 取逐组最小值向量代回约束    | **否证**：`A_ub` 违反 900–1400，不存在          |
| 扰动幅度太小（H2）         | cv 0.05→0.50 扫描 | **部分否证**：CDG 在 cv=0.50、角度 9.9° 下仍 0 位移 |

三个替代解释全部排除后，剩下的只有「旋转方向不敏感 + 顶点稳定半径大」  
这个组合，且两个量都已独立测出。

### 24.6 裁定结论

**「不确定性是否进决策」不能全局回答，必须分省，且判据是两个可测量的量：**

> 当 **尾部方向偏离均值方向的角度 θ_tail > 该省的顶点稳定半径 θ*** 时，  
> 风险偏好才会改变推荐膳食。

- **CDG 6/6 省**：20–26/40 个方向在 30° 内不切换，会切换者中位半径 8–15°，  
  占位场景的 θ_tail ≤16.3° 仍未触发 → 该情景下风险偏好不影响推荐膳食；
- **EAT 安徽/江西/福建**：θ* = 0.5–1.0°，任何扰动都触发  
  → 这三省**必须**交代 λ，否则结论不可复现；
- **HEAL_base**：混合，江苏/山东/浙江 θ* 低（0.5–2°），江西/浙江/福建高（8–15°）。

### 24.7 对论文结构的建议（可裁定项）

**主线用 D1 确定性推荐，把「期望目标下不确定性零传导」作为可证明的结构性论证。**  
理由是这条不依赖任何后验，写法上不需要场景数、不需要 λ、不需要鲁棒性辩护。

**CVaR 放附录做稳健性**，报告 `θ_tail` 与 `θ*` 两个量，并说明哪些省会变。  
这比「加一个 λ 说我们做了鲁棒优化」诚实，也更难被审稿人打。

**不建议把随机优化作为主模型宣称**：其结论完全取决于后验形态  
（i.i.d. 下恒为零，组特异性冲击下 EAT 三省大变），而占位场景  
（`evidence_status=plumbing_only`）无法支撑这个判断。

### 24.8 预注册的判定规则（等 B1 后验到位后执行）

B1 层级随机游走后验到位后，对每个省计算：

1. `θ_tail` = 尾部 10% 场景成本方向与均值方向的夹角；
2. `θ*` = 该省可行域的顶点稳定半径（`scripts/diagnose_vertex_radius.py`，与后验无关，现已可算）；
3. 若 `θ_tail < θ*` → 该省 CVaR **可证明**无效，附录只需一句「已验证不敏感」；
4. 若 `θ_tail ≥ θ*` → 该省必须报告 λ 敏感性曲线。

**这条规则现在就可以写进预注册，因为它只依赖两个已定义、可复现的量。**

### 24.9 证据等级

| 结论             | 等级              | 依据                                           |
| -------------- | --------------- | -------------------------------------------- |
| 期望目标零传导        | `formal`（代数）    | `robust_modopt` 推导 + D3≡D1 实测                |
| 可行域非单点         | `structural`    | `DIAG_feasible_width_20261027_164140`        |
| CVaR 在 CDG 零位移 | `plumbing_only` | `DIAG_cvar_channel_20261027_163855`，占位场景     |
| 旋转角量级          | `plumbing_only` | `DIAG_cvar_angle_spike_20261027_164753`      |
| 顶点稳定半径         | `structural`    | `DIAG_vertex_radius_20261027_164952`，与场景分布无关 |

⚠️ **`plumbing_only` 的三条不能作为 C2 证据**，只能作为「机制存在性与量级」。  
`structural` 的两条与场景分布无关，可以进正文。

---

## 二十五、B1 → B2 的两处接线（2026-10-27 第十轮）

作者要求按第九轮定的思路「依次完成任务」，即把 R200–R203 的两处占位替换掉。  
本节记录实现、两个实现 bug、一个回归验证，以及**接线完成后暴露的新问题**。

### 25.1 接线一：场景源换成 B1 经验残差

新增 `src/b2_scenarios.py` 的 `load_residual_pool` / `posterior_scenarios`。

**为什么用残差重抽样而不是拟合参数分布**：B1 的残差既不零均值也不对称。  
`hierarchical_rw` / `single_cell` 下逐组统计：

| 组        | n   | 残差 sd     | 残差范围          |
| -------- | --- | --------- | ------------- |
| G02 蛋类   | 89  | 0.131     | −0.31 ~ +0.23 |
| G04 谷物豆类 | 38  | 0.124     | −0.19 ~ +0.21 |
| G05 禽肉   | 49  | 0.167     | −0.25 ~ +0.35 |
| G06 红肉   | 198 | 0.224     | −0.48 ~ +0.62 |
| G07 水产品  | 42  | **0.377** | −0.34 ~ +1.01 |
| G08 蔬菜   | 66  | 0.191     | −0.34 ~ +0.44 |

组间离散度差 **3 倍**（G07 vs G04），这正是 CHANGELOG §24.3 说的  
「决定 CVaR 旋转角的是残差的组间结构」。用单一 `cv=0.05` 会把这个结构抹平。

三条实现约束：

1. **残差去均值**，抽样后归一化到列均值 1——保证 `E_s[c_s] = c_point`，  
   否则 D3 与 D1 不再是同一个问题，两者差值里会混进纯平移偏差；
2. **只扰动成本目标**，ghg/land 保持点估计。残差是价格误差，套到全国环境系数上没有语义依据  
   （`placeholder_scenarios` 三个目标都扰动，那是占位实现的历史行为，未改以免破坏可复现性）；
3. **缺组必须报错**，不能静默回退到占位噪声——静默回退会让结果看起来是正式的。

实测抽样结果（200 场景，安徽 CDG）：乘子 sd 0.135 / 0.122 / 0.166 / 0.225 / 0.343 / 0.192，  
范围 0.52–2.11，`E[cost]` 相对点估计偏差 **8.9e-16**（机器精度）。

### 25.2 接线二：重复结构换成 B1 遮蔽协议

新增 `src/b2_protocol.py`，把 B1 的 `(fold, repeat, mask_type)` 单元转成  
「逐省逐组的价格位移」，再由 `Contract.instance(price_override=...)` 装配成决策实例。

**关键实现细节：位移必须按年数稀释。** 合同组价是 2016–2024 的**跨年均值**，  
所以一个被遮蔽的**单年**单元格，其插补误差要被年数除：

```
shift(p,g) = Σ_{被遮蔽单元格} w_c·(pred − truth) / [ n_years(p,g) × price_mean(p,g) ]
```

第一版实现直接把相对误差 `pred/truth − 1` 当作组价变化，**放大了 9 倍**  
（实测 40% 的年误差被记成 40% 的组价变化，实际应为 4.4%）。已修正，  
并加了 `test_single_cell_shift_is_diluted_by_year_average` 钉住。

修正后 100 个单元 × 36 个 (省, 组) 格的位移：

- 每个单元平均只有 **4.06 / 36** 个格非零（与 B1 每单元遮蔽 ~5 格吻合）；
- `|shift|` 均值 **0.298%**，最大 52.3%（G07 只有 3 年观测，年数稀释最弱）。

### 25.3 两个实现 bug（都已修，留痕）

| # | 现象                                 | 原因                                                          | 修正                                        |
| - | ---------------------------------- | ----------------------------------------------------------- | ----------------------------------------- |
| 1 | `nut` 形状是 `[S,1,J,K]` 而非 `[S,J,K]` | `np.repeat(inst.nutrient_coeff[None,...], S, axis=0)` 多套了一层 | 去掉 `[None,...]`，`nutrient_coeff` 本身已含 S 维 |
| 2 | 协议位移放大 9 倍                         | 把年度相对误差直接施加到 9 年均价                                          | 改为绝对误差 / 组价总量（§25.2 公式）                   |

另有**一个测试假设被证伪**：我原以为「整组遮蔽（`province_group`）的位移  
应大于单年遮蔽（`single_cell`）」，实测相反（0.259% vs 0.298%）。  
原因是两种几何的**插补误差本身不同量级**（G07：0.086 vs 0.377），  
跨几何比较不能用来验证稀释。测试已改为「位移 vs 同一批单元格的原始相对误差」，  
直接检验稀释。

### 25.4 回归验证：旧行为逐位可复现

用 `--protocol reseed --scenario-source placeholder --bounds-basis rni --scenarios 200`  
重跑，与接线前的 `R200_203_b2_smoke_20261027_151138` 对比：

| 方法                | 逐省逐组最大差    |
| ----------------- | ---------- |
| D0 / D1 / D2 / D3 | **全部 0.0** |

四个方法逐元素完全相同。接线没有改变任何旧路径。

### 25.5 正式批次：两口径对照

| 口径 | run | 行数 | D0 |Δq| | D1 |Δq| | D3 |Δq| | D3 翻转率 |  
|---|---|---|---|---|--- | --- | --- | --- | --- | --- | --- | --- |  
| **EAR（主口径）** | `R200_203_b2_formal_20261027_170542` | 2400 | **0.000** | **0.000** | **0.000** | 0.000 |  
| RNI（对照） | `R200_203_b2_formal_20261027_171718` | 2400 | 38.771 | 1.049 | 10.906 | 0.028 |

（`|Δq|` = 相对该省真值参考解 `q*` 的最大组级位移，g/day；100 单元 × 6 省 = 600）

### 25.6 接线完成后暴露的问题：EAR 让 M2 失去全部对比度

> ⚠️ **本节的因果归因已被 §25.9 更正。**「EAR 下 D0≡D1≡D3」这个**事实**成立且可复现；  
> 但把它解释成「EAR 让 M2 失去全部对比度」是**过强的**，且把驱动因素认错了——  
> 真正的驱动是 15–65% 的「合并价 vs 省内价」价差，不是 0.3% 的协议位移。  
> 阅读本节请与 §25.9、§26 连读。

这是本节最重要的一条，且**不是接线 bug**。

EAR 口径下，6 个省在 **100 个协议单元**上：

- D0 ≡ D1 ≡ D3，`|Δq|` 精确为 **0.000**，`gap` 精确为 **0.0000**；
- D1 的解在 100 个单元间**逐位不变**（逐组标准差全为 0.0000）；
- 只有 D2（无营养约束）不同：`|Δq|` 128.65、gap −0.80、翻转率 0.194。

RNI 口径下对比度部分恢复：D1 有 **3/6 省**出现两个不同顶点  
（安徽 sd 8.40、山东 19.02、浙江 10.54 g/day），D3 与 D1 分离（`|Δq|` 10.91）。

**这意味着**：EAR 下 R200–R203 无法报告任何「方法差异」，  
只能报告「四个方法给出同一套膳食」。而 R200–R203 的预注册指标  
（feasibility / flips / p95 regret）**在 EAR 下全部退化**——  
flips 恒为 0，regret 恒为 0。

机制与 §24.4 一致：EAR 让更多营养素变为可操作，顶点稳定半径变大；  
而协议位移只有 0.3% 量级，远小于任何翻转阈值。

### 25.7 顺带查清：合同的价格面板**没有用到插补**

`Contract.price_panel()` 用的是 `price_cny_kg`（303/756 非空），  
按 `(省, 组)` 对**可用年份**取均值。`price_cny_kg_full`（473/756）从未被调用。

也就是说：

- 453 个缺失格不是被插补填上，而是**被年份平均直接跳过**；
- G07 只有 **23/63** 格有价（每省约 3 年），合同组价实为 3 年均值；
- B1 的插补结果目前只通过**残差分布**进入 B2，没有通过**点估计**进入。

**这比「真值仍是占位」更值得优先处理**：如果决策本来就不用插补价格，  
那 B1 → B2 的链路在点估计层面是断的，只在不确定性层面接了半条。

### 25.8 证据等级与待裁定

| 结论                        | 等级                                            |
| ------------------------- | --------------------------------------------- |
| 两处接线可运行、旧路径逐位可复现          | `formal`（回归 diff 全 0）                         |
| EAR 下 D0≡D1≡D3、D1 对协议单元不变 | `formal`（2400 行，两口径对照）                        |
| 残差池的组间结构                  | `formal`（直接来自 B1 正式批次）                        |
| 真值仍是冻结点估计                 | **仍是占位**，`evidence_status` 保持 `plumbing_only` |

**待作者裁定（三选一，见 §25.6/§25.7）**：

> ⚠️ **本清单已被 §26.8 修订为四选一，再被 §28.6 拆成 ③-a（否证）/ ③-b（待裁定）。
> 最新、可签字的版本见 `docs/TO_DECIDE.md`。** 下面保留原文仅为留痕。

1. **接受 EAR 的代价**：M2 改写成「决策对价格信息稳健」的零结果报告；
2. **M2 决策层回退 RNI**：与 M1 的评估层解耦，M2 用 RNI 保住对比度；
3. **改合同价格口径**：用年度价或 `price_cny_kg_full`，让插补与价格差异不被平均掉  
   ——这是建模变更，影响面最大。

### 25.9 更正：三处结论需要修正（同日复核发现）

作者追问「多解是不是真解差异」时复核，发现我上一轮的三个判断有问题。**逐条留痕**。

#### 更正一：多解分析被「方法混池」污染

上一轮我报告「安徽两解差 49.00 g、gap 0 与 0.001442；山东差 110.97 g；  
浙江差 74.87 g，说明多解是真解差异不是浮点退化」。这个**结论本身对，  
但证据是脏的**——我是把 D0/D1/D2/D3 四个方法混在同一个「解签名」池里分组的。

按方法拆开后真相是：

| 现象                                               | 上一轮解释   | 实际                                           |
| ------------------------------------------------ | ------- | -------------------------------------------- |
| `gap ≈ −0.80`、`q = [40,200,40,0,40,300]` 的 600 行 | 疑似求解器退化 | **就是 D2**（故意不加营养约束），600 = 6 省 × 100 单元，每省唯一解 |
| `feasible_all = 0/2400`                          | 疑似 bug  | **由构造决定**：钙与硫胺素结构不可达（§23），任何解都不可能全 11 项可行    |
| 「安徽 2 个解」                                        | 求解器多解   | D0 走顶点 B（98/100）、D1 走顶点 A（97/100），**是方法差异**  |

`feasible_active` 在 D0/D1/D3 上均为 **1.0**（600/600），只有 D2 是 0.0——符合设计。

按方法拆开后的唯一解数（RNI 批次）：

| 方法 | 安徽 | 山东 | 江苏 | 江西 | 浙江 | 福建 |
| -- | -- | -- | -- | -- | -- | -- |
| D0 | 2  | 2  | 2  | 2  | 2  | 2  |
| D1 | 2  | 2  | 1  | 1  | 2  | 1  |
| D2 | 1  | 1  | 1  | 1  | 1  | 1  |
| D3 | 2  | 1  | 1  | 2  | 1  | 2  |

**D1 的少数解只占 2–3/100**（安徽 3、山东 3、浙江 2）。这不是「D1 在两个顶点间摇摆」，  
而是「D1 基本钉在顶点 A，偶发 2–3 个单元被推到 B」。上一轮写成  
「D1 有 3/6 省出现两个不同顶点」夸大了摇摆程度。

#### 更正二：「EAR 让 M2 失去全部对比度」过强，且归因错误

D0 与 D1 的**唯一**差别是价格：D0 = 6 个决策省的合并价，D1 = 该省价。  
两者价差实测（`max|base/pooled − 1|`）：

| 省  | 安徽    | 山东    | 江苏    | 江西    | 浙江    | 福建    |
| -- | ----- | ----- | ----- | ----- | ----- | ----- |
| 价差 | 42.3% | 24.6% | 30.1% | 34.2% | 64.5% | 14.5% |

**比协议位移（0.298%）大两个数量级。** 所以

> 「EAR 下 D0 ≡ D1」**不是**因为「0.3% 太小推不动」，  
> 而是因为 **EAR 下顶点稳定到连 65% 的价格差都推不动**。

§25.6 末段写的「协议位移只有 0.3% 量级，远小于任何翻转阈值」把驱动因素认错了。  
正确的表述见 §26.6。

同时，§25.6 写的「EAR 让更多营养素变为可操作，顶点稳定半径变大」也不准确：  
两种口径**只差 7 个营养下界**，而绑定约束集合实际是**换了一组**（§26.5），不是「变多」。

#### 更正三：诊断脚本的 B 度量口径与 D0 不一致（已修）

初版 `diagnose_price_radius.py` 用 `price_panel().mean(axis=0)`——**7 省，含被排除的上海**。  
正式批次的 D0 用 `price_panel().reindex(provinces).mean(axis=0)`——**6 省**。

后果：安徽在 7 省口径下 `t = 4`，6 省口径下 `t = 1`，**差 4 倍**。  
修正后逐省 `t` 与正式批次 D0↔D1 的翻转模式**完全一致**（安徽/山东/浙江 t=1，  
江苏/江西/福建 t=3–8，见 §26.4）。

这个 bug 的方向是「低估对比度」——会让 EAR 看起来比实际更稳。

---

## 二十六、价格扰动半径：EAR 的稳定是「真稳」还是「没踩到阈值」（2026-10-27 第十一轮）

run：`DIAG_price_radius_20261027_174014`（`structural`，纯 LP 扫描，无随机场景）  
脚本：`scripts/diagnose_price_radius.py`

> 批次沿革：`..._173136`（7 省合并价，**作废**）→ `..._173521`（改 6 省，作废，  
> 未含度量 C）→ `..._173709`（三度量齐全）→ `..._174014`（合并价改走  
> `Contract.pooled_price()` 单一入口，三个 CSV 与 `173709` **逐字节一致**）。  
> **引用请用 `174014`。**

### 26.1 要判的问题

§25.6 的零对比度有两种解释，处置完全相反：

- **H1（稳健）**：EAR 的可行域把决策钉得很稳，价格偏几十个点都不动  
  → 零对比度是**结论**，M2 可以写成「决策对价格信息稳健」；
- **H2（伪影）**：只是喂进去的扰动太小 → 零对比度是**设计产物**，必须回退。

### 26.2 三个度量

| 度量           | 定义                                                                 | 读法                       |
| ------------ | ------------------------------------------------------------------ | ------------------------ |
| **A 单组价格半径** | 某组价格乘 `1+δ`，找最小 δ 使最优解改变                                           | 最敏感那一组要偏多少               |
| **B 省际价差放大** | 对数空间外推 `p(t) = p_pooled·(p_prov/p_pooled)^t`，`t=0` 是 D0、`t=1` 是 D1 | `t=1` 动 ⟺ 真实 D0↔D1 对比度成立 |
| **C 绑定约束集合** | 最优解上哪些营养下界顶死（用**决策组贡献** vs **生效界**比较）                              | 解释 A/B 的差异来源             |

度量 C 的口径陷阱：`inst.nutrient_lower/upper` 是**已扣除非决策组偏移**的生效界，  
必须与 `nutrient_coeff @ q` 比较；与含偏移的总量比较会重复扣减，得出假越界。

### 26.3 度量 A：单组价格半径

δ 网格 `{1%, 2%, 5%, 10%, 20%, 30%, 50%, 100%, 200%}`，`|Δq| > 1e-4` 记为改变。

**必须按情景分开报**——「EAR 稳」这个结论在三个情景上强度差很多：

| 情景           | 口径  | 有效格 | 200% 内从不动    | 最小半径   | 中位半径 |
| ------------ | --- | --- | ------------ | ------ | ---- |
| **CDG**（主情景） | EAR | 36  | **28 (78%)** | 20%    | 100% |
| CDG          | RNI | 36  | 14 (39%)     | 10%    | 100% |
| EAT          | EAR | 18  | 5 (28%)      | **5%** | 50%  |
| EAT          | RNI | 18  | 5 (28%)      | **5%** | 50%  |
| HEAL_base    | EAR | 36  | **27 (75%)** | **2%** | 100% |
| HEAL_base    | RNI | 0   | —            | —      | —    |

合计：EAR 60/90 不动、最小 2%、中位 50%；RNI 19/54 不动、最小 5%、中位 100%。

**最小半径那 2% 出现在 `HEAL_base/江苏/G05`；5% 的两格都在 EAT（安徽 G07、福建 G08）。**  
也就是说**小半径集中在 EAT 与 HEAL_base**，与 §24.4「EAT 顶点稳定半径只有 0.5–1.0°」互相印证；  
CDG 的最小半径是 **20%**，是协议位移的 67 倍。

CDG 情景逐省「最敏感那一组」的半径：

| 省   | 安徽      | 山东   | 江苏   | 江西   | 浙江   | 福建     |
| --- | ------- | ---- | ---- | ---- | ---- | ------ |
| EAR | 1.00    | 1.00 | 2.00 | 0.20 | 0.50 | 0.50   |
| RNI | 0.10    | 0.50 | 2.00 | 0.20 | 0.20 | 0.10   |
| 倍数  | **10×** | 2×   | 1×   | 1×   | 2.5× | **5×** |

（RNI/HEAL_base 全部求解失败，0/36 有效——与 §21.7「HEAL_base 在 K=6 下结构性不可行」一致。）

### 26.4 度量 B：省际价差放大（口径已修正为 6 省）

| 省  | 实际价差  | EAR 的 t | RNI 的 t |
| -- | ----- | ------- | ------- |
| 安徽 | 42.3% | 4       | **1**   |
| 山东 | 24.6% | 8       | **1**   |
| 江苏 | 30.1% | 4       | 4       |
| 江西 | 34.2% | 2       | 3       |
| 浙江 | 64.5% | >12（永不） | **1**   |
| 福建 | 14.5% | 4       | 8       |

**读法**：`t=1` 表示「真实价差本身已足够翻转决策」。

- **EAR：0/6 省在真实价差下翻转。** 最接近的是江西（需 2 倍），  
  即价差要从 34% 放大到约 57% 才动；
- **RNI：3/6 省在真实价差下翻转**（安徽/山东/浙江），其余需 3–8 倍。

这与正式批次**逐省一致**：EAR 下 D0≡D1 全部 6 省；RNI 下安徽/山东/浙江的 D0≠D1，  
江苏/江西/福建相同。**两套证据互相验证。**

### 26.5 度量 C：绑定约束换了身份

| 口径  | 安徽       | 山东       | 江苏          | 江西          | 浙江       | 福建          |
| --- | -------- | -------- | ----------- | ----------- | -------- | ----------- |
| EAR | 能量·脂肪    | 能量·脂肪    | 能量·脂肪       | 能量·脂肪       | 能量·脂肪    | 能量·脂肪       |
| RNI | 脂肪·**硒** | 脂肪·**硒** | 能量·脂肪·**硒** | 能量·脂肪·**硒** | 脂肪·**硒** | 能量·脂肪·**硒** |

安徽 EAR 的具体数值（决策组贡献 vs 生效下界）：

| 营养素 | EAR 贡献 / 下界                  | RNI 贡献 / 下界                    |
| --- | ---------------------------- | ------------------------------ |
| 能量  | 6766.626 / 6766.626 ← **绑定** | 6877.286 / 6766.626（余量 +1.64%） |
| 脂肪  | 39.052 / 39.052 ← **绑定**     | 39.052 / 39.052 ← **绑定**       |
| 硒   | 56.775 / 48.549（余量 +16.9%）   | 58.549 / 58.549 ← **绑定**       |

EAR 与 RNI 的实例**逐字段对比**：`objective_coeff`、`nutrient_coeff`、`q_lower`、  
`q_upper`、`objective_weights`、`nutrient_offset`、`baseline`、`nutrient_upper_raw`、  
`active_mask` **全部逐位相同**，只有 `nutrient_lower_raw` 不同  
（钙 650→800、铁 12→15、锌 8.25→10、硒 50→60、核黄素 1.1→1.3、烟酸 11→13.5、硫胺素 1.1→1.3）。

**所以稳定性差异 100% 归因于这 7 个下界。** 机制不是「约束变多」  
（EAR 2 条、RNI 2–3 条），而是**绑定约束换了身份**：  
EAR 下能量顶死（把总进食量钉住），RNI 下硒顶死（钉住的是组成而非总量）。  
这是**观察到的相关性，不是已证明的因果**——要证因果需要单独扫下界，未做。

### 26.6 统一解释：两个「矛盾」其实是同一件事

上一轮遗留的矛盾是：「单组 ±2% 就能移动解」与「100 个协议单元里 D1 逐位不变」并存。

统一后：

1. **协议位移（0.298%）确实远小于任何半径。** 最不利的个案是  
   `HEAL_base/江苏/G05` 的 2%，仍是协议位移的 **6.7 倍**；  
   主情景 CDG 的最小半径是 **20%，即 67 倍**。所以 D1 在协议单元间不动，是**真稳健**，  
   不是没踩到阈值；
2. **D0↔D1 的对比度来自 15–65% 的价差，不是来自协议位移。** EAR 下连这个量级也推不动，  
   RNI 下推得动——这就是两口径差异的**全部来源**；
3. 小半径（2–5%）只出现在 **HEAL_base 的一格与 EAT 的两格**，主情景 CDG 最小 20%。  
   用这些个案代表整体是选择性举例；反过来，也不能把 CDG 的稳健性外推到 EAT。

### 26.7 结论：H1 成立，但只在 EAR 上

| 假设          | 判定          | 依据                                                                       |
| ----------- | ----------- | ------------------------------------------------------------------------ |
| H1（EAR 真稳健） | **成立，但分情景** | CDG 28/36 格 200% 内不动、最小半径 20%（位移的 67 倍）；0/6 省在真实价差下翻转；EAT 最弱（5/18、最小 5%） |
| H2（EAR 是伪影） | **否证**      | 若为伪影，真实价差（15–65%）应能翻转，实际 0/6                                             |
| RNI 有对比度    | **成立**      | 3/6 省在 t=1 翻转；D1 `\|Δq\|` 1.05、D3 10.91                                  |

**但「稳健」不等于「有价值」。** EAR 下 D0≡D1≡D3 意味着  
**价格信息在决策层完全不起作用**，M2 的四个方法退化成同一套膳食。  
这是一个**真实的零结果**，可以报告，但它不是「方法比较」的结论。

### 26.8 对 §25.8 三选一的修订

原三选一（①接受 EAR 代价 ②回退 RNI ③改价格口径）的**依据需要更新**：

- ①「接受 EAR 的代价」现在有了更强的支持：**不是「恰好没踩到阈值」，是真的稳**；
- ②「回退 RNI」的代价也要说清：RNI 让 3/6 省的决策变成**对价差敏感**，  
  而价差（15–65%）来自「合并价 vs 省内价」这个**建模选择**，不是数据噪声；
- ③「改价格口径」的优先级**上升**：如果决策本来就用不到插补价格（§25.7），  
  那 B1→B2 的链路在点估计层面是断的——这比口径之争更根本。

新增第四条候选：

1. **改对比维度**：既然 `flip_rate`（符号翻转，1 g/day 容差）在 RNI 下  
   对 D0 的 49–111 g/day 决策差异只报 **0.0003**（方向没变），应把  
   **`max_abs_dq_ref` 作为主指标**（D0 实测 38.77 g/day），  
   `flip_rate` 降为辅助。这是**指标选择问题，不需要动模型**，成本最低。

### 26.9 证据等级

| 结论            | 等级                                        |
| ------------- | ----------------------------------------- |
| 度量 A/B/C 的数值  | `structural`（纯 LP 扫描，可复现）                 |
| 「EAR 下 D0≡D1」 | `formal`（2400 行正式批次 + 本诊断互相验证）            |
| 「绑定约束换了身份」    | `structural`（观察值，因果未证）                    |
| 「协议位移 0.298%」 | `formal`（来自 B1 遮蔽协议，`protocol_shift.csv`） |

---

## 二十七、执行裁定 4：把「决策位移」提为主指标（2026-10-27 第十二轮）

run：`R200_203_b2_formal_20261027_174710`（EAR）/ `..._174714`（RNI），各 2400 行  
改动：`src/b2_evaluate.py`、`scripts/run_b2.py`、新增 `scripts/summarize_dq.py`

### 27.1 这是预注册偏离，必须声明

R200–R203 预注册的指标是「feasibility, flips, p95 regret」。  
把 `flips` 降为辅助**属于改动预注册指标优先级**，处置：

- `flips` **仍然完整报告**，没有隐藏；
- 新增 `dq_ref_median / p95 / max / change_rate` 为主指标；
- **论文的「预注册偏离」一节必须写明这一条**，理由引用 §26.8 与本节。

### 27.2 为什么必须换

`flip_rate` 只看**方向**（`sign(q−b)` 是否与 `q*` 一致，1 g/day 容差），对**幅度盲**。  
RNI 口径下最刺眼的一行：

| 省 | 方法 | `\|Δq\|` 中位 | 变化率 | **`flip_rate`** |  
|---|---|---|---|--- | --- | --- |  
| 山东 | D0 | **110.97 g/day** | **0.98** | **0.000** |  
| 安徽 | D0 | 49.00 g/day | 0.98 | 0.000 |  
| 浙江 | D0 | 74.88 g/day | 0.99 | 0.000 |  
| 福建 | D3 | 36.41 g/day | 1.00 | 0.000 |

**98% 的协议单元上决策偏了 111 g/day，`flip_rate` 报 0。** 原因：这些位移都没改变  
「该增还是该减」——从 477 g 降到 428 g 与降到 477 g 都是「减少」。  
用 `flip_rate` 当主指标，会把 M2 最重要的对比度完全抹掉。

### 27.3 回归验证：只改报告，没改结果

`b2_results.csv` 新旧批次**逐列逐元素对比，全部差异为 0**（26 列 × 2400 行，两口径）：

| 口径  | 旧 run        | 新 run        | 逐元素差异   |
| --- | ------------ | ------------ | ------- |
| EAR | `..._170542` | `..._174710` | **全 0** |
| RNI | `..._171718` | `..._174714` | **全 0** |

即求解路径、场景、遮蔽协议、参考解 `q*` 全部未动，改动完全在汇总层。

### 27.4 新指标表

**EAR（主口径）**

| 方法 | `\|Δq\|` 中位 | `\|Δq\|` p95 | 变化率 | gap 均值 | gap p95 | 可行(活跃) | 翻转率* |  
|---|---|---|---|---|---|---|--- | --- | --- | --- | --- |  
| D0 | 0.00 | 0.00 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |  
| D1 | 0.00 | 0.00 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |  
| D2 | 129.12 | 156.69 | 1.000 | −0.800 | −0.779 | 0.000 | 0.194 |  
| D3 | 0.00 | 0.00 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |

**RNI（对照）**

| 方法 | `\|Δq\|` 中位 | `\|Δq\|` p95 | 变化率 | gap 均值 | gap p95 | 可行(活跃) | 翻转率* |  
|---|---|---|---|---|---|---|--- | --- | --- | --- | --- |  
| D0 | 0.00 | **110.97** | **0.498** | 0.006 | 0.027 | 1.000 | 0.000 |  
| D1 | 0.00 | 0.00 | 0.013 | 0.000 | 0.000 | 1.000 | 0.000 |  
| D2 | 156.95 | 177.39 | 1.000 | −0.805 | −0.782 | 0.000 | 0.222 |  
| D3 | 0.00 | **36.41** | **0.333** | 0.000 | 0.002 | 1.000 | 0.028 |

### 27.5 新暴露的聚合陷阱：中位数在 `change_rate ≈ 0.5` 时失效

RNI/D0 的 `|Δq|` **中位数是 0**，但**变化率是 0.498、p95 是 110.97**。

原因是结构性的：6 个省里恰好 3 个动、3 个不动，中位数正好落在 0/非 0 的分界上。  
**这不是「一半单元位移为 0」的平稳分布，而是两个众数之间的空档。**

因此报告口径必须写成：

> 「D0 在 **49.8%** 的协议单元上偏离真值参考解，`p95 = 110.97 g/day`」

而**不能**写成「位移中位数 0」——后者会让读者以为 D0 与 D1 没有差别。  
`dq_ref_median` 保留在 `metrics.json` 里，但**不应单独引用**；  
主报告用 `change_rate + p95` 这一对。

### 27.6 分省表：位移集中在 3 个省

`scripts/summarize_dq.py`（新增）按 (省, 方法) 拆开。RNI 口径：

| 省 | D0 `\|Δq\|` 中位 | D0 变化率 | D0 唯一解数 | D1 变化率 | D3 `\|Δq\|` 中位 |  
|---|---|---|---|---|--- | --- | --- | --- | --- |  
| 安徽 | **49.00** | 0.98 | 2 | 0.03 | 0.00 |  
| 山东 | **110.97** | 0.98 | 2 | 0.03 | 0.00 |  
| 浙江 | **74.88** | 0.99 | 2 | 0.02 | 0.00 |  
| 江苏 | 0.00 | 0.02 | 2 | 0.00 | 0.00 |  
| 江西 | 0.00 | 0.01 | 2 | 0.00 | **29.03**（变化率 1.00） |  
| 福建 | 0.00 | 0.01 | 2 | 0.00 | **36.41**（变化率 1.00） |

读法：

- **D0 在 6 个省都出现 2 个解**，但只有安徽/山东/浙江是「多数单元走错顶点」（98–99%）；  
  江苏/江西/福建是「1–2 个单元走错」——同一个二选一，两边的主次正好相反；
- **D1 基本钉在正确顶点**（变化率 ≤ 3%），**D3 在江西/福建系统性偏离**（100%）；
- EAR 口径下 6 省 × 4 方法的唯一解数**全部为 1**，位移全部为 0（D2 除外）。

### 27.7 两个实现 bug（都已修，留痕）

**bug 1：`-0.0` 被当成不同解。** 初版用 `round(6)` 转字符串做解签名，  
`-1e-9` 舍入成 `-0.0`，`str()` 得到 `"-0.0"` ≠ `"0.0"`。加 `+ 0.0` 归一即可。

**bug 2：6 位小数的舍入边界。** 修完 bug 1 后 EAR/安徽/D3 仍报 2 个解。  
实测两个解的差是 **7.3e-9 g/day**（纯浮点噪声），但恰好卡在  
`436.062207 | 436.062208` 的舍入边界上。

**根因是方法选错了**：唯一解判定应该用**容差聚类**，不是字符串相等。  
现改为 `SIG_TOL = 1e-3` g/day 的贪心聚类（`_n_unique`），  
并加测试钉住「7.3e-9 噪声必须合并、49 g/day 真实差必须分开」。

> 教训：任何「把浮点数变成可比较的键」的做法都要先问容差是多少。  
> 字符串舍入只是把容差问题藏起来，没解决它。

### 27.8 结论：M2 现在有一个可报告的主结果

| 口径         | 可报告的主结果                                                                                      |
| ---------- | -------------------------------------------------------------------------------------------- |
| **EAR（主）** | D0 ≡ D1 ≡ D3，变化率 **0.000**，`p95 = 0.00`。价格信息对决策**完全无影响**——真实零结果                              |
| RNI（对照）    | D0 变化率 **0.498**、`p95 = 110.97`；D1 变化率 **0.013**、`p95 = 0.00`；D3 变化率 **0.333**、`p95 = 36.41` |

EAR 下这个零结果是**干净的**（不是指标退化造成的假象——换成对幅度敏感的指标后仍然是 0），  
可以直接写成「决策对价格信息稳健」的结论；但必须同时说明  
**这是 EAR 口径的性质，RNI 下同一批数据有 49.8% 的单元会变**（§26）。

### 27.9 证据等级

| 结论                            | 等级                                            |
| ----------------------------- | --------------------------------------------- |
| 只改报告层、结果逐元素不变                 | `formal`（26 列 × 2400 行 × 2 口径，diff 全 0）       |
| EAR 下变化率 0.000                | `formal`（2400 行）                              |
| RNI 下 D0 变化率 0.498 / D1 0.013 | `formal`（2400 行）                              |
| 位移集中在安徽/山东/浙江                 | `formal`（分省表，可复现）                             |
| 真值仍是冻结点估计                     | **仍是占位**，`evidence_status` 保持 `plumbing_only` |

---

## 二十八、价格面板口径诊断：换价格构造能不能救回 EAR 的对比度（2026-10-27 第十三轮）

run：`DIAG_price_panel_20261027_180334`（`structural`）  
脚本：`scripts/diagnose_price_panel.py`（新增）

### 28.1 先更正一处措辞错误

§25.7 与裁定书里，我把「改用 `price_cny_kg_full`」写成了**让 B1 插补进入决策**的选项。  
**这是错的。** 查 `scripts/build_group_prices.py` 源码：

- `price_cny_kg`：观测口径。部分结构时**只用观测到的品类**、权重归一化  
  （如只观测到猪肉，则 `pork=1.000`）；
- `price_cny_kg_full`：**观测 + 批发价桥接**（`price_bridge_wholesale.csv`），  
  按完整结构权重加权。源码注释写明：
  > `full: 观测 + 桥接的混合面板（敏感性口径，不进入主口径）`  
  > `price_cny_kg_full：观测 + 桥接混合的完整版本，仅供 B4 敏感性对照。`

所以它**是桥接，不是 MICE 插补**。换它不会把 B1 的点估计接进 B2。  
B1 → B2 在点估计层面**仍然是断的**（§25.7 的结论不变），  
但**修法不是换这一列**，而是用根目录的 MICE 品类级插补结果重新聚合组价  
（`华东华中7省食品零售价_商务预报_分省批发价_mice插补.xlsx`，567 行省×品类×年）。  
那是建模变更，未做。

### 28.2 顺带查出一个真实的数据缺陷：G06 组价被系统性低估

`structure_weighted_partial` 的行里，只观测到猪肉时权重被归一成 `pork=1.000`，  
牛肉（0.136）与羊肉（0.076）被**直接丢掉**。而这两类更贵，所以组价偏低。

| 指标         | 值                  |
| ---------- | ------------------ |
| 部分结构行数     | 24                 |
| 组价低估**中位** | **21.7%**          |
| 组价低估**最大** | **36.6%**（江苏 2023） |

典型：上海 2018 G06，观测 30.00 元/kg，桥接补全后 38.79 元/kg（低估 29.3%）。  
福建 3 行低估为 0——因为它连桥接值都没有，两边同样缺。

**这是独立于「对比度」问题的数据缺陷**：G06 是决策组，成本目标因此系统性偏低。  
若要修，应改为「缺失品类用桥接补全后再按完整结构加权」，  
即把 `price_cny_kg_full` 的**聚合规则**用于主口径，而不是把整列换掉。

### 28.3 换面板后组价变了多少

| 省  | G02    | G04    | G05   | G06   | G07  | G08        |
| -- | ------ | ------ | ----- | ----- | ---- | ---------- |
| 安徽 | −7.4%  | −0.3%  | −3.5% | −6.7% | 0.0% | +10.0%     |
| 山东 | −1.4%  | +3.3%  | +4.0% | +9.7% | 0.0% | +0.6%      |
| 江苏 | −2.2%  | −8.8%  | +0.3% | +9.3% | 0.0% | **−21.6%** |
| 江西 | −0.3%  | +3.0%  | −4.3% | +2.0% | 0.0% | −2.2%      |
| 浙江 | −10.1% | −14.4% | 0.0%  | +5.0% | 0.0% | −10.3%     |
| 福建 | +0.3%  | 0.0%   | 0.0%  | −3.3% | 0.0% | −4.1%      |

`|差异|` 中位 **2.6%**、最大 **21.6%**；full 面板无缺失格（36/36）。

两列在哪些行上会不同，取决于桥接**填的是「整年无观测」还是「年内缺品类」**：

| 组       | 桥接品类合计 | 两列不等的行      |
| ------- | ------ | ----------- |
| G02     | 21     | 0 / 42      |
| G04     | 32     | 0 / 25      |
| G05     | 33     | 0 / 36      |
| **G06** | 75     | **21 / 51** |
| G07     | **0**  | 0 / 23      |
| G08     | 28     | 0 / 35      |

G02/G04/G05/G08 的桥接只补「整年零观测」的行——那些行 `price_cny_kg` 本来就是 NaN，  
所以**两列同时有值的行完全一致**，差异只体现为 full 的**覆盖率更高**。  
只有 G06 是「年内缺品类」（牛肉/羊肉缺失、猪肉有），才会在同一年内改变加权结果。  
G07 两列恒等是因为它**一个桥接值都没有**（福建整组缺、其他省观测稀疏）。

### 28.4 换面板后决策变不变

| 口径      | 情景  | 安徽          | 山东  | 江苏  | 江西  | 浙江  | 福建  |
| ------- | --- | ----------- | --- | --- | --- | --- | --- |
| **EAR** | CDG | 0.0000      | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| **EAR** | EAT | 0.0000      | —   | —   | 0.0 | —   | 0.0 |
| RNI     | CDG | **48.9961** | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| RNI     | EAT | 0.0000      | —   | —   | 0.0 | —   | 0.0 |

（`dq = max|Δq|`，g/day；「—」为该省在该情景下无解）

**目标值确实变了**（EAR/CDG 相对变化 −5.95% 到 +2.24%），  
但 **EAR 下 6 个省的决策一个都没变**（最大 5.1e-13，纯浮点噪声）。

RNI 下只有安徽翻转（49.0 g/day）——与 §26.4「安徽在 RNI 下 t=1 就翻」一致。

### 28.5 结论：EAR 的零结果经得起三种独立的价格构造

到目前为止，EAR 下「决策不变」已经在**三种量级递增的价格扰动**下验证过：

| 扰动来源             | 量级               | EAR 下决策变化 |
| ---------------- | ---------------- | --------- |
| 遮蔽协议位移（§25）      | 0.298%           | 0         |
| 合并价 vs 省内价（§26）  | 15–65%           | 0/6 省     |
| 观测口径 vs 桥接口径（本节） | 中位 2.6%、最大 21.6% | **0/6 省** |

三种扰动的**构造方式完全不同**（插补误差 / 跨省平均 / 桥接补全），  
结论一致。所以 EAR 的零结果**不是某一种价格构造的巧合**。

### 28.6 对裁定清单的影响

**选项 ③「改合同价格口径」作为「救回对比度」的手段，被否证。**

它的原设想是「让插补与价格差异不被 9 年平均掉，从而恢复对比度」。  
但本节显示：把组价改动到 21.6% 这个量级，EAR 下的决策**一步都没动**。  
**换价格口径不会给 EAR 带来对比度**——要对比度只能改下界口径（选项 ②）。

但选项 ③ 作为**数据质量修复**仍然成立，且现在有了具体目标：  
G06 的 24 行部分结构组价低估中位 21.7%，这是成本目标里的系统性偏差，  
与对比度无关，**应该独立修**。

因此裁定清单应拆成两条：

| 编号  | 内容                     | 状态                 |
| --- | ---------------------- | ------------------ |
| ③-a | 改价格口径**以恢复对比度**        | **否证**（本节）         |
| ③-b | 修 G06 部分结构聚合的 21.7% 低估 | **待裁定**（数据质量，独立问题） |

### 28.7 证据等级

| 结论                               | 等级                                    |
| -------------------------------- | ------------------------------------- |
| `price_cny_kg_full` 是桥接口径、非 MICE | `formal`（源码注释 + 列构造可查）                |
| G06 部分结构低估中位 21.7%               | `formal`（24 行逐行可查）                    |
| 换面板后 EAR 下 dq 全 0                | `structural`（18 个 (口径, 情景, 省) 格，纯 LP） |
| RNI 下安徽翻转 49.0                   | `structural`（同上，与 §26.4 互验）           |

---

## 二十九、执行 §24.8 预注册判定：θ_tail vs θ*，以及它没预料到的结果（2026-10-27 第十四轮）

run：`DIAG_tail_angle_20261027_192248`（`structural`）/ `DIAG_lambda_curve_20261027_191751`
（`structural`）/ `DIAG_lambda_curve_fine_20261027_191956`（`structural`）
脚本：`scripts/diagnose_tail_angle.py`、`scripts/diagnose_lambda_curve.py`（均新增）

> **三个早期批次不再引用**：`DIAG_tail_angle_..._190238`（`evidence_status` 误标为
> `formal`，与其它 `DIAG_*` 的 `structural` 不一致）、
> `DIAG_lambda_curve_..._190959` 与 `_fine_..._191241`（汇总表把跨 seed 抽样差异
> 算进了 λ 效应，见 29.6）。数值结论不变，只是标签与聚合层级错，已重跑。

### 29.1 规则执行结果

§24.8 预注册的判定规则（B1 后验到位前被阻塞，现已执行）：
`θ_tail` = 尾部 10% 场景成本方向与均值方向的夹角；`θ*` = 顶点稳定半径
（`DIAG_vertex_radius_20261027_164952`，与后验无关）。200 场景、20 个种子。

| 情景 | 省 | θ* | θ_tail 中位 | 5–95% | θ_tail/θ* | 判定翻转率 | 判定 |
|---|---|---|---|---|---|---|---|
| CDG | 江苏 | 8.0° | 4.11° | 3.07–4.91 | 0.51 | **0.00** | **可证明无效** |
| CDG | 福建 | 8.0° | 6.99° | 4.86–9.93 | 0.87 | 0.25 | 无效（边界不稳） |
| CDG | 浙江 | 8.0° | 9.30° | 8.03–12.18 | 1.16 | 0.95 | 须报 λ 曲线（边界） |
| CDG | 安徽 | 5.0° | 6.61° | 5.16–7.90 | 1.32 | 0.95 | 须报 λ 曲线（边界） |
| CDG | 山东 | 6.0° | 8.45° | 6.64–11.45 | 1.41 | 1.00 | 须报 λ 曲线 |
| CDG | 江西 | 4.0° | 6.74° | 4.83–7.57 | 1.69 | 1.00 | 须报 λ 曲线 |
| EAT | 江西 | 1.0° | 3.38° | 2.33–4.85 | 3.38 | 1.00 | 须报 λ 曲线 |
| EAT | 安徽 | 0.5° | 2.42° | 1.52–3.90 | 4.84 | 1.00 | 须报 λ 曲线 |
| EAT | 福建 | 0.5° | 3.42° | 2.24–4.87 | 6.84 | 1.00 | 须报 λ 曲线 |

汇总：**1 格可证明无效 / 3 格边界不稳 / 5 格须报 λ 曲线**（共 9 格）。
EAT 只有 3 省可解——山东/江苏/浙江在 EAT 下结构性不可行，
**20 个种子全部求解失败（240 行中 60 行 `solver_failed`）**，不计入 `n_cells`。
这与 §21.7、§26.3 的结论一致，不是新问题。

**规则要求「须报 λ 曲线」的 5 格，必须真把曲线算出来才算执行完。** 见 29.2。

### 29.2 关键发现：角度判据是**充分非必要**条件，CDG 被过度标记

`θ*` 的定义是「扰动方向落在 θ* 以内**则**顶点不变」——这是稳定性的**充分**条件。
反过来说，`θ_tail > θ*` 只意味着「不能保证顶点不变」，**不意味着顶点一定会变**。
若扰动方向恰好没有越过任何约束面，顶点照样不动。

所以 `θ_tail ≥ θ*` 的正确读法是「不能证明无效」，而不是「有效」。
§24.8 的规则本身没错（它只要求「报告曲线」，没有断言「CVaR 有效」），
但**如果不真算曲线、只按判定写正文，就会在 CDG 上报出一个不存在的效应**。

### 29.3 λ 曲线：CDG 完全平坦，EAT 是阶跃

`scripts/diagnose_lambda_curve.py`：λ ∈ {0, .25, .5, .75, 1}，200 场景、3 seed，
目标 = `均值成本 + λ·CVaR_0.9`，`Δq` 相对同 seed 的 λ=0，容差 **1e-6 g/day**。

| 情景 | 省 | λ∈[0,1] 的 `max\|Δq\|` | 均值成本变动 | CVaR 变动 | 决策是否动 |
|---|---|---|---|---|---|---|
| CDG | 安徽 | **0.0000** | 0.0000% | 0.0000% | 否 |
| CDG | 山东 | **0.0000** | 0.0000% | 0.0000% | 否 |
| CDG | 江苏 | **0.0000** | 0.0000% | 0.0000% | 否 |
| CDG | 江西 | **0.0000** | 0.0000% | 0.0000% | 否 |
| CDG | 浙江 | **0.0000** | 0.0000% | 0.0000% | 否 |
| CDG | 福建 | **0.0000** | 0.0000% | 0.0000% | 否 |
| EAT | 江西 | **252.00** | 10.26% | 13.34% | **是** |
| EAT | 安徽 | **213.87** | 6.66% | 8.86% | **是** |
| EAT | 福建 | **127.71** | 1.96% | 2.89% | **是** |

（CDG 实测最大 1.0e-9 g/day，纯浮点噪声。）

**CDG 六省在 λ 从 0 拉到 1 的整个区间上，解逐位相同、均值成本相同、CVaR 也相同。**
所以 CDG 不需要 CVaR——这不是「不能证明无效」，是**直接测出来无效**。
§24.8 的保守判定在 CDG 上被实测推翻，**5 格「须报曲线」的格子全部落在平坦区**。

EAT 则相反：λ 一旦越过阈值，决策跳 **128–252 g/day**。CVaR 在 EAT 是**一阶驱动**。

### 29.4 EAT 的 λ 曲线是**阶跃**，且阶跃点跨种子不稳定

细网格（λ 步长 0.05–0.1，3 seed）显示曲线不是平滑下降，而是**分段常数**——
顶点解在 λ 越过临界值前完全不变，越过瞬间换顶点。EAT/江西（seed 20261027）：

| λ | `max\|Δq\|` | 均值成本 | CVaR |
|---|---|---|---|
| 0.00–0.50 | 0.0000 | 9.0631 | 10.9089 |
| 0.60 | 153.27 | 8.5426 | 10.0934 |
| 0.65–0.70 | 208.16 | 8.3561 | 9.8142 |
| 0.75–0.90 | 227.68 | 8.2898 | 9.7185 |
| 1.00 | 248.23 | 8.2200 | 9.6249 |

**阶梯结构本身是顶点解的必然结果**（目标函数在 λ 上是线性的，最优顶点只在
面对偶价格跨越时才切换），不是数值伪影。但它有个直接后果：

| 省 | 3 个种子各自的跳变 λ | 区间 |
|---|---|---|
| EAT/江西 | 0.60 / 0.40 / 0.50 | **[0.40, 0.60]** |
| EAT/安徽 | 0.70 / 0.60 / 0.75 | **[0.60, 0.75]** |
| EAT/福建 | 0.90 / 0.75 / 0.80 | **[0.75, 0.90]** |

跳变点**随场景样本变化**（因为它取决于抽到的那 20 个尾部场景）。
所以 **EAT 不存在一个「自然的」λ**：λ 选 0.5 还是 0.75，可能就是一个省换不换顶点。

### 29.5 结论

| 情景 | CVaR 的地位 | 处置 |
|---|---|---|
| **CDG（主情景）** | **实测无效**（λ∈[0,1] 全平，Δq = 1e-9） | 正文用 λ=0 的纯期望结果，**不需要 λ 曲线**；附录一句「λ 从 0 扫到 1 决策逐位不变」 |
| **EAT** | **一阶有效**，且 λ 无自然取值 | 必须报阶跃曲线 + 跳变 λ 区间；**不能只报 λ=1 的端点** |

对正式结果的含义：所有 `R200_203` 批次用的是默认 `risk_weight=0.0`（纯期望）。
**CDG 主结果不受影响**（CVaR 本来就动不了它）；**EAT 的结论依赖 λ 选择**，
若 EAT 要进正文，必须同时给 λ 曲线，否则单点结果会被质疑。

### 29.6 我自己的一个聚合错误（已修，留痕）

初版 `lambda_curve_summary.csv` 里 CDG 的「CVaR 变动」报 **1.25–1.54%**，
但 Δq 明明是 0。原因：`mean_cost_range_pct` / `cvar_range_pct` 是在
**跨 3 个种子**的合并表上取 `max/min`，把**种子间抽样差异**算进了「λ 效应」。

正确做法：**在同一 seed 内扫 λ** 取变动，再跨 seed 取中位。
修正后 CDG 三项变动全部为 **0.0000%**。

> 与 §27.7 同一个教训的第二次出现：**比较之前先确定「被比较的两个东西」是什么。**
> 那次是浮点容差，这次是聚合层级。

### 29.7 证据等级

| 结论 | 等级 |
|---|---|
| θ_tail / θ* 逐省数值与判定 | `structural`（200 场景 × 20 seed × 9 格；是诊断，不是预注册重复协议） |
| CDG 的 λ 曲线全平（Δq=1e-9） | `structural`（3 seed，但 Δq 与 0 差 6 个数量级，结论不依赖种子） |
| EAT 的 λ 跳变 128–252 g/day | `structural`（3 seed，方向一致） |
| 跳变 λ 跨种子不稳定 | `structural`（3 seed，区间宽 0.15–0.20） |
| θ* 是充分非必要 | `formal`（定义层面可证，且被 29.3 实测印证） |

---

## 三十、价格面板审计：G06 不是孤立事件，但真正的坑在 G3 gate 本身（2026-10-27 第十五轮）

run：`DIAG_price_coverage_20261027_193323`（`structural`，纯数据审计无求解）
脚本：`scripts/diagnose_price_coverage.py`（新增）

### 30.1 起由

§28.2 查出 G06 的 24 行部分结构组价低估中位 21.7%，但那是**偶然撞见的**。
「部分结构时权重归一化」是**一类**缺陷，不是一处。若范围不明，「修 G06」这个
决定本身可能就是错的（也许要修 5 个组）。所以先做范围确认。

### 30.2 范围确认：归一化缺陷**只在 G06**

| 组 | 品类数 | 是否有权重归一化风险 |
|---|---|---|
| G02 蛋 / G04 谷物豆类 / G05 禽肉 / G07 水产 / G08 蔬菜 | **1** | 否——单品类，权重恒为 1 |
| G06 红肉 | **3**（beef/pork/lamb） | **是** |

G06 的 51 个 observed 行里：

| aggregation | 行数 | 保留权重和 | **丢掉的质量** |
|---|---|---|---|
| `structure_weighted_complete`(beef=.136/pork=.788/lamb=.076) | 27 | 1.000 | 0 |
| `structure_weighted_partial`(pork=1.000) | **23** | 0.788 | **21.2%** |
| `structure_weighted_partial`(beef=.147/pork=.853) | 1 | 0.924 | 7.6% |

即 **24 行受影响，全部在 G06**。修的范围比预想的小，也确认了 §28.2 的 21.7%
低估不是抽样巧合，而是 21.2% 的权重质量损失直接造成的。

### 30.3 G3 gate 的两条盲区：一条是新发现，一条是旧账

先分清哪些是新发现、哪些是早已记录的——否则这节就是在重复邀功。

| 事项 | 是否新发现 |
|---|---|
| G3 的 `collapsed = 45.1%` 由 `pork=1.000` 的行构成 | **旧账**：本文档 §五「未解决的问题 #1」已写明 |
| `thin` 是**组级**、不是**单元级** | **新发现** |
| 36 个单元只有 2 个是 9 年全观测 | **新发现** |
| 权重质量损失精确到 21.2% / 7.6% | **新发现**（§28.2 只给了价格低估幅度） |
| 一致性筛查的 4 个可疑单元 | **新发现** |

`scripts/check_contract_gates.py` 的 G3 报 **PASS**。查它的判定逻辑后，发现两处
它**测不到**的东西。

#### 盲区 A：`thin` 是**组级**、不是**单元级**

```python
per_group = sub[sub["observed"]].groupby("group_id").agg(
    n_obs=("price_cny_kg", "size"), n_region=("province", "nunique"))
```

`n_obs` 按 `group_id` 汇总**所有省所有年份**。一个组总观测数够了就过——
即使某个 (省, 组) 单元只有 1 年观测。而合同 `Contract.price_panel()` 是
`groupby(["province","group_id"])["price_cny_kg"].mean()`，**没有最小年数检查**：
只有 1 年观测的单元，那 1 年就是它的 9 年均价，静默通过。

36 个 (省, 组) 单元的实测覆盖（有价格的年份数 / 9）：

| 省 | G02 | G04 | G05 | G06 | G07 | G08 |
|---|---|---|---|---|---|---|
| 安徽 | 6 | 4 | 5 | 5 | 3 | 5 |
| 山东 | 8 | 2 | **1** | 8 | **1** | 7 |
| 江苏 | 8 | 4 | 6 | **9** | 6 | 4 |
| 江西 | 8 | 8 | 8 | **9** | 8 | 7 |
| 浙江 | 2 | 3 | **9**\* | 5 | **1** | 2 |
| 福建 | 7 | 3 | 6 | 8 | 4 | 7 |

\* 浙江/G05 的 9 年是**全部桥接**（`n_observed_categories = 0`，9 年零观测）。

| 指标 | 值 |
|---|---|
| 单元总数 | 36 |
| 9 年全观测 | **2**（江苏/G06、江西/G06） |
| 全部桥接（零观测） | **1**（浙江/G05） |
| 只有 1 年 | **3**（山东/G05、山东/G07、浙江/G07） |
| ≤2 年 | **6（17%）** |
| ≤4 年 | **13（36%）** |
| 中位年数 | **5** |

**即 36 个单元里只有 2 个真正是「9 年均价」，其余 34 个都是「若干年均价」。**

#### 盲区 B：`collapsed` 指标**完全由这个缺陷构成**（旧账，本节只是把它拆开）

```python
collapsed = (lowest["price_cny_kg"].round(6) == lowest["price_min"].round(6)).mean()
ok = ... and collapsed < 0.5
```

这个指标的本意是「主口径不得退化为取最低价」。实测：

| 口径 | `collapsed` | 构成 |
|---|---|---|
| 全量（G3 实际用的） | **0.451** | 23 行「等于最低价」，**23/23 全部来自 `pork=1.000`** |
| 排除 `structure_weighted_partial` 后 | **0.000** | 27 行完整结构，无一等于最低价 |

**这不是新发现。** 本文档 §五「未解决的问题 #1」原文就写着：

> **G3 断言余量只剩 4.9 个百分点**：G06 的 51 个省-年观测中 23 行只有猪肉单品类，
> 归一后组价仍等于猪肉价，实测比例 45.1%（阈值 <50%）
> → 若面板覆盖恶化到 50% 以上，G06 组价实质退化为猪肉价，主结论不成立。

所以「45.1% 就是缺陷本身」这件事，第一轮就已经记在未解决清单里。
本节**新增的只有两件事**：

1. **构成拆解**：23/23 全部来自 `pork=1.000`，排除后 `collapsed = 0.000`——
   即这个指标在完整结构行上是**完全干净**的，它的全部数值都由缺陷贡献；
2. **它离阈值只差 4.9 个百分点**，而 `pork=1.000` 恰好占 23/51 = 45.1%。
   这不是巧合：若 G06 再多一年「只观测到猪肉」，gate 就直接 FAIL。

**要更正的是我自己的表述**：§30 初稿把这条写成「顺带查出两个更大的问题」，
把旧账当成了新发现。实际是**旧账 + 新的定量拆解**。

（TRACKER 里那句「等于最低价比例 45.1%，阈值 50% 已贴近」当时被当作
「贴近但可接受」；现在可以明确：**它就是缺陷本身，不是余量问题**。）

### 30.4 影响范围：不动决策，动成本与「观测价」这个说法

**不影响决策。** §28.4 已验证：组价变动到 21.6% 量级，EAR 下 6 省决策一步都没动。
§29 又验证风险偏好 λ 也推不动。所以这批数据问题**不会改变任何 M2 结论**。

**影响两件事**：

1. **成本目标的绝对水平**。G06 的 24 行低估 21.2% 权重质量，直接进成本；
2. **「观测价」这个措辞**。目前 34/36 个单元的价格是「若干年观测的均值」，
   其中 3 个只有 1 年、1 个零观测全靠桥接。论文若写「用省内观测均价」，
   在 浙江/G05 这一格上是不成立的。

### 30.5 处置建议

| 事项 | 建议 | 是否需要作者裁定 |
|---|---|---|
| 修 G06 的 24 行 | 缺失品类先桥接补全，再按完整结构加权 | **是**（决定 2，范围已确认很小） |
| G3 的 `thin` 改为单元级 | 加「每个 (省,组) 至少 N 年观测」的门槛 | 否，属 gate 修订，可直接做 |
| G3 的 `collapsed` 排除部分结构 | 只在完整结构行上算该指标 | 否，同上 |
| 论文数据节披露覆盖率 | 给出 §30.3 的表 | 否，属写作要求 |

后三条我可以直接执行，但会改动 gate 的通过状态（`thin` 改单元级后 G3 可能 FAIL），
**所以先不动，等作者确认是否接受「G3 从 PASS 变 FAIL」**——这会牵动
`EXPERIMENT_TRACKER.md` 里那张「七条 gate 全 PASS」的表。

### 30.6 证据等级

| 结论 | 等级 |
|---|---|
| 归一化缺陷只在 G06（24 行） | `structural`（组品类数可查，单品类组权重恒 1） |
| 36 单元只有 2 个 9 年全观测 | `structural`（逐单元计数，可复现） |
| `collapsed` 的 23 行全部来自 `pork=1.000` | `structural`（逐行可查） |
| 排除部分结构后 `collapsed = 0.000` | `structural`（同上） |
| 一致性筛查的 4 个可疑单元 | `structural`（残差可复现；**是筛查提示，不是错误判定**） |
| 不影响决策 | `formal`（引 §28.4 与 §29.3 的正式/结构性结果） |

### 30.7 顺带做的一致性筛查：4 个单元偏离「本省自身价格水平」>30 个百分点

既然把面板逐格拆开了，就顺手做一个筛查：每个单元的组价相对**组内 6 省中位**偏离多少，
再减去**该省在其它 5 个组的偏离中位**（即该省自身的价格水平）。
残差大的单元，价格与「这个省一般多贵」不一致，值得回源核对。

**这不是错误判定。** 跨省食品价格差异本身是真实的（浙江整体偏贵、山东水产偏贵都可能为真），
这里只筛出「值得查」的格子，不下结论。

| 组 | 省 | 相对组内中位 | 该省自身水平 | **残差** | 有价年数 |
|---|---|---|---|---|---|
| G07 水产品 | 浙江 | +79.4% | +19.2% | **+60.1 pp** | **1** |
| G07 水产品 | 山东 | +35.8% | −12.0% | **+47.9 pp** | **1** |
| G05 禽肉 | 江西 | +43.5% | −4.2% | **+47.7 pp** | 8 |
| G08 蔬菜 | 江苏 | +29.9% | −3.7% | **+33.6 pp** | 4 |

读法：

* **前两个是「薄样本噪声」的典型**——G07 在这两个省都只有 **1 年观测**，
  那一年的价格直接当 9 年均价用，偏离本省水平近 50 个百分点不奇怪。
  这与 §30.3 的覆盖率问题同源，**不是两个独立缺陷**；
* **后两个不是薄样本**（江西 G05 有 8 年、江苏 G08 有 4 年），
  是「观测到但与本省其它组不一致」。可能是真实的区域品种/品质差异，
  也可能是品类定义或单位问题。**需要回源核对，我不下判断。**
* 36 个单元里 32 个残差在 ±30 pp 内，面板整体是自洽的。

顺带验了一件事：**浙江/G05 那个全桥接价格（+24.3%）并不异常**——
浙江在其它 5 个组的偏离中位是 +19.2%，两者差 5.1 pp。
所以这一格用批发价桥接替代，量级上是站得住的，问题只在「不能称之为观测价」。

### 30.8 §30 的两处口径声明

1. **本文的「9 年均价」只在 2 个单元上成立**（江苏/G06、江西/G06）。
   其余 34 个是「若干年观测的均值」，中位 5 年。论文若写「用省内观测均价」，
   需改为「用省内可获得年份的观测均值（中位 5 年，范围 1–9 年）」。
2. **浙江/G05 这一格没有观测**，价格来自批发价桥接。任何逐省结果若在浙江的
   禽肉（G05）上被单独解读，都要带上这个限制。

---

## 三十一、按建议执行五条决定：修 G06、修 gate、重跑验证（2026-10-27 第十六轮）

批次：`R200_203_b2_formal_20261027_222841`（EAR，替换 `_174710`）
脚本改动：`scripts/build_group_prices.py`、`scripts/check_contract_gates.py`、
`src/ontology.py`、`scripts/diagnose_price_panel.py`、`tests/test_b2.py`

作者裁定「按建议继续」，即 `TO_DECIDE.md` 五条决定全部取 A。其中决定 1/3/4 是写法与
取舍（不碰代码），决定 2/5 改动数据与验收逻辑，因此必须先做、再重跑验证。

### 31.1 决定 2：修 G06 的部分结构聚合

**旧行为**：三品类里只观测到猪肉时，把权重归一成 `pork=1.000`——牛肉（0.136）
与羊肉（0.076）被丢掉，等于「假设这两类不存在」，组价系统性偏低。

**新行为**（三态标签）：

| 情形 | 标签 | 行数（修后） | 处理 |
|---|---|---|---|
| 三品类齐全 | `structure_weighted_complete` | 27 | 按 .788/.136/.076 加权 |
| 缺品类但桥接表有值 | `structure_weighted_bridged` | **21** | 先桥接补全，再按完整结构加权 |
| 缺品类且桥接表也没有 | `structure_weighted_partial_lowerbound` | **3** | 保持归一（**下界**），标签显式声明 |
| 整组零观测 | `no_observation` | 12 | 缺失 |

修前 24 行部分结构，修后 21 行被桥接补全、**只剩 3 行仍是下界**。

**价格变化**：21 行，全部在 G06，**+1.95% ~ +36.57%，中位 +25.05%**。
其余 5 个决策组、其余省份、其余列**逐元素不变**（已逐列核对，非数值列也一致）。

#### 残留：福建 3 行仍是下界

| 省 | 年 | 值 | 桥接可得品类 |
|---|---|---|---|
| 福建 | 2017 / 2022 / 2023 | 28.09 / 30.87 / 25.63 | **无**（福建在桥接表里零覆盖） |

这 3 行相对福建自己的完整结构年份低估约 **54.1%**，但摊到 9 年均价只影响
**+2.4%**（福建 G06 面板均值 37.73，若上修 38.62）。量级很小，且标签已显式写明
`lowerbound`——**这是下界，不是估计值**。

> 这也是为什么标签要分三态：如果三态合并成一个 `structure_weighted_partial`，
> 修完的 21 行和没修成的 3 行就分不出来了，下次审计会把它们当成同一类。

#### 顺带修的两处

1. **权重标签顺序不稳定**：`_weighted()` 直接遍历 dict，导致同一组权重有时写成
   `beef=0.136/pork=0.788/lamb=0.076`、有时写成别的顺序，20 行一种、1 行另一种。
   审计时按标签字符串匹配会漏。已改为**按权重降序**固定顺序。
2. **`price_cny_kg_full` 与主口径在「两者都非空」处逐行相同**（6 省 × 6 组范围内
   197 行交集，max|diff| = 0）——但**这一列并没有变得冗余**：它比主口径多填了 87 行
   （full 非空 284 行 vs 主口径 197 行）。
   **⚠ 这里我上一版写错了**，原文说「两列逐行相同、`full` 已冗余」，是把
   「交集相同」误读成「整列相同」。§32.1 会说明这 87 行是什么，以及为什么它
   直接决定了「真值口径」那个决定能不能做。
   `diagnose_price_panel.py` 的护栏仍然保留（交集相同则不出对照），但**判据要改**：
   应判「交集相同且行数相同」才算冗余。

### 31.2 决定 5：修 G3 gate 的两条判定

| 改动 | 旧 | 新 |
|---|---|---|
| `thin` | **组级**：一个组总观测数够就过 | 保留组级 + **新增单元级** `MIN_CELL_PRICE_YEARS = 5` |
| `collapsed` | 所有多品类 observed 行 | **只在完整结构行上算**（排除 `structure_weighted_partial*`） |
| 覆盖率不足 | 不报告 | **WARN**（不 FAIL，因为这是数据限制不是违规） |

修后 G3 实测：

```
[PASS] G3 group_prices.csv
       完整结构行的「等于最低价」比例 0%（需 <50%，分母 48 行、已排除部分结构行）
       [WARN] 单元级覆盖率不足：7/28 个 (省,组) 单元有价年份 <5
       [WARN] 决策口径 k6_price（6 组 × 6 省 = 36 单元）覆盖率不足 13 个：
              山东/G05=1年, 山东/G07=1年, 浙江/G07=1年, 浙江/G02=2年,
              浙江/G08=2年, 山东/G04=2年
```

三点要注意：

1. **`collapsed` 从 45.1% 变成 0%**，分母从 51 行变成 48 行（3 行下界被排除）。
   这条指标的语义终于对了：它现在测的是「完整结构行有没有退化成取最低价」，
   答案是零。§30.3 说的「用被污染的指标检查污染」已解除。
2. **单元级门槛做成 WARN 而非 FAIL**。如果做成 FAIL，13 个单元会直接把 G3 打成
   FAIL，而这是**数据可得性**问题（原始统计年鉴就没有这些格子的分品类价），
   不是我们能修的错误。把它写成 FAIL 会逼着后续用一个假门槛去绕开它。
   但**必须在论文数据节披露**，所以 WARN 的文字里写了「必须披露」。
3. **覆盖率按两个口径各报一次**。合同口径 `include=1` 是 K=4（G02/G05/G06/G08），
   模型实际用的是 `k6_price`（多了 G04 与 G07）——**恰好是覆盖率最薄的两个组**。
   只按 K=4 报会低估问题（7/28 vs 13/36）。

G7 因 `model_manifest.json` 的 hash 漂移一度 FAIL，重建合同后恢复。7/7 通过。

### 31.3 重跑验证：成本变了，决策一步没动

`R200_203_b2_formal_20261027_174710`（旧）→ `_222841`（新），2400 行逐元素对比：

| 量 | 最大绝对变化 | 相对变化 |
|---|---|---|
| 6 个决策列 `q_*` | **9.8e-08 g/day** | — |
| `max_abs_dq_ref` | **< 1e-6**（0 行超过） | — |
| `total_cost` | 0.366 元/day | 中位 +0.197%，最大 +2.61% |
| `total_ghg` / `total_land` | 2.5e-11 / 2.0e-10 | **0.0000%** |

`total_cost` 逐省（D0）：

| 省 | 旧 | 新 | 变化 |
|---|---|---|---|
| 山东 | 9.345 | 9.523 | **+1.90%** |
| 浙江 | 13.101 | 13.376 | **+2.10%** |
| 江苏 | 11.027 | 11.191 | **+1.49%** |
| 江西 | 13.758 | 13.802 | +0.32% |
| 安徽 | 8.842 | 8.842 | 0.000% |
| 福建 | 10.369 | 10.369 | 0.000% |

安徽与福建为零，因为它们的 G06 观测行全是完整结构（没有部分结构行可修）。

**结论：G06 修正只动成本水平，不动决策。** 决策列变化 9.8e-08 g/day，
比判定容差（1 g/day）小 7 个数量级，是求解器浮点噪声。

这与 §28.4（组价变动 21.6% 不动决策）、§29.3（风险偏好 λ 0→1 不动决策）
一起，构成「EAR 零传导」的**第 5 条独立证据**——但方向不同：前四条是
「扰动进不去」，这一条是「修正真的进去了，但只到成本层」。

### 31.4 独立核对：参考解 q* 也没动

不走 B2 流程，直接用新旧面板各解一次确定性参考问题：

| 省 | ΔG06 价 | `max\|Δq*\|` | Δ成本 | Δghg | Δland |
|---|---|---|---|---|---|
| 山东 | +11.6% | **0.000** | **+2.98%** | 0.00% | 0.00% |
| 浙江 | +9.1% | **0.000** | **+3.27%** | 0.00% | 0.00% |
| 江苏 | +4.3% | **0.000** | +1.43% | 0.00% | 0.00% |
| 江西 | +2.0% | **0.000** | +0.61% | 0.00% | 0.00% |
| 安徽 / 福建 | 0% | **0.000** | 0% | 0.00% | 0.00% |

成本上升、`q*` 与 ghg/land 完全不变——符号自洽。

> 中间踩了一次自己的坑：先看到 `r.objective` 在**下降**，以为符号错了。
> 实际上 `r.objective` 是 **payoff 归一化**后的加权值（`normalized_cost_vector`
> 除以各目标取值区间），价格涨了归一化尺度也变，它的方向不能当成本方向读。
> 要读成本必须用原始 `objective_coeff @ q`。**又一次「先确定被比较的是什么」。**

### 31.5 一个必须写进论文方法节的口径警告：`objective_gap` 不可跨价格版本比较

`objective_gap = [F(q) − F(q*)] / |F(q*)|`，而 `F` 用的是**逐目标 payoff 区间缩放**。
价格面板一变，成本目标的 payoff 区间就变，归一化尺度跟着变——**同一个 `q` 会得到不同的 gap**。

实测（同一次修正前后）：

| 方法 | `q` 变化 | gap 最大变化 |
|---|---|---|
| D0 / D1 / D3 | 0 | **6.5e-16**（机器精度） |
| **D2** | 0 | **0.0092**（相对 **1.15%**） |

D0/D1/D3 的 gap 恒为 0（它们的最优解就是参考解，分子恒 0，归一化怎么变都不影响）；
**只有 D2 这类远离参考解的方法，gap 会随归一化尺度漂移**。

所以：**不同价格面板版本之间不能直接比 gap**。本文所有 gap 数字必须标注
「同一面板版本内可比」。这条在 §31.3 之前没人注意，因为此前面板只改过一次且
当时没做逐元素对比。

### 31.6 决定 1 / 3 / 4 的落档（写法，不碰代码）

| 决定 | 取 A 后的正文写法 |
|---|---|
| **1. M2 用 EAR** | 写成**零结果报告**。5 条独立证据全部 0/6 省：遮蔽协议位移 0.298%、合并价 15–65%、桥接口径 2.6–21.6%、风险偏好 λ 0→1、**组价修正 21 行（本轮新增）**。前三条扰动价格、第四条扰动目标函数、第五条是**真实数据修正** |
| **3. B1 不接价格点估计** | 明确写「B1 通过残差分布进入 B2，不进入价格点估计」，并给出理由：会造成决策输入与「真值」同源 MICE 的循环 |
| **4. EAT 只作定性对照** | 正文不给 EAT 点估计。理由：正式批次 `R200_203` **只有 CDG**（2400 行）；且 EAT 的 λ 曲线是阶跃、跳变点跨 seed 漂移 0.40–0.90，**没有自然的 λ 可报**（§29.4） |

### 31.7 证据等级

| 结论 | 等级 |
|---|---|
| G06 修后 21 行涨价 +1.95%~+36.57%（中位 +25.05%）、其余列逐元素不变 | `structural`（逐行对比，可复现） |
| 福建 3 行仍为下界、摊薄后只影响 +2.4% | `structural`（同上） |
| G3 的 `collapsed` 从 45.1% → 0%（分母 48 行） | `formal`（gate 脚本可复现） |
| 决策列变化 9.8e-08 g/day、ghg/land 完全不变 | `formal`（2400 行逐元素，`R200_203_b2_formal_20261027_222841`） |
| `q*` 不动、成本 +0.61%~+3.27% | `formal`（独立求解，不依赖 B2 流程） |
| `objective_gap` 跨面板版本不可比 | `formal`（定义层面可证 + 实测 D2 漂移 1.15%） |

### 31.8 RNI 对照批次重跑后，查出一个此前没人注意的问题：**D0 是二值开关**

批次：`R200_203_b2_formal_20261027_224315`（RNI，替换 `_174714`）
诊断：`DIAG_d0_bistability_20261027_231703`（`structural`，纯读 CSV 不求解）
脚本：`scripts/diagnose_d0_bistability.py`（新增）

重跑后主指标变了：

| 方法 | 变化率（旧） | 变化率（新） | q 最大变化 |
|---|---|---|---|
| D0 | **0.498** | **0.460** | **110.97 g/day** |
| D1 | 0.013 | 0.013 | 0.0000 |
| D2 | 1.000 | 1.000 | 0.0000 |
| D3 | 0.333 | 0.333 | 0.0000 |

D1/D2/D3 逐位不变，**只有 D0 变了**，而且变的是 50–111 g/day 的量级。查下去发现不是「数值扰动」：

#### 事实 1：D0 的解在每个省只有两个取值

以 `q_G08`（蔬菜）为例，100 个协议单元里：

| 面板 | 省 | 取值数 | 两个取值 | 多数侧占比 |
|---|---|---|---|---|
| 旧 | 安徽 | **2** | 428.40 / 477.39 | 0.98 |
| 旧 | 山东 | **2** | 350.78 / 461.75 | 0.98 |
| 旧 | 浙江 | **2** | 396.71 / 471.58 | 0.99 |
| 新 | 安徽 | **2** | 428.40 / 477.39 | 0.93 |
| 新 | 山东 | **2** | 350.78 / 461.75 | 0.92 |
| 新 | 浙江 | **2** | 396.71 / 471.58 | 0.82 |

**六个省的「两取值间距」是固定的六个常数**：29.03 / 36.41 / 48.99 / 54.00 / 74.87 / 110.97。
这不是连续响应，是**两个顶点之间的切换**——`q_G08` 只可能在 A 或 B，不存在中间值。

对照组：**EAR 下 D0 的 `q_G08` 只有 1 个取值**（六个省全部，极差 0.00e+00），
且新旧面板完全相同（436.06 / 368.14 / 422.18 / 456.69 / 408.42 / 448.57）。

#### 事实 2：切换由「D0 的池化价格」触发，而池化价格逐单元不同

`scripts/run_b2.py` 里 D0 的价格是：

```python
imputed_panel = base_panel * (1.0 + cell.shift.reindex(index=provinces))
pooled = imputed_panel.mean(axis=0, skipna=True)      # 跨省均值
```

`cell.shift` 是**该协议单元各自的位移**，所以 `pooled` 逐单元不同。实测（100 单元 × 6 组）：

| 组 | 池化价格跨单元的极差 |
|---|---|
| G02 蛋 | 3.42% |
| G04 谷物豆类 | 2.58% |
| G05 禽肉 | 3.53% |
| **G06 红肉** | **1.06%** |
| G07 水产 | **13.00%** |
| G08 蔬菜 | 3.22% |

全局 `|rel|` 中位 **0.115%**、最大 11.50%。也就是说 **1%–13% 的价差就足以让 D0
在两个顶点之间跳**——这正是「顶点稳定半径」在 D0 这一侧的表现。这就是每个省那批「少数侧」单元的来源
——不是求解误差，是**被 0.3% 推过边界的单元**：

| 面板 | 少数侧占比（6 省） |
|---|---|
| 旧 | **1%–2%** |
| 新 | **7%–27%** |

旧面板下 D0 稳稳坐在低顶点（98–99%），新面板下池化价格整体抬高了几个百分点，
于是有 7%–27% 的单元被推过边界。

#### 事实 3：「哪 3 个省 D0≠D1」是个开关，不是测量

**D1 也是二值开关**，但它的分布跨面板**完全不动**：

| 省 | D1 的 `q_G08` 取值计数（旧 / 新面板） |
|---|---|
| 安徽 | 477.39×97 / 428.40×3（两版相同） |
| 山东 | 461.75×97 / 350.78×3（两版相同） |
| 浙江 | 471.58×98 / 396.71×2（两版相同） |
| 江苏 / 江西 / 福建 | 单一取值（两版相同） |

所以「D0≠D1」当且仅当**D0 的多数侧与 D1 的多数侧落在不同顶点**：

| 面板 | D0 多数侧 | D0≠D1 的省 | 与 D1 同顶点的省 |
|---|---|---|---|
| 旧 | **低顶点**（98–99%） | 安徽 48.99 / 山东 110.97 / 浙江 74.87 | 江苏 / 江西 / 福建 |
| 新 | **高顶点**（73–93%） | 江苏 54.00 / 江西 29.03 / 福建 36.41 | 安徽 / 山东 / 浙江 |
| smoke（`_151138`，未加位移） | 低顶点 | 江苏 54.00 / 江西 29.03 / 福建 36.41 | 安徽 / 山东 / 浙江 |

三种价格构造给出**三套不同的省份集合**，用的却是**同一组六个常数**。

**结论：D0 的「3/6 省」不是「失去省级价格信息导致 3 个省决策变化」这个命题的测量，
而是「D0 的池化价格此刻落在边界的哪一侧」这个开关的读数。**
价格修正 2–14% 就把多数侧整体翻过去了，所以省份集合整套换掉。

#### 这对论文的三点影响

1. **不能报「3/6 省（江苏/福建/江西）」这个具体名单。** 它在旧面板上是
   「安徽/山东/浙江」，在 smoke 上是「江苏/江西/福建」，在修正后又是「江苏/江西/福建」。
   名单是开关读数，不是结论。
2. **`D0 变化率 0.498` 必须改成 0.460，且必须标注它是开关侧占比。**
   这个数字在新面板上是 46.0%，含义是「D0 落在少数侧的单元比例」，
   **不是**「46% 的单元决策不可靠」。
3. **这反而加强了 EAR 主线。** EAR 下 D0 的 `q_G08` 只有一个取值、跨面板不变——
   池化价格的 0.3% 位移和 G06 的 2–14% 修正**都没有跨过任何约束面**。
   RNI 下 D0 恰好坐在面上，所以它对 0.3% 都敏感。这正是 §26.3「顶点稳定半径
   ≫ 协议位移」的同一件事，只是这次是从 D0 这一侧看到的。

> **⚠️ 同时更正一条此前记录的「事实」**：`docs` 与项目记忆里都写着
> 「RNI 口径下 D1 vs D0 位移 3/6 省：江苏 54.00 / 福建 36.41 / 江西 29.03」。
> 追查后发现这组数字出自 **`R200_203_b2_smoke_20261027_151138`（smoke，2 repeats，
> 未加协议位移）**，而**正式批次 `_174714` 给的是安徽 49.00 / 山东 110.97 / 浙江 74.87**。
> 也就是说这条「事实」**从来不是正式批次的结果**，且它与正式批次不一致的原因
> 正是本节说的开关效应。引用时必须带面板版本与批次号。

#### 证据等级

| 结论 | 等级 |
|---|---|
| D0 的 `q_G08` 在 RNI 下每省恰有 2 个取值、间距为 6 个固定常数 | `formal`（2400 行，可复现） |
| EAR 下 D0 的 `q_G08` 每省恰有 1 个取值，且跨面板不变 | `formal`（同上） |
| 省份集合随价格构造翻转（三种构造三套） | `formal`（`DIAG_d0_bistability_20261027_231703` 给出 2 个互斥集合） |
| D1 也是二值开关、但其分布跨面板不变（97/3） | `formal`（同上） |
| 池化价格跨单元极差 G06 1.06% / G07 13.00%，中位 \|rel\| 0.115% | `formal`（100 单元直接计算） |

---

## 三十二、「真值口径」这个决定做不了——查下去发现它不是一个数据问题（2026-10-27 第十七轮）

run：`R002_group_freeze_20261027_232440`（合同重建，7/7 gate）
脚本改动：`scripts/build_group_prices.py`、`scripts/diagnose_price_panel.py`、`tests/test_b2.py`

### 32.1 起由：我上一轮写错了一句话，顺着错话往下查

§31.1 我写「`price_cny_kg_full` 与主口径现在逐行相同（303 行 max|diff| = 0），
修完之后两者就是同一个东西了」。**这句话是错的。**

真实情况（6 省 × 6 组范围）：

| 列 | 非空行数 | 9 年全有值的单元 |
|---|---|---|
| `price_cny_kg`（主口径） | **197** / 324 | **3** / 36 |
| `price_cny_kg_full` | **284** / 324 | **28** / 36 |

两列在**交集**（197 行）上确实逐行相同（max|diff| = 0），但 `full` **多填了 87 行**
——那些是「整组零观测」的年份。我把「交集相同」误读成「整列冗余」了。

> 教训与 §27.7、§29.6 同源，第三次：**先确定被比较的是什么**。
> 这次是「交集相同」vs「整列相同」。

#### 顺着这条线查出的真问题：`truth_eligible` 的判据错了

`scripts/build_price_bridge.py` 与 `build_group_prices.py` 的 docstring 都写着
「**桥接行一律 `truth_eligible=False`**，不能用于真值参照」。桥接表 278 行的
`note` 里也逐行写着 `truth_eligible=False`（方法为 `wholesale × category_ratio(median)`）。

但 `build_group_prices.py` 里这个字段是这样算的：

```python
"truth_eligible": bool(observed_block["truth_eligible"].any()) if n_obs else False
```

判据是「**有没有观测**」，不是「**组价里有没有非实测成分**」。于是 §31 修完之后：

| 标签 | 行数 | 其中 `truth_eligible=True` |
|---|---|---|
| `structure_weighted_complete` | 27 | 26 |
| `structure_weighted_bridged`（含 21.2% 桥接质量） | **21** | **20** ← 违规 |
| `structure_weighted_partial_lowerbound`（只观测到猪肉） | 3 | **3** ← 违规 |

**23 行被标成「真值可用」，而它们的价格里分别有 21.2% 的桥接质量和 100% 的单品类下界。**

这是我上一轮修 G06 时引入的。已改判据为 `complete and observed_block["truth_eligible"].any()`
（全部品类实测才算真值可用），并新增 `truth_eligible_reason` 列区分
`complete` / `bridged` / `partial_lowerbound`。重建后 **23 行 True→False，价格一行未动**。

> **数值影响：零。** 因为 `Contract.price_panel()` **根本不过滤 `truth_eligible`**——
> 它只做 `groupby(...)["price_cny_kg"].mean()`。所以这次改的是**元数据契约**，
> 不是数值。这条也顺带说明：真值面板本来就包含桥接值，不是「修完才有」。

### 32.2 能不能把真值改成「只取实测」？不能

试了一下：把 `price_panel()` 限定为 `truth_eligible=True`，结果 **浙江直接不可评估**：

| 省 | 仅实测后仍缺值的单元 |
|---|---|
| **浙江** | **G05（禽肉）、G06（红肉）** |

- 浙江/G05 是**零观测**，9 年全部来自批发价桥接（§30.3 已记录）；
- 浙江/G06 的 5 个有值年份全部是桥接补全或单品类下界，无一为完整结构。

所以「真值只取实测」这条路径**在浙江上行不通**——不是我们不肯，是数据没有。

### 32.3 换真值到底会动什么？**决策一步不动，成本动 ±5%~10%**

三种真值口径各解一次确定性参考问题（EAR，CDG）：

| 真值口径 | 六省 `max\|Δq*\|` | 成本变化 | 备注 |
|---|---|---|---|
| 主口径（现用，含桥接 G06） | 基准 | — | — |
| `price_cny_kg_full`（桥接补满） | **0.00** | **−10.0% ~ +0.7%** | 江苏 −9.98%、浙江 −8.22% |
| 仅实测（`truth_eligible`） | **0.00** | **−4.7% ~ +3.7%** | **浙江不可评估** |

**三者的 `q*` 完全相同（六省全部 0.00 g/day）。** 成本差 5%–10% 全部来自价格水平，
不是决策变化。

顺带查清了为什么 `q*` 这么稳：`q*` 里 G02、G04 贴着**上界**，G07 贴着**下界**，
剩下 3 个自由组被 **9 条营养约束 + 1 条联合约束**压住（10 约束 / 3 变量）。
所以价格只能改成本，改不动顶点。**但这不等于价格永远无关**：
把价格按对数正态（σ=0.6，约 ±80%）随机扰动，六省会分别出现 **5–7 个不同解**——
「零传导」是一个**有半径的局部性质**，不是全局无关。

### 32.4 为什么 `full` 不能直接当真值：它有水平断点

`full` 多填的 87 行里，被补年份的价格系统性低于观测年份（**25 个单元中 18 个偏低，
中位 −12.9%**）。最典型的是江苏/G08（蔬菜）：

| 年 | 主口径（观测） | `full`（桥接） |
|---|---|---|
| 2016–2020 | — | 5.79 / 5.03 / 5.19 / 5.55 / 6.28 |
| 2021–2024 | 9.02 / 8.60 / 8.82 / 10.04 | 同左 |

**2020 → 2021 有 40% 的断点**，且此后维持在高位。真实的蔬菜价格不会这样跳。
同组在安徽就没有这个问题（桥接 5.17–7.55 vs 观测 4.54–5.62，量级一致）。

所以 `full` 不是一个「更完整的真值」，而是一个**混了两套价格概念的序列**
（批发价 × 品类比价 vs 零售观测），在个别格子上有 30%–39% 的水平断点
（江苏/G08 −39%、江西/G05 −39%、福建/G06 −30%）。

### 32.5 结论：这个占位**无法用现有数据解决**，只能披露

我上一轮建议「用遮蔽前伪完整面板作真值（选项 A）」——**这个建议是错的**，撤回。
理由：

1. 唯一的「伪完整面板」候选是 `price_cny_kg_full`，而它是桥接值，
   **契约上就标着 `truth_eligible=False`**，且有 30%–39% 的水平断点；
2. 「只用实测」在浙江不可行（G05/G06 零实测）；
3. 三条路径的**决策完全相同**（`max|Δq*| = 0.00`），差别只在成本水平（±5%~10%）。

**所以「真值占位」不是一个待修的数据缺陷，而是这份数据的固有边界。**
正确处置是**如实披露**，而不是继续找一版「更真」的面板：

> 论文写法：评估基准（真值）为**省内可获得年份的实测均价**（中位 5 年，范围 1–9 年）；
> **浙江的禽肉（G05）与红肉（G06）没有可用的实测组价**，其基准价来自批发价桥接
> （`truth_eligible=False`）。已核验：把基准在三种口径间切换，六省决策
> **完全不变**（`max|Δq*| = 0.00`），成本水平变动 −10%~+4%。因此本文的
> **方法比较与决策结论不受基准口径影响**，但**成本/gap 的绝对水平带 ±10% 的口径不确定性**。

### 32.6 这对 R200–R203 的 DONE 判定意味着什么

§31 我说「R200–R203 不能标 DONE，因为真值占位未解决」。查完之后要修正这个说法：

| 原判断 | 修正后 |
|---|---|
| 真值占位 = 待修的数据缺陷 | **真值占位 = 固有边界**（浙江两格零实测） |
| 需要换真值才能标 DONE | **换真值也解决不了**；应当以「披露 + 不变性检验」结案 |
| 阻塞 DONE | **不再阻塞**，但需在论文数据节写入 §32.5 那段 |

即：**R200–R203 可以标 DONE-conditional**（带口径披露），而不是 DONE。
是否这样标，仍请作者定——因为这决定了论文里要不要专门写一段数据边界。

### 32.7 证据等级

| 结论 | 等级 |
|---|---|
| `full` 比主口径多填 87 行、9 年全有值单元 3/36 → 28/36 | `structural`（逐单元计数） |
| 23 行 `truth_eligible` 由 True 改 False，价格未动 | `formal`（重建前后逐元素对比） |
| 仅实测真值时浙江 G05/G06 无数据 | `structural`（同上） |
| 三种真值口径下 `max\|Δq*\| = 0.00`、成本 −10%~+4% | `formal`（独立求解，六省） |
| `q*` 由边界 + 营养约束钉住（10 约束 / 3 自由变量） | `formal`（贴界状态可查） |
| ±80% 随机价格下出现 5–7 个不同解 | `structural`（每省 60 次抽样） |
| `full` 有 30%–39% 水平断点（3 个单元） | `structural`（逐年序列可查） |

### 32.8 面板 hash 漂移：v2→v3 是**纯元数据变更**，不重跑 B2

改 `truth_eligible` 判据会让 `group_prices.csv` 的 sha256 变（`eadc85e6…` → `3b7ae42d…`），
而已跑的两个正式批次记录的是 v2 的 hash。**这会看起来像「批次用了旧面板」，实际不是。**

| 版本 | hash（前 16） | G06 均值 | `truth_eligible=True` | 改了什么 |
|---|---|---|---|---|
| v1 原始 | `54f7fee0ce3898ce` | 43.92 | 242 | — |
| v2 G06 修完 | `eadc85e6af57c421` | 47.03 | 242 | 21 行涨价（+1.95%~+36.57%） |
| v3 当前 | `3b7ae42d9fbc0fc9` | 47.03 | **219** | **价格 0 行变化**，23 行标记 True→False |

不重跑的四条依据（逐条可查）：

1. 价格列逐元素相同：756 行合并比对，`price_cny_kg` 与 `price_cny_kg_full` 的
   `max|diff|` 均为 **0.000e+00**；
2. `Contract.price_panel()` 不读 `truth_eligible`（只做 `groupby(...)["price_cny_kg"].mean()`）；
3. 遮蔽协议读的是**消费面板**（`group_audit.csv`，键 `province/group_raw/year`），
   该文件**没有 `truth_eligible` 列**，`make_mask()` 走 `panel["observed"]` 分支；
4. 合同重建后只有 3 个文件变（`group_prices.csv`、`model_manifest.json`、
   `contract_gate_report.json`），`group_audit*` 等 34 个产物**逐字节不变**。

台账见 `docs/PANEL_LEDGER.md`（三个版本 + 各批次对应哪一版 + 引用规则）。

> 这条值得单独记一笔，因为它是「hash 变了但结果没变」这种最难自证的情况：
> **光看 hash 无法区分「价格改了」和「只改了标记」**。要么像这里一样逐元素比对价格列，
> 要么把元数据与数值拆成两个文件。

### 32.9 顺带修一个「还在跑、但已经测不到东西」的指标

`scripts/diagnose_price_panel.py` 的第 3 节原本报 **「G06 部分结构行低估中位 0.0%」**——
而 §31.1 明明写着福建 3 行低估 54.1%。矛盾出在算法：

```python
g6["understate_pct"] = (g6["price_cny_kg_full"] / g6["price_cny_kg"] - 1.0) * 100.0
```

它测的是「**主口径 vs 桥接补满**」。§31 修完之后主口径**本身就含桥接补全**，
两者在桥接行上恒等 → 这个量**按构造恒为 0**。它还在正常输出、还在进 metrics、
看起来是个健康的 0，实际什么也没测。

改成有意义的比较：**下界行（只观测到单品类）比同省其它年（complete/bridged）低多少**。
参照来源写进 `ref_source` 列，因为参照本身也含桥接成分，这是**估计不是测量**。

| 指标 | 修前 | 修后 |
|---|---|---|
| `g06_lowerbound_rows` | 3 | 3 |
| `g06_lowerbound_understate_median_pct` | **0.0**（假） | **54.1** |
| `g06_lowerbound_ref_sources` | 无此字段 | `same_province_complete_or_bridged` |
| `g06_pooled_lb_to_ref_ratio` | 无此字段 | 0.585 |

修后 54.1% 与 §31.1 手算一致。

run：`DIAG_price_panel_20261027_232721`（修前，含假 0.0%）→
`DIAG_price_panel_20261027_232756`（修后）。`g06_partial_structure.csv` 的列名也从
`price_obs/price_full/understate_pct` 改成 `price_lowerbound/reference_price/understate_pct/ref_source`
——**旧列名会让人以为它还是「主口径 vs full」的对照**。

⚠ 这个 54.1% 是**省级均值比**，不是逐年比：三行的 `understate_pct` 完全相同（54.091），
只有 `reference_price` 随各年下界价等比缩放（43.28 / 47.57 / 39.49）。所以它是
「福建下界年比福建完整年系统性低多少」的估计，**不是每一年的独立测量**。
若要有逐年值，需要福建的逐年分品类价，而桥接表对福建零覆盖——拿不到。

> **这是「修数据」带出来的第二类副作用**：修完之后，原先用来量化缺陷的指标失效了，
> 而且失效方式是**静默返回 0**，不是报错。凡是「A/B 两列的差」型指标，
> 在把 B 合并进 A 之后都要重新检查一遍。

---

## 三十三、项目治理：把 tracker 变成可被脚本核对的账本（2026-10-28 第十八轮）

> 本轮**没有跑任何求解**，也没有改任何 run 产物。改的是文档与一个校验脚本。

### 33.1 为什么现在做

`EXPERIMENT_TRACKER.md` 跨 17 轮累积到 780 行，里面混了四种东西：run 台账、进度总览、
结构诊断的叙述、以及 M2 的推导过程。它的引用是**散文式**的——写「run: `outputs/xxx`」，
但没有任何机制保证那个目录还在、或者那段数字真的出自那个目录。

清理（`CLEANUP_2026-10-28.md`）之后这种风险变高了：目录从 199 个降到 36 个，
正文却还留着对已删目录的引用。**「文档说的」与「磁盘有的」必须能机械对齐**。

### 33.2 查出的四个缺陷（都可现场复核）

| # | 缺陷 | 证据 |
|---|---|---|
| 1 | **R002 引用了过期批次**：tracker 写 `run: outputs/R002_group_freeze_20261027_150751` | 该目录 `metrics.json.artifacts["group_prices.csv"].sha256` = `54f7fee0…`，即**面板 v1（G06 未修）**；磁盘当前是 `3b7ae42d…`（v3）。更糟的是合同表里引的 `collapsed 0%` / `7/28` / `13/36` **只存在于 `_232440` 的 gate 报告**——引用与数字出自两个不同 run |
| 2 | **计数过期**：合计行写「另有 164 个含 `DIAG_*` 的目录」 | 清理后实测：36 个目录 = 15 批次 + 20 个 `DIAG_*` + 1 个遗留 `R307_binding` |
| 3 | **状态与证据等级混用**：R300–R303 标 `DONE` | 其 `metrics.json.evidence_status` 是 `plumbing_only`，产物 `M3_all_smoke_*` 本身是 smoke 轮次。`DONE` 被读成「可进正文」的风险是真实的 |
| 4 | **`evidence_status` 没有统一词表** | 36 个目录里 6 种取值：`plumbing_only`、`structural`、`diagnostic_only`、`masking_protocol`、`None`、缺省。**不能当证据等级用** |

### 33.3 处置

**新增 `scripts/check_tracker.py`**（15 项校验，退出码即门禁）：
表结构 / 状态词表 / 里程碑归属 / 引用路径可解析 / 目录全覆盖 / DONE 行有产物 /
DONE 行目录带 `DONE` 标记 / 汇总计数自洽 / 索引覆盖 / 证据等级词表。
已清理目录必须登记在脚本的 `RETIRED_DIRS` 里并写明替代者，否则报错——**不允许悄悄引用已删目录**。

**tracker 结构性改造**：

1. 新增「状态与证据等级」小节，把 `DONE` / `DONE-conditional` / `PARTIAL` / `TODO` / `SUPERSEDED`
   与 `formal` / `formal_conditional` / `sensitivity` / `structural` / `smoke` 分开定义，
   并写明两者**正交**：`DONE` 只说明「跑完、产物在库」；
2. 新增「产物索引」：46 个 run ↔ 36 个目录逐条对账，21 个结构诊断目录标注支撑的结论与出处 §；
3. R002 引用改 `_232440`，并注明 `_150751` 是 v1 留档、其 gate 报告不得引用；
4. 合计改为 `26 DONE / 4 DONE-conditional / 0 PARTIAL / 16 TODO`；
5. 首轮运行时 5 项 FAIL（含 14 个 DONE 行「无产物可追」、24 个目录未被提及），全部修完。

### 33.4 执行 M2 定稿（作者 2026-10-28 裁定：选项 A）

R200–R203 由 `PARTIAL` 改为 **`DONE-conditional`**，证据等级 `formal_conditional`。
**`metrics.json` 一个字没改**（`evidence_status: plumbing_only` 保留）——改元数据会让
`artifacts` 里的 hash 与内容失配，而 `plumbing_only` 指的正是「真值占位」这条已知边界，
与 `DONE-conditional` 是同一件事的两种措辞。

放行条件三条（写死在 tracker「R200–R203 的定稿条件」）：

1. **基准口径披露**：省内可获得年份均价（中位 5 年、1–9 年），不是 9 年均价；
2. **真值边界披露**：浙江 G05/G06 无实测、价格来自桥接；三口径不变性检验 `max|Δq*| = 0.00`；
3. **不引用开关读数**：RNI 只报机制与区间，不报「D0≠D1 的省份名单」。

### 33.5 验证

```
python scripts/check_tracker.py      → 15 项全绿
    run 行 46 条；outputs 目录 36 个；正文引用目录 39 个（其中已清理 3 个已登记）
python -m unittest discover -s tests → 69 tests OK
python scripts/check_contract_gates.py → 7/7 PASS（但见下方环境说明）
```

> **环境说明（不影响结论）**：在 DSH 沙箱内跑 `check_contract_gates.py`，
> 七条 gate 全部打印 `[PASS]`（含 G3 的两条覆盖率 WARN），但脚本**无法回写**
> `data/processed/contract_gate_report.json`——沙箱只允许写工作区根目录，
> 子目录（`data/`、`docs/`、`outputs/`）一律 `PermissionError`。
> 因此该命令在本环境退出码为 1，**判定以打印结果为准**；磁盘上已有的报告
> （2026-10-27 23:28:39，7/7）未被改动。在正常 shell 下该脚本会正常落盘。
> 校验脚本 `check_tracker.py` 只读不写，不受影响。

### 33.6 本轮教训

**文档里的 run ID 若不能被脚本解析，它就只是叙述，不是证据。**
此前每一处引用都「看起来对」，是因为没人把 46 行 × 36 个目录两两对过。
建议此后每次改 tracker 都跑 `check_tracker.py`，把它当 gate 用，而不是当检查表用。

---

## 三十四、上海口径结案：不是「补一格」，是「改样本」（2026-10-28）

### 34.1 为什么必须先解决

M4 的 R400–R406 是「七地区各 3 情景」。但主口径 `k6_price` 需要 G07（水产品），
上海在该组上**整块缺失**——这不是「结果不好」，是**实例装不起来**。
不裁定就无法写 `run_m4.py`：R401 到底产出决策数字还是别的，决定脚本骨架。

### 34.2 查清的四条事实（`outputs/R401_shanghai_availability_20261028_180508/`）

| 事实 | 数值 | 出处 |
|---|---|---|
| 上海 G07 有价年数 | **0 / 9** | `coverage_matrix.csv`；权威面板标 `整块缺失-品类 / P0` |
| 批发价桥接表品类 | 9 类，**无水产品** | `price_bridge_wholesale.csv` 的 `category` 去重 |
| `k6_price` 需要 / 上海缺 | 6 组 / **G07** | `scope_gap.csv` → `shanghai_usable=False` |
| `k4_official` 需要 / 上海缺 | 4 组 / 无 | `scope_gap.csv` → `shanghai_usable=True` |

上海在其余组上也很薄：G02 3 年、G04 1 年、G05 **1 年**、G06 7 年、G08 3 年。

### 34.3 一条容易误用的记录（新发现）

`data/input/clean_tables/prices.csv` 里有一条 **上海水产品 30.26 元/kg**（记录号 P023，
`source_file=零售价格表.xlsx`、`source_row=5`）。它与权威面板矛盾——后者把该组 9 年全标为缺失。

查清：它是**早期扁平清洗表**的产物，来自 `零售价格表.xlsx` 的 `Sheet1`（单张表），
而主分析用的 `price_panel_clean.xlsx` 是**分省工作表**（`上海!B5–J5` 全空）。
两者不同源，且该记录**没有年份字段**，无法定位到 2016–2024 的任何一年。

**结论：不能用。** 强行拿它充当某一年，等于给一个组建「年份不明的价」，
比不补更糟（会以「有观测」的名义污染 `observed` 与 `truth_eligible` 标记）。
已写进 R401 的 `report.md` 与 `metrics.json.legacy_single_point_records`，供数据节引用。

### 34.4 为什么不能「顺手补上」

D0 的池化价按**口径内可用省**计算（§26 已收敛到 `Contract.pooled_price(provinces)`）。
把上海加进 `k6_price` 的实际后果不是多一行结果，而是：

1. 池化价变 → 其余 **6 省的 D0 全部变**；
2. RNI 附录那套「`D0 变化率` 0.460」「D0≠D1」的读数**全部作废**（它本来就是开关读数）；
3. `k6_price` 的语义会在 35 处脚本/文档里被悄悄改写；
4. 需重跑 B2 两批（≈1 h）+ M3 网格（≈30 min），并重发 M2 的 `DONE-conditional`。

收益只是「多一个样本很薄的省」。**为一个薄省动摇刚定稿的零结果链，不划算。**

### 34.5 裁定与执行（方案 B）

| 项 | 内容 |
|---|---|
| 裁定 | 上海**不进入决策层**；主口径维持 6 省 `k6_price`，不重跑 |
| R401 | 由「上海 3 情景」改为**数据可得性报告**（预注册修订 `R-2026-10-28-c`），已产出 |
| 附录 | `k4_official` 下上海单点结果只作对照，**不得与 K=6 并列**（§21.4：可行率不可跨口径比较） |
| 下游影响 | R503 地区热图只画 6 省；论文方法节写一句「上海因 G07 整块缺失出局，桥接表不含水产品、仓库内不可修复」 |

**没有改任何既有产物**：R401 是新增目录，B2/M3 的 36 个目录与全部合同文件逐字节未动。

---

## 三十五、M4 开工：附录单点 + `run_m4.py` 骨架（2026-10-28）

### 35.1 上海 `k4_official` 附录单点（方案 B 第 2 条）

run：`outputs/APPENDIX_shanghai_k4_official_20261028_181254`
（`--scope k4_official --provinces 上海 --scenario CDG --profile smoke --bounds-basis ear`）

| 方法 | `\|Δq\|` 中位 | 变化率 | gap 均值 | 可行(活跃) |
|---|---|---|---|---|
| D0 | 0.00 | 0.000 | 0.000 | 1.000 |
| D1 | 0.00 | 0.000 | 0.000 | 1.000 |
| D2 | 85.05 | 1.000 | −0.720 | 0.000 |
| D3 | 0.00 | 0.000 | 0.000 | 1.000 |

**与 6 省主结果同型**：D0≡D1≡D3、只有 D2（无营养约束）移动。
它的价值不是「多一个省」，而是证明「口径决定样本」——同一套数据下上海能进 K=4、进不了 K=6。

⚠ 目录内已写 `APPENDIX_ONLY.json`，声明：**不得与 K=6 并列、不并入 46 run 计数**。
为避免误命名，本轮给 `scripts/run_b2.py` 补了 `--run-id`（原先目录前缀硬编码为
`R200_203_b2_<profile>`，跑附录会生成一个看起来像正式批次的目录；顺带修了 AUDIT P2-4 的一项）。

### 35.2 `run_m4.py`：只实现能定死的那一块

| 块 | run | 状态 |
|---|---|---|
| `provinces` | R400 / R402–R406 | ✅ 已实现并冒烟通过 |
| `looro` | R407 | ❌ 未实现：**「留一拟合的是什么」没定义** |
| `delta` | R408 | ❌ 未实现：`posterior_scenarios` 无尺度参数，事后缩放是新协议 |
| `bounds` | R409 | ❌ 未实现：`decision_bounds.csv` 只有一套冻结边界，四套变体的生成规则未定 |

三个未实现的块**直接 `SystemExit` 并打印缺什么**，不返回占位结果。
理由：δ 与边界变体一旦自行假定，δ 的语义就无法与 B1 的残差定义对齐，R409 也会因改变可行域
而与「决策边界口径」冲突——这类假设必须先进 Plan，不能进代码。

### 35.3 标签规则（新定义，论文方法节须照抄）

```
d1 = sign(q_D1 − baseline)     # |Δ| < DIRECTION_TOL = 1.0 g/day 记为 0
d3 = sign(q_D3 − baseline)
label = d1==d3==+1 → stable-up
        d1==d3==−1 → stable-down
        d1==d3== 0 → stable-neutral
        d1!=d3     → data-sensitive
direction_agreement = 该 (省,情景) 下 d1==d3 的组占比
```

`DIRECTION_TOL` 沿用 `src/b2_evaluate.py` 的既有定义，没有新造容差。

### 35.4 冒烟（单省 20 场景，已删目录）

`--block provinces --provinces 安徽 --scenario CDG --n-scenarios 20`：

```
cells ok=1/1 | agreement_mean=0.833
labels: stable-up 3 / stable-down 2 / stable-neutral 0 / data-sensitive 1
```

6 组里唯一的 `data-sensitive` 是 **G05 禽肉**：D1 判「持平」（+0.46 g/day < 1.0 容差），
D3 判「下降」（−24.30）。这正是标签规则要抓的情形——不是「解变了」，
而是**在容差带边缘、两种口径给出不同方向**。冒烟目录 60 秒可重跑，未保留。

### 35.5 遗留：三条待定协议

R407/R408/R409 的实现都卡在同一件事上——**协议没写死**。补齐后 `run_m4.py` 只需加三个函数，
装配与求解、标签与落盘的链路（本轮的 `provinces` 块）可以直接复用。

> **2026-10-28 晚已补齐**，见 §36。

---

## 三十六、R407/R408/R409 落地：三条算子定死，并验明扰动真的生效（2026-10-28）

### 36.1 三条算子（修订 `R-2026-10-28-d`，已写入 Plan §B4）

| run | 算子 | 比较基准 |
|---|---|---|
| R407 | 逐省留一，**只重算 D0 池化价**；B1 残差池不动 | 全样本 D0 |
| R408 | `mult' = exp((1+δ)·log mult)`，δ ∈ {−0.5,0,+0.5}，求 D3 | δ = 0 |
| R409 | low/high = 三情景边界逐元素 min/max；mid = HEAL_base；worst = 交集 | mid |

三条都写进 `scripts/run_m4.py` 的 `PROTOCOLS` 常量与对应 block 函数，与 Plan 逐字一致。

### 36.2 先踩了一个坑：`use_chance_constraint=False` 会把营养约束一起删掉

冒烟先跑出「R407 的 75 格位移全为 0、R409 位移 150–300 g/day」，数字看着像结论。
按「位移为 0 必须先证明扰动进去了」的规矩去核验，反而先发现了 bug：

- 我最初把 D0/D1 写成 `use_chance_constraint=False, epsilon=0`，本意是
  「关掉机会约束、保留硬营养约束」；
- 实际 `solve_chance_modopt` 里营养约束**是经由 z 机制实现的**，关掉它等于**连营养约束一起删掉**
  ——那正是 D2 的定义；
- 结果 D1 解成「成本最小 = 全 0」，D3 恰好贴 box 上界（= 2×baseline），
  于是标签里出现一堆假的 `data-sensitive`（安徽 HEAL_base 的一致率 0.5）。

对照实验（安徽 / HEAL_base）直接暴露：

| 调用 | 解 |
|---|---|
| `use_chance=False, eps=0` | `[0, 0, 0, 0, 0, 0]` ❌ |
| `use_chance=True, epsilon=0` | `[73.79, 298.79, 0, 91.81, 0, 595.07]` ✅（= D3） |

**正确语义**：D0/D1 = `use_chance=True, epsilon=0`；D2 = `use_chance=False`。
`run_b2.py` 一直是对的，是我在 M4 里重新实现 `_solve` 调用时写反了。
三批作废结果（R407/R409/R400 组首批）已删除并重跑。

**教训**：复用求解器时，「关掉某个机制」与「该机制承担的功能」必须分开确认——
这里关掉机会约束，连带删掉的是**全部营养约束**，而脚本不会报错，只会给一个更便宜的解。

### 36.3 正式批次结果（重跑后，有效）

| run | 目录 | 结果 |
|---|---|---|
| R407 | `R407_looro_20261028_183054` | 75 格全解；**6 格翻向**（全在 EAT；省份 安徽/江西/福建，被移除 fold 为 山东/浙江），位移 **339.3–341.7 g/day**，牵动 G04/G06/G07/G08；其余 69 格 `max\|Δq\| = 0` |
| R408 | `R408_delta_20261028_183131` | 45 格可解（9 格 EAT 硬不可行）；δ=±0.5 相对 δ=0 的 `max\|Δq\|` **中位 1.4e-11、最大 2.3e-9**（机器精度） |
| R409 | `R409_bounds_20261028_183421` | 24 格：mid 6 解、high 6 解、**low 6 格 `Status 8: model infeasible`、worst 6 格空盒**；high 相对 mid 位移 **43.7（中位）–92.05（最大）g/day** |
| R400 / R402–R406 | `R400_406_provinces_20261028_183104` | 18 格 15 解（EAT 的 山东/江苏/浙江 硬不可行）；**一致率均值 0.956**；90 个组格 = up 36 / down 49 / neutral 1 / **data-sensitive 4** |

### 36.4 三条结论（可直接进 B4）

1. **价格类扰动不改变决策**：R408（离散度 ±50%）位移 ~1e-9；R407（池化价变 15.7–24.1%）
   仅 EAT 局部翻向，其余 69 格不动。与 §26「顶点稳定半径 ≫ 扰动幅度」同源。
2. **EAT 是唯一不稳的情景**：R400 组的 4 个 `data-sensitive` 全部来自 EAT
   （安徽/江西各 2 个，都是 G07、G08），且 R407 的 6 个翻向格也全部落在 EAT。
   与 §29「EAT 依赖 λ 且无自然取值」一致——**EAT 只能作定性对照，不能进结论门**。
3. **边界变体改变的是可行域本身**：R409 的 low/worst 在 6 省**全部不可行**，
   high 移动 43.7–92.05 g/day。这与前两条不是同一类证据，
   **B4 结论门必须把「稳健性」与「边界可行性」分开报**。

### 36.5 状态与遗留

M4 的十个 run 全部 `DONE`；tracker 合计变为 **36 DONE / 4 DONE-conditional / 0 PARTIAL / 6 TODO**
（剩余 M5）。

遗留两条，都不是本轮引入的：①R409 只覆盖 box，联合约束（`G05+G06 ∈ [40,75]`）未做变体；
②EAT 下山东/江苏/浙江的硬不可行是既有结构问题（冲突集「碳水化合物+硫胺素」）。

---

## 三十七、M5 交付：表与图从原始产物生成，R505 只认「能自动验的那部分」（2026-10-28）

### 37.1 为什么不用 matplotlib

`requirements.txt` 里没有绘图库。为 M5 引入 `matplotlib` 会改依赖、改环境，
而这一层**只是把既有数字摆成表/图**，没有绘图语义上的难点。

所以：**图形直接写 SVG**（纯文本、可 diff、可被脚本校验），数据另存 CSV 供重绘。
`scripts/build_paper_artifacts.py` 不 import 任何新包。

### 37.2 产物（`outputs/R500_504_paper_artifacts`，共 11 个文件）

| run | 文件 | 内容 |
|---|---|---|
| R500 | `table1_price.csv` / `table1_consumption.csv` / `table1.md` | 3 遮蔽 × 4 方法 × 8 指标；只读 `calibration_summary.csv` |
| R501 | `table2_decision.csv` / `table2.md` | 2 口径 × 4 方法 = 8 行；主指标 `dq_change_rate`，附 `feasible_active` |
| R502 | `figure1_stable_flip.csv` / `figure1.svg` | 三情景标签分布：CDG 36 / EAT 18 / HEAL_base 36 = 90 组格 |
| R503 | `figure2_regional_heatmap.csv` / `figure2.svg` | CDG 下 **6 省 × 6 组**方向标签矩阵 |
| R504 | `artifact_manifest.json` / `appendix_index.md` | 每个产物的 bytes + sha256 + 源 run 路径 |

脚本内置三条断言（表 2 必须 8 行、图 1 必须 3 个情景、图 2 必须 6×7），
任一不满足即失败——避免「图悄悄画空了还显示成功」。

**两个必须带进论文的注释已写进表里**：

1. Table 2 的 `feasible_all` 恒为 0 不是 bug，是**钙在 18 个格子全部不可达**的结构事实（§23），
   所以可行性只报 `feasible_active`；
2. `gap` 用逐目标 payoff 归一化，**不可跨价格面板版本比较**（§31.5）。

### 37.3 R505：只认「能自动验的那部分」

`scripts/verify_reproducibility.py` 自动验四件事，全过：

| 项 | 结果 |
|---|---|
| 合同哈希零漂移 | **10/10** 与 `model_manifest.json` 一致 |
| 关键 run 目录完整 | **13 个**全部存在且带 `DONE` |
| unittest | 69 tests OK |
| tracker 校验 | 15 项全绿 |

**「干净环境重跑」没有做，也不假装做了**——它需要仓库外 `git clone` + 新建 venv + 联网装依赖。
报告把它列进 `not_verified`，并生成 `RUNBOOK.md`（逐条命令 + 判据容差：
`dq_ref_change_rate` 同号且 |差| ≤ 1e-6、`feasible_active_rate` 逐位相同、
`direction_agreement_mean` 同号且 |差| ≤ 1e-6）。

### 37.4 顺带修的一个「先有鸡先有蛋」

R505 的 tracker 校验第一次失败，原因是**它自己的输出目录还没被 tracker 收录**。
给 `check_tracker.py` 加了 `--ignore <前缀>` 白名单，只用于「正在生成、尚未登记」的目录，
并在 help 里写明**不得用来掩盖真正的漏登记**；R505 用它排除 `R505_reproducibility` 前缀后通过。
登记完成后，不带宽限的 `check_tracker.py` 仍然是全绿。

### 37.5 状态

46 个预注册 run **全部结案**：**42 DONE / 4 DONE-conditional / 0 PARTIAL / 0 TODO**。

仍待人工的两件（都已在报告里标为未验证）：①干净环境复跑；②R502/R503 的 SVG 人工视觉核对。

---

## 三十八、英文账本与英文图：把「说得对」变成「可被机器核对」（2026-10-28）

### 38.1 背景

外部交付需要一份**英文的 run 账本**。仓库里那份（`EXPERIMENT_TRACKER.md`）是中文的，
且带着 800 行推导叙事；对外交付需要的是「每个 run 一行、状态可查、产物可点」的版本。

同时，M5 的两张图原先用中文标注（`图 1 方向标签分布`、`稳定上升`…），对外不可用。

### 38.2 做了什么

1. **`docs/EXPERIMENT_TRACKER_EN.md`**：46 行英文账本，全部结案
   （**42 DONE / 4 DONE-conditional / 0 PARTIAL / 0 TODO**），含状态与证据等级定义、
   产物索引、五条必须带进论文的陷阱、以及三行自校验命令。
2. **图 1 / 图 2 改为英文标注**：标题、图例、单元格缩写（`UP` / `DOWN` / `FLAT` / `SENS`）
   全部英文；仍是纯 SVG，无新依赖。产物目录随之重建为
   `outputs/R500_504_paper_artifacts`（旧目录已删）。
3. **`check_tracker.py` 支持 `--file`**：中英两版共用同一套 15 项校验，
   小节锚点同时认「进度总览 / Summary」与「产物索引 / Artifact index」。
4. **新增 `scripts/verify_tracker_numbers.py`**：把账本里的关键数字**逐条对回产物**。

### 38.3 为什么单靠 `check_tracker.py` 不够

`check_tracker.py` 只验「结构」——引用能不能解析、目录有没有漏、计数自不自洽。
它**不验数字对不对**：把 `0.460` 写成 `0.640`，它照样全绿。

`verify_tracker_numbers.py` 补上这一层：27 条断言，每条都从
`metrics.json` / CSV 重新算一遍，再要求该字符串**逐字出现**在账本里。覆盖：

| 组 | 断言数 | 例 |
|---|---|---|
| B2 主指标 | 6 | EAR D0/D3 = 0.000、RNI D0 = 0.460、D2 `\|Δq\|` = 128.65 |
| M4 标签 | 8 | 一致率 0.956、up 36 / down 49 / neutral 1 / sens 4、sens 全在 EAT |
| R407/R408/R409 | 8 | 6 格翻向、`2.3e-9`、`low` 6 不可行、`high` 92.05 |
| R401 / 合同 / R505 | 5 | G07 `0/9`、gate 7/7、R505 PASS |

实测 **27/27 PASS**。

### 38.4 过程中修掉的两处不一致（都是校验抓出来的）

1. 中文版 R500–R504 仍指向已删除的旧产物目录（`_183757`），新目录是 `_184742`
   → `check_tracker` 直接报「DONE 行引用的产物不存在」；
2. 英文版只写了 `_150751` 简写，未写完整路径 → 「outputs 目录未被提及」报错。

两处都是**文档漂移**，不是数值错误；但如果没有门禁，它们会一路带到交付版里。

### 38.5 交付

- 仓库：`docs/EXPERIMENT_TRACKER_EN.md`（版本化）
- 外部：同名文件已写回用户指定路径，原件备份为 `EXPERIMENT_TRACKER.orig-2026-10-28.md`
- 图：`figure1.svg` / `figure2.svg`（英文标注，位于 `outputs/R500_504_paper_artifacts/`）

### 38.6 图 1 图例被裁：一个只有「看」才能发现、但可以被「算」拦住的问题

用户看图时发现 **图 1 的图例只显示了一部分**。查下来是几何算错：

```
plot_h = h - 2*pad = 420 - 120 = 300
图例基线 ly = pad + plot_h + 56 = 416      ← 画布高 420
图例方块 y+h = 428，文字基线 426            ← 已经掉到画布外
```

即**图例整体画在了可视区之外**，SVG 本身仍「合法」，XML 校验、文字提取、英文检查全部通过。

修复两件事：

1. 画布改为 `760 × 490`，柱区固定 `plot_h = 300`，图例基线 `ly = 430`（文字 440），
   四行内容（柱 / 情景名 / n= / 图例）都有位置；
2. **新增 `assert_viewbox()`**：写完 SVG 后逐元素解析 `x` / `y` / `width` / `height`，
   任何 `rect` 或 `text` 越出画布就 `AssertionError`，让构建失败而不是产出被裁的图。

**教训**：机器能验「结构合法、文字正确、无中文残留」，验不了「排版是否完整」；
但「元素是否越界」是可以算的——把它算进去，就只剩审美需要人来判断。

---

## 三十九、台账收敛：只保留一份，并把数值门禁从「认措辞」改成「认事实」（2026-10-28）

### 39.1 为什么要删掉英文版

`EXPERIMENT_TRACKER.md` 与 `EXPERIMENT_TRACKER_EN.md` 是同一份 46-run 账本的两种语言版本。
同时维护两份的直接代价已经出现过两次：

1. 图产物目录重建后，**两份都指向已删除的旧路径**，中文版先报错、英文版随后报错；
2. R505 的目录改成确定性路径后，**两份又各自漏改一次**。

同一事实存两处，就一定会漂移。经确认，**只保留中文版**（项目内部引用、推导叙事、
合同口径讨论都在中文版里），英文版删除。

### 39.2 删之前必须先拆掉的依赖

数值门禁 `verify_tracker_numbers.py` 原来是**照着英文措辞**写的 27 条断言
（`"15/18"`、`"6 cells flip"`、`"Contract gates **7/7 PASS**"` …）。直接删英文版会让一半断言失效。

改法：把 `claim()` 的期望参数从「单个字符串」改成「**字符串或字符串元组，命中任一即可**」，
每项同时给出中文与英文表述。这样门禁验的是**事实是否被写进台账**，
而不是「台账用了哪种语言」。

```python
claim("R407 变化格 = 6", int(len(changed)), lambda v: v == 6,
      ("6 cells flip", "6 格翻向", "6 格"))
```

改完后默认目标改为 `docs/EXPERIMENT_TRACKER.md`，实测 **27/27 PASS**。

### 39.3 清理与留痕

| 处理 | 内容 |
|---|---|
| 删除 | `docs/EXPERIMENT_TRACKER_EN.md`（可由 git 历史 `c78e408` 恢复；外部副本仍在交付目录） |
| 同步 | `README.md`、`docs/README.md`、`PROJECT_SUMMARY.md` 的文档地图与命令示例 |
| 保留 | CHANGELOG §38 的原文（它记录的是当时「建了英文版」这一事实，不因后来删除而改写） |

**原则重申**：历史记录不因后续决定而改写；改变写在新的 §，旧 § 保留原貌。
