"""交互项启用条件的调参与留出验证。

选择准则：三种掩码的尺度化误差相对默认值的平均比值最小（等权，避免只优化年块）。
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_audit import load_clean_price_panel  # noqa: E402
from src.imputation import hierarchical_rw_predict  # noqa: E402
from src.masking import apply_mask, make_mask  # noqa: E402

ARCHIVE = ROOT / "outputs" / "B1_formal_withmice_20261023_124906"
OUT = ROOT / "outputs" / "B1_interaction_sweep_20261023_141000"
OUT.mkdir(parents=True, exist_ok=True)

cfg = yaml.safe_load((ROOT / "configs" / "default.yaml").read_text(encoding="utf-8"))
section = cfg["calibration"]
seed = int(cfg["project"]["seed"])
mask_types = list(section["mask_types"])
n_folds = int(section["formal_folds"])


def resolve(rel: str) -> Path:
    return (ROOT / "configs" / rel).resolve()


panel = load_clean_price_panel(
    resolve(cfg["paths"]["clean_price_workbook"]),
    float(cfg["audit"]["oil_density_kg_per_litre"]),
    resolve(cfg["paths"]["price_workbook"]),
)
allowed = set(section["training_data_natures"])
excluded = panel["observed"] & ~panel["data_nature"].isin(allowed)
panel.loc[excluded, "value"] = np.nan
panel.loc[excluded, "observed"] = False
panel["truth_eligible"] = panel["observed"]

archived = pd.read_csv(ARCHIVE / "cell_predictions.csv")
archived_rw = archived[archived["method"] == "hierarchical_rw"]
mice_all = archived[archived["method"] == "mice"]


def blocks(repeats):
    for fold in range(n_folds):
        for repeat in repeats:
            for mt in mask_types:
                mask_seed = seed + fold * 10000 + repeat * 100 + mask_types.index(mt)
                rng = np.random.default_rng(mask_seed)
                mask = make_mask(
                    panel, mt, rng,
                    float(section["point_mask_fraction"]), int(section["block_years"]),
                    fold=fold, n_folds=n_folds,
                    fold_seed=seed + mask_types.index(mt) * 1000,
                    min_series_observations=int(section["min_series_observations"]),
                )
                masked = apply_mask(panel, mask)
                target = masked.loc[mask, ["province", "group_raw", "year", "target_truth"]].copy()
                yield fold, repeat, mt, masked, target


# ---------- 回归校验 ----------
print("=" * 72)
print("1) 回归校验")
worst = 0.0
for fold, repeat, mt, masked, target in blocks(range(3)):
    pred = hierarchical_rw_predict(masked, target)
    ref = archived_rw[(archived_rw.fold == fold) & (archived_rw.repeat == repeat)
                      & (archived_rw.mask_type == mt)].set_index(
        ["province", "group_raw", "year"])
    for i, (_, row) in enumerate(target.iterrows()):
        key = (row["province"], row["group_raw"], int(row["year"]))
        if key in ref.index:
            worst = max(worst, abs(pred.mean[i] - float(ref.loc[key, "prediction"])))
print(f"   默认参数与存档最大绝对差 = {worst:.3e}",
      "（逐位复现）" if worst < 1e-9 else "（不一致！）")

# ---------- 调参 ----------
CONFIGS = {"default": {}}
for ir, k in itertools.product([1.0, 10.0], [1, 2, 3, 4, 5, 6]):
    CONFIGS[f"ir{ir:g}_k{k}"] = {"interaction_ridge": ir, "interaction_min_observations": k}


def evaluate(repeats, configs):
    rows = []
    for fold, repeat, mt, masked, target in blocks(repeats):
        truth = target["target_truth"].to_numpy(float)
        keys = list(zip(target["province"], target["group_raw"], target["year"].astype(int)))
        m = mice_all[(mice_all.fold == fold) & (mice_all.repeat == repeat)
                     & (mice_all.mask_type == mt)].set_index(
            ["province", "group_raw", "year"]).reindex(keys)
        for name, kwargs in configs.items():
            pred = hierarchical_rw_predict(masked, target, **kwargs)
            for i, k in enumerate(keys):
                rows.append({
                    "config": name, "fold": fold, "repeat": repeat, "mask_type": mt,
                    "province": k[0], "group_raw": k[1], "year": k[2], "truth": truth[i],
                    "prediction": float(pred.mean[i]),
                    "lower95": float(pred.lower95[i]), "upper95": float(pred.upper95[i]),
                })
        for i, k in enumerate(keys):
            rows.append({
                "config": "mice", "fold": fold, "repeat": repeat, "mask_type": mt,
                "province": k[0], "group_raw": k[1], "year": k[2], "truth": truth[i],
                "prediction": float(m["prediction"].iloc[i]),
                "lower95": float(m["lower95"].iloc[i]), "upper95": float(m["upper95"].iloc[i]),
            })
    return pd.DataFrame(rows)


def pooled(df):
    t = df["truth"].to_numpy(float)
    p = df["prediction"].to_numpy(float)
    scale = max(float(np.mean(np.abs(t))), 1e-8)
    return {
        "n": len(df),
        "scaled_mae": float(np.mean(np.abs(p - t)) / scale),
        "log_rmse": float(np.sqrt(np.mean((np.log(np.maximum(p, 1e-12))
                                           - np.log(np.maximum(t, 1e-12))) ** 2))),
        "coverage95": float(np.mean((t >= df["lower95"]) & (t <= df["upper95"]))),
        "width95": float(np.mean(df["upper95"] - df["lower95"])),
    }


print()
print("=" * 72)
print("2) 调参（repeats 0-9）")
tune = evaluate(range(10), CONFIGS)
rows = []
for (cfgname, mt), sub in tune.groupby(["config", "mask_type"]):
    met = pooled(sub)
    met.update({"config": cfgname, "mask_type": mt})
    rows.append(met)
tune_df = pd.DataFrame(rows)
tune_df.to_csv(OUT / "tuning.csv", index=False, encoding="utf-8-sig")

base = tune_df[tune_df.config == "default"].set_index("mask_type")["scaled_mae"]
piv = tune_df.pivot(index="config", columns="mask_type", values="scaled_mae")
rel = piv.div(base, axis=1)
rel["mean_ratio"] = rel.mean(axis=1)
print(rel.round(4).sort_values("mean_ratio").to_string())

best = rel.drop(index="default")["mean_ratio"].idxmin()
print(f"\n   选中: {best}（三掩码平均相对误差 {rel.loc[best, 'mean_ratio']:.4f}）")

# ---------- 留出 ----------
print()
print("=" * 72)
print("3) 留出评估（repeats 10-19）")
HOLD = {"default": CONFIGS["default"], best: CONFIGS[best]}
hold = evaluate(range(10, 20), HOLD)
hrows = []
for (cfgname, mt), sub in hold.groupby(["config", "mask_type"]):
    met = pooled(sub)
    met.update({"config": cfgname, "mask_type": mt})
    hrows.append(met)
hold_df = pd.DataFrame(hrows)
hold_df.to_csv(OUT / "heldout.csv", index=False, encoding="utf-8-sig")
print(hold_df.pivot(index="config", columns="mask_type",
                    values=["scaled_mae", "coverage95", "width95"]).round(4).to_string())

# ---------- bootstrap ----------
print()
print("=" * 72)
print("4) 格子级配对 bootstrap（留出集，2000 次）")
rng = np.random.default_rng(20261023)
for mt in mask_types:
    d = hold[hold.mask_type == mt]
    wide = d.pivot_table(index=["fold", "repeat", "province", "group_raw", "year"],
                         columns="config", values="prediction")
    truth = d.drop_duplicates(["fold", "repeat", "province", "group_raw", "year"]) \
             .set_index(["fold", "repeat", "province", "group_raw", "year"])["truth"]
    wide = wide.join(truth).dropna()
    t_all = wide["truth"].to_numpy(float)
    scale = max(float(np.mean(np.abs(t_all))), 1e-8)
    print(f"\n   {mt}（{len(wide)} 格）")
    for a in [c for c in HOLD if c != "mice"]:
        for b in ["mice", "default"]:
            if a == b:
                continue
            diffs = []
            for _ in range(2000):
                idx = rng.integers(0, len(wide), len(wide))
                t = t_all[idx]
                ea = np.abs(wide[a].to_numpy(float)[idx] - t).mean()
                eb = np.abs(wide[b].to_numpy(float)[idx] - t).mean()
                diffs.append((ea - eb) / scale)
            lo, hi = np.percentile(diffs, [2.5, 97.5])
            verdict = "显著" if lo > 0 or hi < 0 else "不显著"
            print(f"     {a:12s} vs {b:8s}: {np.mean(diffs):+.4f}  [{lo:+.4f}, {hi:+.4f}]  {verdict}")

json.dump({"best": best, "configs": CONFIGS},
          (OUT / "configs.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n产物已写入 {OUT}")
