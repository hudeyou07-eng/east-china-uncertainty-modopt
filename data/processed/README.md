# `data/processed/` 文件说明

本目录混放了两类文件，**命名有重叠，取用前务必确认属于哪一类**。

## 一、当前合同产物（B2 冻结，11 个）

由一条命令重建：

```bash
python scripts/build_contract_files.py
```

| 文件 | 内容 | 行/大小 |
|---|---|---|
| `group_audit.csv` | 组级四域审计，**主口径 K=4**（G02/G05/G06/G08） | 12 行 × 23 列 |
| `group_audit_k3_strict.csv` | 预注册原口径 K=3（痕量不算有效观测） | 12 行 |
| `group_audit_sensitivity_c0.90.csv` | 敏感性口径 K=6（营养格覆盖率 ≥0.90） | 12 行 |
| `baseline_consumption.csv` | 基线摄入量，7 省 × 10 组 × 9 年 | 630 行 |
| `group_prices.csv` | 组级价格，G06 按消费结构加权 | 756 行 |
| `nutrients.csv` | 组级营养系数，12 组 × 11 硬营养素 | 132 行 |
| `environment.csv` | 环境系数，双数据集（global_pn 主 / china_lca 对照） | 82 行 |
| `decision_bounds.csv` | 决策边界，单组 252 + 联合 7 | 259 行 |
| `ontology.csv` | 本体，`group_audit.csv` 的生成依据 | 12 行 |
| `model_manifest.json` | 全部产物 hash + 9 个输入 hash + 口径声明 | 473 行 |
| `contract_gate_report.json` | Plan §3 七条 gate 的实测结果 | — |

## 二、历史阈值扫描产物（27 个，**不是当前口径**）

形如 `group_audit_{notrace,trace}_c{0.80,0.85,0.90,0.95,1.0}.csv`、
`group_audit_{relax,relax_map,chk,baseline_check}.csv`，以及配套的
`group_audit_summary_*.json`（共 13 个 summary）。

来源：早期用 `python scripts/build_group_audit.py --suffix <名字> --min-cell-coverage <值>`
做的阈值敏感性扫描，用于确认「纳入组数完全由营养覆盖率阈值决定」这一结论。

**已核实**：随机抽两个变体（`_notrace_c0.80`、`_trace_c0.90`）用当前脚本重算，
`include` 决策与磁盘文件**完全一致**（都是 G02/G04/G05/G06/G07/G08）。
差异只在 schema：旧文件 18 或 22 列，当前 23 列（新增 mapping 审计列与 `baseline_source`）。

**使用限制**：

- 可引用其 `include` 列，作为阈值敏感性的证据；
- **不要**引用旧文件的列级字段（`mapping_missing_items` 等），列定义已变；
- **不要**把其中任何一个当作当前合同产物。当前口径只有上表 11 个文件。

## 三、`group_audit_summary.json` 属于哪类

属于**当前**产物——`build_group_audit.py` 在主口径下会写它。
带后缀的 `group_audit_summary_<名字>.json` 才属于历史扫描。

## 四、已知的命名陷阱

`group_audit.csv` 与 `group_audit_relax.csv` / `group_audit_chk.csv` 等**只差一个后缀**，
审阅时极易误取。若在论文或报告里引用审计表，请确认路径是 `group_audit.csv`
（无后缀）且列数为 23。
