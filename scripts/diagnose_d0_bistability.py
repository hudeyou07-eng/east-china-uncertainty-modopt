"""D0 的二值开关诊断：D0 的解在两个顶点之间跳，不是连续响应。

背景（CHANGELOG §31.8）
------------------------
`R200_203` 的 D0 用「跨省池化价格」（`price_mode="pooled"`，模拟遮蔽后省份信息
丢失）。池化价格含该协议单元自己的位移，所以逐单元不同。实测：

* **RNI 下** D0 的 `q_G08` 在每个省**只有 2 个取值**，间距是 6 个固定常数
  （29.03 / 36.41 / 48.99 / 54.00 / 74.87 / 110.97）。价格面板修正 2–14% 后，
  多数侧整体从低顶点翻到高顶点，于是「D0≠D1 的省份集合」整套换掉
  （旧：安徽/山东/浙江 → 新：江苏/江西/福建）。
* **EAR 下** D0 的 `q_G08` 每省只有 **1 个取值**，且新旧面板完全相同。

结论：`dq_ref_change_rate(D0)` 是「落在少数侧的单元比例」，不是「不可靠单元比例」；
「哪 3 个省 D0≠D1」是开关读数，不能当结论引用。

用法
----
    python scripts/diagnose_d0_bistability.py
    python scripts/diagnose_d0_bistability.py --runs <run1> <run2> ...

不指定 ``--runs`` 时自动扫描 ``outputs/R200_203_b2_formal_*``（含 ``config.json`` 的）。
纯读 CSV，不求解。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.io_utils import create_run_dir, write_json  # noqa: E402

QCOLS = ["q_G02", "q_G04", "q_G05", "q_G06", "q_G07", "q_G08"]
IDX = ["province", "fold", "repeat", "cell"]
PROVINCES = ["安徽", "山东", "江苏", "江西", "浙江", "福建"]


def _load(run_dir: Path) -> tuple[pd.DataFrame, dict]:
    cfg = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    df = pd.read_csv(run_dir / "b2_results.csv", encoding="utf-8-sig")
    return df, cfg


def _switch_table(df: pd.DataFrame, tag: str) -> list[dict]:
    """逐省统计 D0 的取值个数、两取值间距、多数侧占比，以及 D1 落在哪一侧。"""
    d0 = df[df["method"].eq("D0")]
    d1 = df[df["method"].eq("D1")]
    rows: list[dict] = []
    for prov in PROVINCES:
        sub = d0[d0["province"].eq(prov)]
        if not len(sub):
            continue
        v = sub["q_G08"].round(2)
        counts = v.value_counts()
        vals = sorted(counts.index)
        # D1 在同一省也可能有 2 个取值（RNI 下安徽/山东/浙江实测 97/3），
        # 所以不能假定它恒定——把它的取值数与多数侧占比一起记下来。
        d1v = d1[d1["province"].eq(prov)]["q_G08"].round(2)
        d1_counts = d1v.value_counts()
        d1_vals = sorted(d1_counts.index)
        majority = counts.idxmax()
        rows.append({
            "run": tag,
            "province": prov,
            "n_distinct": int(len(vals)),
            "low": float(vals[0]),
            "high": float(vals[-1]),
            "gap": float(vals[-1] - vals[0]),
            "majority_share": float(counts.max() / len(v)),
            "d1_low": float(d1_vals[0]),
            "d1_high": float(d1_vals[-1]),
            "d1_n_distinct": int(len(d1_vals)),
            "d1_majority_share": float(d1_counts.max() / len(d1v)),
            "d0_majority_on_d1": bool(abs(majority - d1_counts.idxmax()) < 1.0),
        })
    return rows


def _dq_ref_rate(df: pd.DataFrame) -> dict[str, float]:
    """各方法的 dq_ref 变化率（位移超过 1e-6 的单元占比）。"""
    out = {}
    for m, sub in df.groupby("method"):
        col = sub["max_abs_dq_ref"]
        out[str(m)] = float((col > 1e-6).mean())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="*", default=None)
    ap.add_argument("--run-id", default="DIAG_d0_bistability")
    args = ap.parse_args()

    if args.runs:
        run_dirs = [ROOT / r if not Path(r).is_absolute() else Path(r) for r in args.runs]
    else:
        run_dirs = sorted(
            p for p in (ROOT / "outputs").glob("R200_203_b2_formal_*")
            if (p / "config.json").exists() and (p / "b2_results.csv").exists()
        )
    if not run_dirs:
        print("没有可用的批次", file=sys.stderr)
        return 1

    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    rows: list[dict] = []
    meta: list[dict] = []
    rates: list[dict] = []
    for d in run_dirs:
        df, cfg = _load(d)
        tag = d.name
        rows.extend(_switch_table(df, tag))
        rate = _dq_ref_rate(df)
        rates.append({"run": tag, **rate})
        meta.append({
            "run": tag,
            "bounds_basis": cfg.get("bounds_basis"),
            "group_prices_sha256": (cfg.get("contract_hashes") or {}).get("group_prices.csv"),
            "n_rows": int(len(df)),
            "repeats": cfg.get("repeats"),
        })

    sw = pd.DataFrame(rows)
    sw.to_csv(run_dir / "d0_switch_by_province.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(rates).to_csv(run_dir / "dq_ref_change_rate.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(meta).to_csv(run_dir / "runs.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 220)
    print("=== 批次 ===")
    print(pd.DataFrame(meta).to_string(index=False))
    print()
    print("=== D0 的 q_G08 逐省开关状态 ===")
    print(sw.to_string(index=False))
    print()
    print("=== dq_ref 变化率 ===")
    print(pd.DataFrame(rates).to_string(index=False))

    # ---- 判定 ----
    # 逐批次汇总。**不能按口径合并**：合并后 d0_ne_d1 会变成所有批次的并集，
    # 而这里的核心结论恰恰是「不同批次的省份集合不同」。
    basis_of = {m["run"]: m["bounds_basis"] for m in meta}
    per_run: dict[str, dict] = {}
    for run, sub in sw.groupby("run"):
        per_run[run] = {
            "bounds_basis": basis_of[run],
            "d0_distinct_values": sorted(set(int(x) for x in sub["n_distinct"])),
            "d1_distinct_values": sorted(set(int(x) for x in sub["d1_n_distinct"])),
            "gaps": sorted(set(round(float(x), 2) for x in sub["gap"] if x > 1e-9)),
            "d0_majority_share": {r.province: round(float(r.majority_share), 2)
                                  for r in sub.itertuples()},
            "d0_ne_d1": sorted(set(sub.loc[sub["d0_majority_on_d1"].eq(False), "province"])),
        }
    # 跨批次不变性：同一口径下，D0 的取值个数与间距是否一致
    stability: dict[str, object] = {}
    for basis, sub in sw.groupby(sw["run"].map(basis_of)):
        stability[f"{basis}_d0_distinct_values"] = sorted(set(int(x) for x in sub["n_distinct"]))
        stability[f"{basis}_gaps"] = sorted(set(round(float(x), 2) for x in sub["gap"] if x > 1e-9))
        sets = {
            run: tuple(sorted(set(s.loc[s["d0_majority_on_d1"].eq(False), "province"])))
            for run, s in sub.groupby("run")
        }
        stability[f"{basis}_d0_ne_d1_sets"] = sorted(set(sets.values()))
    summary: dict[str, object] = {
        "n_runs": len(run_dirs),
        "per_run": per_run,
        "stability": stability,
    }
    write_json(run_dir / "metrics.json", {
        "evidence_status": "structural",
        "note": (
            "纯读 CSV，不求解。evidence_status=structural：结论依赖既有批次产物，"
            "本脚本不重跑 B2。per_run.d0_distinct_values 是 D0 的 q_G08 在 100 个协议"
            "单元里的取值个数（1=稳定，2=二值开关）；per_run.gaps 是两取值间距。"
            "stability.<basis>_d0_ne_d1_sets 列出该口径下各批次给出的「D0≠D1 省份集合」"
            "去重后的结果——**若多于 1 个集合，说明省份名单不稳定，不能引用具体名单**。"
        ),
        **summary,
    })
    (run_dir / "DONE").write_text("ok\n", encoding="utf-8")
    print()
    print(f"[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
