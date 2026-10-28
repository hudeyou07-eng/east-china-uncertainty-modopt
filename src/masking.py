from __future__ import annotations

import numpy as np
import pandas as pd


KEYS = ["province", "group_raw", "year"]


def _fold_slice(items: list, fold: int, n_folds: int, seed: int) -> list:
    if n_folds < 1 or not 0 <= fold < n_folds:
        raise ValueError("Invalid fold specification")
    order = np.random.default_rng(seed).permutation(len(items))
    partitions = np.array_split(order, n_folds)
    return [items[int(i)] for i in partitions[fold]]


def make_mask(
    panel: pd.DataFrame,
    mask_type: str,
    rng: np.random.Generator,
    fraction: float,
    block_years: int,
    fold: int = 0,
    n_folds: int = 1,
    fold_seed: int = 0,
    min_series_observations: int = 5,
) -> np.ndarray:
    eligibility = panel["truth_eligible"] if "truth_eligible" in panel else panel["observed"]
    # 位置化：``mask`` 是按位置索引的布尔数组，而下面要用 ``frame.index`` 回写。
    # 若调用方过滤过行（索引不连续），标签 ≠ 位置，会静默错位甚至越界。
    # 在函数内部重置索引，使两者恒等，调用方无需关心自己传进来的索引形态。
    panel = panel.reset_index(drop=True)
    eligibility = np.asarray(eligibility, dtype=bool)
    observed_idx = panel.index[eligibility].to_numpy()
    if len(observed_idx) == 0:
        raise ValueError("Cannot mask a panel with no observed values")
    mask = np.zeros(len(panel), dtype=bool)
    if mask_type == "single_cell":
        fold_candidates = _fold_slice(observed_idx.tolist(), fold, n_folds, fold_seed)
        if not fold_candidates:
            raise ValueError(f"Fold {fold} has no eligible single-cell truth")
        count = max(1, int(round(len(fold_candidates) * fraction)))
        mask[rng.choice(fold_candidates, size=min(count, len(fold_candidates)), replace=False)] = True
        return mask
    groups: list[pd.DataFrame] = []
    for _, frame in panel.loc[observed_idx].groupby(["province", "group_raw"]):
        frame = frame.sort_values("year")
        if len(frame) >= max(min_series_observations, block_years):
            groups.append(frame)
    if not groups:
        raise ValueError(f"No eligible series for mask type {mask_type}")
    if mask_type == "consecutive_years":
        blocks: list[np.ndarray] = []
        for frame in groups:
            years = frame["year"].to_numpy(int)
            for start in range(len(frame) - block_years + 1):
                selected = years[start : start + block_years]
                if np.all(np.diff(selected) == 1):
                    blocks.append(frame.iloc[start : start + block_years].index.to_numpy())
        fold_blocks = _fold_slice(blocks, fold, n_folds, fold_seed)
        if not fold_blocks:
            raise ValueError(f"Fold {fold} has no eligible consecutive-year block")
        chosen = fold_blocks[int(rng.integers(0, len(fold_blocks)))]
        masked_years = panel.loc[chosen, "year"].sort_values().to_numpy(int)
        if not np.all(np.diff(masked_years) == 1):
            raise AssertionError(f"Year-block is not consecutive: {masked_years.tolist()}")
        mask[chosen] = True
    elif mask_type == "province_group":
        fold_groups = _fold_slice(groups, fold, n_folds, fold_seed)
        if not fold_groups:
            raise ValueError(f"Fold {fold} has no eligible province-group series")
        frame = fold_groups[int(rng.integers(0, len(fold_groups)))]
        mask[frame.index] = True
    else:
        raise ValueError(f"Unknown mask type: {mask_type}")
    return mask


def apply_mask(panel: pd.DataFrame, mask: np.ndarray) -> pd.DataFrame:
    if len(mask) != len(panel):
        raise ValueError("Mask length does not match panel")
    out = panel.copy()
    out["target_truth"] = out["value"]
    out.loc[mask, "value"] = np.nan
    out["masked_for_eval"] = mask
    return out
