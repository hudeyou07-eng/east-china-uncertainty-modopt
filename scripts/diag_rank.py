"""诊断 hierarchical_rw 设计矩阵的秩亏问题。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_audit import load_clean_price_panel  # noqa: E402
from src.masking import apply_mask, make_mask  # noqa: E402

cfg = yaml.safe_load((ROOT / "configs" / "default.yaml").read_text(encoding="utf-8"))


def resolve(rel: str) -> Path:
    return (ROOT / "configs" / rel).resolve()


panel = load_clean_price_panel(
    resolve(cfg["paths"]["clean_price_workbook"]),
    float(cfg["audit"]["oil_density_kg_per_litre"]),
    resolve(cfg["paths"]["price_workbook"]),
)
section = cfg["calibration"]
allowed = set(section["training_data_natures"])
excluded = panel["observed"] & ~panel["data_nature"].isin(allowed)
panel.loc[excluded, "value"] = np.nan
panel.loc[excluded, "observed"] = False
panel["truth_eligible"] = panel["observed"]

print("面板:", len(panel), "格 | 可用观测", int(panel["observed"].sum()),
      "| 省", panel["province"].nunique(), "| 品类", panel["group_raw"].nunique(),
      "| 年", panel["year"].nunique())

fold, repeat = 0, 0
mask_type = "consecutive_years"
mask_seed = cfg["project"]["seed"] + fold * 10000 + repeat * 100 + section["mask_types"].index(mask_type)
rng = np.random.default_rng(mask_seed)
mask = make_mask(
    panel, mask_type, rng,
    float(section["point_mask_fraction"]), int(section["block_years"]),
    fold=fold, n_folds=int(section["formal_folds"]),
    fold_seed=cfg["project"]["seed"] + section["mask_types"].index(mask_type) * 1000,
    min_series_observations=int(section["min_series_observations"]),
)
masked = apply_mask(panel, mask)
target = masked.loc[mask, ["province", "group_raw", "year", "target_truth"]]
observed = masked.dropna(subset=["value"])
print("遮蔽后观测", len(observed), "| 待预测", len(target))

provinces = sorted(masked["province"].unique())
groups = sorted(masked["group_raw"].unique())
years = sorted(masked["year"].unique())
p = 1 + len(provinces) + len(groups) + len(years)

x = np.zeros((len(observed), p))
x[:, 0] = 1.0
for i, (_, row) in enumerate(observed.iterrows()):
    x[i, 1 + provinces.index(row["province"])] = 1.0
    x[i, 1 + len(provinces) + groups.index(row["group_raw"])] = 1.0
    x[i, 1 + len(provinces) + len(groups) + years.index(row["year"])] = 1.0

sv = np.linalg.svd(x, compute_uv=False)
rank = np.linalg.matrix_rank(x)
print("\n--- 设计矩阵 ---")
print("形状", x.shape, "| p =", p, "| 秩 =", rank, "| 零空间维数 =", p - rank)
print("奇异值: max %.3e | 次小 %.3e | min %.3e" % (sv[0], sv[-2], sv[-1]))
print("条件数 %.3e" % (sv[0] / sv[-1]))
for name, sl in [("省", slice(1, 1 + len(provinces))),
                 ("组", slice(1 + len(provinces), 1 + len(provinces) + len(groups))),
                 ("年", slice(1 + len(provinces) + len(groups), p))]:
    print(f"  {name}哑变量每行之和恒为1: {np.allclose(x[:, sl].sum(axis=1), 1.0)}")

y = np.log(observed["value"].to_numpy(float))
for ridge, yrw in [(1.0, 4.0), (1.0, 0.5), (10.0, 4.0)]:
    precision = np.eye(p) * 1e-6
    precision[1:1 + len(provinces), 1:1 + len(provinces)] += np.eye(len(provinces)) * ridge
    g0 = 1 + len(provinces)
    precision[g0:g0 + len(groups), g0:g0 + len(groups)] += np.eye(len(groups)) * ridge
    y0 = 1 + len(provinces) + len(groups)
    diff = np.zeros((max(len(years) - 1, 0), len(years)))
    for i in range(len(years) - 1):
        diff[i, i], diff[i, i + 1] = -1.0, 1.0
    if len(diff):
        precision[y0:, y0:] += yrw * (diff.T @ diff)
    system = x.T @ x + precision
    ev = np.linalg.eigvalsh(system)
    print(f"\nridge={ridge} year_rw={yrw}: 最小特征值 {ev[0]:.3e} -> 该方向后验标准差放大 {np.sqrt(1.0/ev[0]):.0f} 倍")
