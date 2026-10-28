"""把 B2 的决策位移按 (省, 方法) 拆开，产出论文可用的表格。

## 为什么需要这个脚本

`run_b2.py` 的 `metrics.json` 只给**全样本**的 `dq_ref_*`。
但决策位移是**分省**的：RNI 口径下安徽 49 g/day、山东 111 g/day、江苏 0，
合并成一个均值会把「3 个省在动、3 个省不动」抹平成「平均 26 g/day」，
读者无法判断差异来自哪里。

本脚本从 `b2_results.csv` 重建分省表，并额外给：

* `dq_ref_median` / `dq_ref_p95` / `dq_ref_max`：位移的量级；
* `change_rate`：`max|Δq| > 1 g/day` 的单元占比（与 `flip_rate` 同量纲，
  但不会漏掉「方向不变、幅度很大」）；
* `flip_rate`：符号翻转率，**保留但降为辅助**（CHANGELOG §26.8 裁定 4）；
* `n_unique_solutions`：该省该方法的唯一解个数——用来判断
  「是稳定地偏离，还是在两个顶点间摇摆」。这两个含义完全不同。

## 用法

    python scripts/summarize_dq.py outputs/R200_203_b2_formal_<id>
    python scripts/summarize_dq.py <run_a> <run_b> --label EAR RNI

输出：终端表格 + `<run_dir>/dq_by_province.csv`。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DQ_CHANGE_TOL = 1.0  # g/day，与 src.b2_evaluate.DQ_CHANGE_TOL 一致
SIG_TOL = 1e-3  # g/day（1 mg），解签名聚类容差；远低于任何决策相关量级


def _n_unique(qmat: np.ndarray, tol: float = SIG_TOL) -> int:
    """按容差聚类数唯一解个数。

    **不能用字符串舍入**：实测 EAR/安徽/D3 的两个解差 **7.3e-9 g/day**
    （纯浮点噪声），但恰好卡在 6 位小数的边界上，round 后变成两个不同字符串，
    虚报成「2 个唯一解」。容差聚类把这种噪声合并掉。

    贪心实现：按字典序排序后，与**当前簇的代表行**比较，超过 tol 即开新簇。
    对本问题的数据（簇间差 ≥ 1 g/day、簇内噪声 ≤ 1e-8）足够；
    若将来出现「链式近似」的情形需换成完整聚类。
    """
    if qmat.size == 0:
        return 0
    order = np.lexsort(qmat.T[::-1])
    ordered = qmat[order]
    n = 1
    ref = ordered[0]
    for row in ordered[1:]:
        if np.max(np.abs(row - ref)) > tol:
            n += 1
            ref = row
    return n


def _q_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("q_")]


def summarize_run(run_dir: Path, label: str | None = None) -> pd.DataFrame:
    path = run_dir / "b2_results.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} 不存在——该 run 可能没跑完")
    df = pd.read_csv(path, encoding="utf-8-sig")
    qcols = _q_columns(df)
    if not qcols:
        raise ValueError("b2_results.csv 里没有 q_* 列")

    # 解签名改用容差聚类（见 _n_unique 的注释：字符串舍入会把浮点噪声当成不同解）
    rows: list[dict] = []
    for (province, method), sub in df.groupby(["province", "method"], sort=True):
        dq = sub["max_abs_dq_ref"].to_numpy(dtype=float)
        dq = dq[np.isfinite(dq)]
        rows.append(
            {
                "label": label or run_dir.name,
                "province": province,
                "method": method,
                "n": int(len(sub)),
                "dq_ref_median": float(np.median(dq)) if dq.size else float("nan"),
                "dq_ref_p95": float(np.percentile(dq, 95)) if dq.size else float("nan"),
                "dq_ref_max": float(dq.max()) if dq.size else float("nan"),
                "change_rate": float((dq > DQ_CHANGE_TOL).mean()) if dq.size else float("nan"),
                "flip_rate": float(sub["flips"].sum() / sub["n_groups"].sum())
                if sub["n_groups"].sum()
                else float("nan"),
                "gap_median": float(sub["objective_gap"].median()),
                "n_unique_solutions": _n_unique(sub[qcols].to_numpy(dtype=float)),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dirs", nargs="+", type=Path)
    ap.add_argument("--label", nargs="*", default=None, help="与 run_dirs 一一对应的标签")
    ap.add_argument("--no-write", action="store_true", help="只打印，不写 CSV")
    args = ap.parse_args()

    labels = args.label or [None] * len(args.run_dirs)
    if len(labels) != len(args.run_dirs):
        ap.error("--label 个数必须与 run_dirs 相同")

    frames = [summarize_run(d, lb) for d, lb in zip(args.run_dirs, labels)]
    out = pd.concat(frames, ignore_index=True)

    pd.set_option("display.width", 240)
    pd.set_option("display.max_rows", 200)
    print("=== 决策位移（|Δq| 相对该省真值参考解，g/day）===")
    print(
        out[
            ["label", "province", "method", "dq_ref_median", "dq_ref_p95",
             "change_rate", "flip_rate", "n_unique_solutions"]
        ].round(3).to_string(index=False)
    )

    print("\n=== 主指标排序（按 dq_ref_median 降序，只看 >0 的省）===")
    moved = out[out["dq_ref_median"] > DQ_CHANGE_TOL]
    if moved.empty:
        print("  没有任何 (省, 方法) 的位移中位数超过 1 g/day")
    else:
        print(
            moved.sort_values("dq_ref_median", ascending=False)[
                ["label", "province", "method", "dq_ref_median", "change_rate", "flip_rate"]
            ].round(3).to_string(index=False)
        )

    if not args.no_write:
        for d, f in zip(args.run_dirs, frames):
            target = d / "dq_by_province.csv"
            f.to_csv(target, index=False, encoding="utf-8-sig")
            print(f"\n[写出] {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
