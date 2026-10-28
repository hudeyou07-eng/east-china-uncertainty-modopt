# 价格面板版本台账（`data/processed/group_prices.csv`）

面板在 2026-10-27 一天内改过两次，**两次的性质完全不同**：一次改价格数值，一次只改元数据。
不记下来的话，「批次记录的 hash 与磁盘不一致」会被误读成「结果不可复现」。

| 版本 | sha256（前 16 位） | G06 均值 | `truth_eligible=True` | 改了什么 | 数值影响 |
|---|---|---|---|---|---|
| **v1 原始** | `54f7fee0ce3898ce` | 43.92 | 242 | — | 基准 |
| **v2 G06 修完** | `eadc85e6af57c421` | 47.03 | 242 | G06 部分结构改为「缺品类先桥接补全」 | **21 行涨价 +1.95%~+36.57%（中位 +25.05%）**；决策列变 9.8e-08 g/day |
| **v3 当前** | `3b7ae42d9fbc0fc9` | 47.03 | **219** | `truth_eligible` 判据改为「全部品类实测」 | **价格 0 行变化**（`max\|diff\| = 0.000e+00`）；23 行 True→False |

备份：`artifacts/group_prices_before_g06fix.csv`（v1）、`artifacts/group_prices_before_te_fix.csv`（v2）。

## 各批次实际用的是哪一版

| 批次 | 记录的 `group_prices.csv` hash | 对应版本 |
|---|---|---|
| `R200_203_b2_formal_20261027_174710` / `_174714` | `54f7fee0…` | **v1** |
| `R200_203_b2_formal_20261027_222841` / `_224315` | `eadc85e6…` | **v2** |
| 当前磁盘 | `3b7ae42d…` | **v3** |

> **2026-10-28 清理**：`_174710` / `_174714`（v1 批次）目录已删除，原因见
> `docs/archive/CLEANUP_2026-10-28.md` B 组。本表保留这两行，因为它的用途正是
> "某个已不存在的批次当时用的是哪版面板"；删除后本表成为**唯一**记录。

## v2 → v3 为什么不重跑 B2

1. **价格列逐元素相同**（756 行合并比对，`price_cny_kg` 与 `price_cny_kg_full` 的 `max|diff|` 均为 `0.000e+00`）；
2. `Contract.price_panel()` **不读** `truth_eligible`，只做 `groupby([...])["price_cny_kg"].mean()`；
3. 遮蔽协议读的是消费面板（`group_audit.csv`，键为 `province/group_raw/year`），
   该文件**没有 `truth_eligible` 列**，`make_mask()` 走 `panel["observed"]` 分支——本次改动碰不到它；
4. 合同重建后只有 3 个文件变：`group_prices.csv`、`model_manifest.json`、`contract_gate_report.json`；
   `group_audit*`、`nutrient_*` 等 34 个产物**逐字节不变**。

结论：**v2 与 v3 在数值上是同一个面板**，`R200_203_b2_formal_20261027_222841` / `_224315` 继续有效。
引用这两个批次时，若被问「hash 与磁盘不一致」，答案是「差在 `truth_eligible` 元数据列，价格未变」。

## 引用规则

- 论文报成本绝对水平 → 必须写 **v2/v3**（G06 已修正）。用 v1 的数字会低 0.2%–2.6%；
- 论文报「真值可用格数」→ 必须写 **v3**（219 vs 242）；
- 任何跨批次比较 gap → 见 CHANGELOG §31.5，**`objective_gap` 不可跨面板版本比较**。
