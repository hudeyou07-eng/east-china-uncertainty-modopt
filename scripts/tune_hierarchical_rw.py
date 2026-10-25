"""B1 补强实验：hierarchical_rw 的参数化敏感性与超参调优。

1. 回归校验：默认参数是否逐位复现已存档的 B1 结果。
2. 参数化对照：原编码 / 年份零和约束 / 参考编码，点预测与区间差异。
3. 调参（repeats 0-9）+ 留出评估（repeats 10-19），与存档 MICE 比较。
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
OUT = ROOT / "outputs" / "B1_tuning_20261023_133000"
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


# ---------- 1. 回归校验 ----------
print("=" * 72)
print("1) 回归校验：默认参数能否逐位复现存档结果")
worst, n_checked = 0.0, 0
for fold, repeat, mt, masked, target in blocks(range(3)):
    pred = hierarchical_rw_predict(masked, target)
    ref = archived_rw[(archived_rw.fold == fold) & (archived_rw.repeat == repeat)
                      & (archived_rw.mask_type == mt)]
    ref = ref.set_index(["province", "group_raw", "year"])
    for i, (_, row) in enumerate(target.iterrows()):
        key = (row["province"], row["group_raw"], int(row["year"]))
        if key in ref.index:
            worst = max(worst, abs(pred.mean[i] - float(ref.loc[key, "prediction"])))
            n_checked += 1
print(f"   比对 {n_checked} 个格子，最大绝对差 = {worst:.3e}")
print("   结论:", "逐位复现，改动未破坏默认行为" if worst < 1e-9 else "不一致！")

# ---------- 2. 参数化对照 ----------
print()
print("=" * 72)
print("2) 参数化对照（同 ridge / year_rw）")
variants = ["original", "year_centered", "reference"]
acc = {v: {"mean": [], "upper95": [], "width95": []} for v in variants}
for fold, repeat, mt, masked, target in blocks(range(3)):
    res = {v: hierarchical_rw_predict(masked, target, parameterisation=v) for v in variants}
    base = res["original"]
    for v in variants:
        acc[v]["mean"].append(np.abs(res[v].mean - base.mean).max())
        acc[v]["upper95"].append(np.abs(res[v].upper95 - base.upper95).max())
        acc[v]["width95"].append(np.mean(res[v].upper95 - res[v].lower95))
for v in variants:
    print(f"   {v:16s} 点预测最大绝对差 {max(acc[v]['mean']):.3e}"
          f" | 95%上界最大绝对差 {max(acc[v]['upper95']):.3e}"
          f" | 平均95%区间宽 {np.mean(acc[v]['width95']):.2f}")

# ---------- 3. 调参 + 留出 ----------
print()
print("=" * 72)
print("3) 调参（repeats 0-9）与留出评估（repeats 10-19）")

CONFIGS = {"default": {"ridge": 1.0, "year_rw": 4.0}}
for r, yw in itertools.product([0.1, 1.0, 10.0, 100.0], [0.5, 1.0, 4.0, 16.0]):
    CONFIGS[f"r{r}_y{yw}"] = {"ridge": r, "year_rw": yw}
CONFIGS["year_centered"] = {"parameterisation": "year_centered"}
for ir in [1.0, 10.0, 100.0, 1000.0]:
    CONFIGS[f"inter{ir}"] = {"ridge": 1.0, "year_rw": 4.0, "interaction_ridge": ir}


def evaluate(repeats, configs):
    rw_rows, mice_rows = [], []
    for fold, repeat, mt, masked, target in blocks(repeats):
        truth = target["target_truth"].to_numpy(float)
        keys = list(zip(target["province"], target["group_raw"], target["year"].astype(int)))
        m = mice_all[(mice_all.fold == fold) & (mice_all.repeat == repeat)
                     & (mice_all.mask_type == mt)]
        m = m.set_index(["province", "group_raw", "year"]).reindex(keys)
        for name, kwargs in configs.items():
            pred = hierarchical_rw_predict(masked, target, **kwargs)
            for i, k in enumerate(keys):
                rw_rows.append({
                    "config": name, "fold": fold, "repeat": repeat, "mask_type": mt,
                    "province": k[0], "group_raw": k[1], "year": k[2], "truth": truth[i],
                    "prediction": float(pred.mean[i]),
                    "lower95": float(pred.lower95[i]), "upper95": float(pred.upper95[i]),
                })
        for i, k in enumerate(keys):
            mice_rows.append({
                "config": "mice", "fold": fold, "repeat": repeat, "mask_type": mt,
                "province": k[0], "group_raw": k[1], "year": k[2], "truth": truth[i],
                "prediction": float(m["prediction"].iloc[i]),
                "lower95": float(m["lower95"].iloc[i]), "upper95": float(m["upper95"].iloc[i]),
            })
    return pd.concat([pd.DataFrame(rw_rows), pd.DataFrame(mice_rows)], ignore_index=True)


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
        "over3x": int(np.sum(p > 3 * t)),
    }


tune = evaluate(range(10), CONFIGS)
tune_rows = []
for (cfgname, mt), sub in tune.groupby(["config", "mask_type"]):
    met = pooled(sub)
    met.update({"config": cfgname, "mask_type": mt})
    tune_rows.append(met)
tune_df = pd.DataFrame(tune_rows)
tune_df.to_csv(OUT / "tuning_grid.csv", index=False, encoding="utf-8-sig")

print("\n   --- consecutive_years 全网格（按 scaled_mae 排序）---")
sub = tune_df[tune_df.mask_type == "consecutive_years"].sort_values("scaled_mae")
print(sub[["config", "n", "scaled_mae", "log_rmse", "coverage95", "width95", "over3x"]]
      .to_string(index=False))

best = sub[sub.config != "mice"].iloc[0]["config"]
print(f"\n   非 MICE 最优配置: {best}")
print(f"   与 MICE 的点误差比: "
      f"{sub[sub.config == best].iloc[0]['scaled_mae'] / sub[sub.config == 'mice'].iloc[0]['scaled_mae']:.2f}x")

# ---------- 4. 留出评估 ----------
print()
print("=" * 72)
print("4) 留出评估：repeats 10-19（调参时未使用）")
HOLD = {k: CONFIGS[k] for k in {best, "default", "year_centered"}}
HOLD["inter10.0"] = CONFIGS["inter10.0"]
hold = evaluate(range(10, 20), HOLD)
hold_rows = []
for (cfgname, mt), grp in hold.groupby(["config", "mask_type"]):
    met = pooled(grp)
    met.update({"config": cfgname, "mask_type": mt})
    hold_rows.append(met)
hold_df = pd.DataFrame(hold_rows)
hold_df.to_csv(OUT / "heldout_metrics.csv", index=False, encoding="utf-8-sig")
print(hold_df.pivot(index="config", columns="mask_type",
                    values=["scaled_mae", "coverage95", "width95"]).round(4).to_string())

# ---------- 5. 格子级配对 bootstrap ----------
print()
print("=" * 72)
print("5) 格子级配对 bootstrap（consecutive_years，留出集，2000 次）")
rng = np.random.default_rng(20261023)
ce = hold[hold.mask_type == "consecutive_years"]
wide = ce.pivot_table(index=["fold", "repeat", "province", "group_raw", "year"],
                      columns="config", values="prediction")
truth = ce.drop_duplicates(["fold", "repeat", "province", "group_raw", "year"]) \
          .set_index(["fold", "repeat", "province", "group_raw", "year"])["truth"]
wide = wide.join(truth).dropna()
print(f"   参与检验的格子数 = {len(wide)}")

pairs = [(c, "mice") for c in HOLD if c != "mice"]
boot = {p: [] for p in pairs}
arr_truth = wide["truth"].to_numpy(float)
scale = max(float(np.mean(np.abs(arr_truth))), 1e-8)
for _ in range(2000):
    idx = rng.integers(0, len(wide), len(wide))
    t = arr_truth[idx]
    for a, b in pairs:
        ea = np.abs(wide[a].to_numpy(float)[idx] - t).mean()
        eb = np.abs(wide[b].to_numpy(float)[idx] - t).mean()
        boot[(a, b)].append((ea - eb) / scale)
print("\n   Δscaled_MAE（正 = 前者更差）")
for (a, b), vals in boot.items():
    lo, hi = np.percentile(vals, [2.5, 97.5])
    print(f"   {a:14s} vs {b:5s}: 点估计 {np.mean(vals):+.4f}  95%CI [{lo:+.4f}, {hi:+.4f}]"
          f"  {'显著' if lo > 0 or hi < 0 else '不显著'}")

json.dump(
    {"best_config": best, "tuning_rows": len(tune), "heldout_rows": len(hold)},
    (OUT / "summary.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=2,
)
print(f"\n   产物已写入 {OUT}")
