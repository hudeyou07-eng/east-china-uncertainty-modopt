# docs/ 目录说明

> 面向共创者的文档入口。**先读 `PROJECT_SUMMARY.md`**，它是全部重要改动的汇总。

## 常读（根目录）

| 文件 | 作用 | 何时更新 |
|---|---|---|
| `PROJECT_SUMMARY.md` | **唯一入口**：结论、关键决定、限制、复现、变更大事记 | 有新结论或新决定时 |
| `EXPERIMENT_PLAN.md` | 预注册方案、claim map、四条修订留痕（R-2026-10-26-a/b、R-2026-10-28-c/d） | 只在预注册变更时 |
| `EXPERIMENT_TRACKER.md` | 逐 run 台账（**唯一版本**，含推导叙事与产物索引） | 每跑完一个 run |
| `PANEL_LEDGER.md` | 价格面板 v1/v2/v3 版本台账（引用成本数字前必查） | 面板重建时 |
| `CHANGELOG_2026-10-26.md` | **逐轮证据链**（§1–§38），被正文以 § 号引用 | 每轮工作后追加一节 |
| `Research_Proposal.docx` | 中英文研究计划书 | 少变 |

## archive/（历史留痕，不再更新）

| 文件 | 内容 | 为什么保留 |
|---|---|---|
| `AUDIT_2026-10-26.md` | 全项目审计（P0/P1/P2 分级） | P2 级技术债仍需追踪 |
| `DECISIONS_2026-10-27.md` | 11 处自我更正与口径裁定 | 记录「当初为什么改」，防止回退 |
| `CLEANUP_2026-10-28.md` | 163 个中间目录的清理台账 | 提供被删目录与替代者的对照 |
| `TO_DECIDE.md` | 五条决定的执行状态（已全部结案） | 决策留痕 |

> **归档不等于失效**：正文里仍以原文件名引用这些文档（例如「见 `TO_DECIDE.md` 第二节」），
> 读到就去 `archive/` 找。文件名不变，是为了让 4000 行 CHANGELOG 的历史引用继续可解析。

## 校验（改完文档必跑）

```powershell
python scripts/check_tracker.py                    # 台账结构（15 项）
python scripts/verify_tracker_numbers.py           # 27 条数值断言（对回产物）
python -m unittest discover -s tests               # 69 tests
python scripts/verify_reproducibility.py --exact   # 哈希/目录/门禁
```

## 写作约定

1. **数字必须可回算**：正文里出现的每个关键数字，都要能和某个 `outputs/` 产物或
   `data/processed/` 文件对得上；对不上就写「未验证」。
2. **不覆盖历史**：预注册变更写进 `EXPERIMENT_PLAN.md` 的修订记录，不修改原条款。
3. **零结果也要先证伪**：位移为 0 的敏感性，必须先证明扰动改变过输入（见 CHANGELOG §36.2）。
4. **图不用 matplotlib**：本仓库图形是手写 SVG，保证无新依赖、可 diff、可被脚本验越界。
