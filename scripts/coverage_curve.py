"""R106：由既有运行的逐格预测重算 coverage–width 曲线。

为什么不重跑：``cell_predictions.csv`` 已经存了每个被遮蔽格的
``truth / prediction / lower95 / upper95``，足以反推等效正态 SD 并计算
任意名义水平的覆盖率。重跑 5×20 的 MICE 要二十分钟，只为多两列，不划算。

同时把 ``calibration_error``（四个名义水平上 |经验覆盖率 − 名义水平| 的均值）
与 ``coverage_slope``（0.50→0.95 的斜率，理想值 1.0）算出来。
斜率 < 1 表示区间偏宽（过度保守），> 1 表示偏窄（过度自信）。

用法：
    python scripts/coverage_curve.py outputs/B1_formal_withmice_20261023_124906
    python scripts/coverage_curve.py <run_dir> --by-fold
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Z = {0.50: 0.6744897502, 0.80: 1.2815515655, 0.90: 1.6448536270, 0.95: 1.9599639845}
LEVELS = tuple(Z)


def _coverage(frame: pd.DataFrame, level: float) -> float:
    sd = (frame["upper95"] - frame["lower95"]) / (2.0 * Z[0.95])
    half = Z[level] * sd
    return float(np.mean((frame["truth"] >= frame["prediction"] - half) & (frame["truth"] <= frame["prediction"] + half)))


def summarise(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    rows = []
    for key, block in frame.groupby(keys):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(keys, key))
        row["n_eval"] = int(len(block))
        sd = float(np.mean((block["upper95"] - block["lower95"]) / (2.0 * Z[0.95])))
        errors = []
        for level in LEVELS:
            cov = _coverage(block, level)
            row[f"nominal_{int(level * 100)}"] = level
            row[f"coverage_{int(level * 100)}"] = cov
            row[f"width_{int(level * 100)}"] = 2.0 * Z[level] * sd
            errors.append(abs(cov - level))
        row["calibration_error"] = float(np.mean(errors))
        row["coverage_slope"] = (row["coverage_95"] - row["coverage_50"]) / (0.95 - 0.50)
        row["scaled_mae"] = float(
            np.mean(np.abs(block["prediction"] - block["truth"])) / max(float(np.mean(np.abs(block["truth"]))), 1e-8)
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(keys).reset_index(drop=True)


def to_curve(summary: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    rows = []
    for _, row in summary.iterrows():
        for level in (50, 80, 90, 95):
            rows.append(
                {
                    **{k: row[k] for k in keys},
                    "nominal": level / 100.0,
                    "empirical_coverage": row[f"coverage_{level}"],
                    "mean_width": row[f"width_{level}"],
                    "gap": row[f"coverage_{level}"] - level / 100.0,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="R106 coverage-width curve from cell_predictions.csv")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--by-fold", action="store_true", help="同时输出逐折汇总（给误差棒用）")
    args = parser.parse_args()

    path = args.run_dir / "cell_predictions.csv"
    if not path.exists():
        raise SystemExit(f"缺 {path}，该运行未保存逐格预测，无法事后重算")
    frame = pd.read_csv(path, encoding="utf-8-sig")
    required = {"truth", "prediction", "lower95", "upper95", "mask_type", "method"}
    missing = required - set(frame.columns)
    if missing:
        raise SystemExit(f"cell_predictions.csv 缺列 {sorted(missing)}")
    if not np.isfinite(frame[["truth", "prediction", "lower95", "upper95"]].to_numpy(float)).all():
        raise SystemExit("逐格预测含非有限值，拒绝计算")

    keys = ["mask_type", "method"]
    summary = summarise(frame, keys)
    summary.to_csv(args.run_dir / "coverage_curve_summary.csv", index=False, encoding="utf-8-sig")
    to_curve(summary, keys).to_csv(args.run_dir / "coverage_curve.csv", index=False, encoding="utf-8-sig")

    print(f"[R106] {args.run_dir.name} | 逐格 {len(frame)} 行")
    show = summary[keys + ["n_eval", "scaled_mae", "coverage_50", "coverage_80", "coverage_90",
                           "coverage_95", "calibration_error", "coverage_slope"]]
    print(show.round(3).to_string(index=False))

    payload = {
        "run_dir": str(args.run_dir),
        "n_cells": int(len(frame)),
        "levels": list(LEVELS),
        "per_mask_method": summary.to_dict("records"),
        "method": "effective normal SD from (upper95-lower95)/(2*z95)",
        "caveat": "对数正态类方法的区间不对称，50% 附近为近似值",
    }

    if args.by_fold:
        fold_summary = summarise(frame, ["mask_type", "method", "fold"])
        fold_summary.to_csv(args.run_dir / "coverage_curve_by_fold.csv", index=False, encoding="utf-8-sig")
        spread = (
            fold_summary.groupby(keys)
            .agg(
                ce_mean=("calibration_error", "mean"),
                ce_sd=("calibration_error", "std"),
                slope_mean=("coverage_slope", "mean"),
                slope_sd=("coverage_slope", "std"),
            )
            .round(4)
        )
        print("\n逐折离散（5 折）:")
        print(spread.to_string())
        payload["by_fold"] = spread.reset_index().to_dict("records")

    (args.run_dir / "coverage_curve.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[written] coverage_curve.csv / coverage_curve_summary.csv / coverage_curve.json")


if __name__ == "__main__":
    main()
