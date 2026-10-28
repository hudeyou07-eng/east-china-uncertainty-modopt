# RUNBOOK — 干净环境复跑（R505 的人工部分）

以下命令在**仓库外的新目录**执行，用于验证「clone 即可复现」。

```powershell
git clone <repo-url> east-china-repro
cd east-china-repro
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# 1) 测试与文档门禁
python -m unittest discover -s tests -v      # 期望 69 tests OK
python scripts/check_tracker.py              # 期望 15 项全绿

# 2) 合同 gate
python scripts/check_contract_gates.py       # 期望 7/7 PASS

# 3) 选定的 MUST run（按耗时排序，可从长到短取舍）
python run_experiments.py audit --run-id R001_repro_audit
python scripts/run_b2.py --profile formal --bounds-basis ear --run-id REPRO_b2_ear
python scripts/run_m4.py --block provinces --run-id REPRO_m4_provinces

# 4) 比对
#    新批次不与旧批次逐元素比较（时间戳与求解器版本会引入微差），
#    而是比较 metrics.json 里的关键量：
#    - B2: per_method[*].dq_ref_change_rate / feasible_active_rate
#    - M4: direction_agreement_mean / label_counts
```

## 判据

| 项 | 容差 |
|---|---|
| `dq_ref_change_rate` | 与报告值同号且 \|差\| ≤ 1e-6 |
| `feasible_active_rate` | 逐位相同（0/1 比例，无随机性） |
| `direction_agreement_mean` | 同号且 \|差\| ≤ 1e-6 |
| 图/表数值 | 与 `artifact_manifest.json` 的 CSV 逐单元格一致 |

## 本报告已自动验证的部分

- ✅ 合同哈希零漂移（10/10）
- ✅ 关键 run 目录完整（13 个，均带 DONE）
- ✅ unittest 全绿
- ✅ tracker 校验全绿（15 项）

## 未验证

- ⬜ 干净环境重跑（git clone + 新建 venv + pip install -r requirements.txt）—— 本环境无网络/不新建环境，未执行；命令见 RUNBOOK.md
- ⬜ 论文图表的人工视觉核对（R502/R503 的 SVG 需人眼确认可读性）