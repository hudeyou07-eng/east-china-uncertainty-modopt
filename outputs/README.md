# Generated outputs

Formal and smoke runs create timestamped folders here. A run is complete only when it contains `metrics.json`, `config.json`, `environment.json`, and `DONE`. Failed runs retain `FAILED.json` and traceback information.

**These folders are versioned as of 2026-10-28** (44 directories, ~9 MB) so that collaborators can
audit the paper numbers without re-running ~1.5 h of experiments. Two directories are exempt from the
timestamp convention because they are gate deliverables that get regenerated: `R500_504_paper_artifacts`
and `R505_reproducibility` (both created with `--exact`).

Small reviewed evidence suitable for version control belongs in `artifacts/`, not here.

## 现存目录约定（2026-10-28 清理后）

当前只保留 **36 个目录**，分三类，**每一类都对应文档中的引用**：

| 类别 | 例 | 说明 |
|---|---|---|
| 主批次（每项只有一个） | `B1_formal_withmice_20261023_124906`、`R103_105_consumption_formal_20261026_174725`、`R108_109_price_formal_20261026_175443` | B1 三个面板各一个合并后目录 |
| 当前应引用的 B2 批次 | `R200_203_b2_formal_20261027_222841`（EAR）/ `_224315`（RNI） | 见 `docs/PANEL_LEDGER.md` |
| 结构诊断 `DIAG_*` | `DIAG_d0_bistability_20261027_231703` | 一律 `evidence_status: structural` |

## 已清理的内容

2026-10-28 清理了 **163 个目录 / 1630 个文件 / 17.9 MB**，明细与逐条理由见
`docs/CLEANUP_2026-10-28.md` 与 `outputs/_cleanup_deleted.csv`（本目录，git 忽略）。

清理只删「被取代 / 不完整 / 并行分片 / 重复 smoke / 空目录」，**没有删除任何当前被
`docs/EXPERIMENT_TRACKER.md` 结论所依赖的 run**。若文档正文仍出现已删目录名，
那是**历史过程的记录**（如「`_174710` → `_222841` 逐元素 diff 全 0」），
不是当前证据来源；`docs/CLEANUP_2026-10-28.md` 的对照表给出每一个已删目录的替代者。
