"""B2 的重复结构：从 B1 的 5 折 × 20 重复 × 3 遮蔽几何取「协议单元」。

## 为什么需要这个模块

`run_b2.py` 原先的 ``repeats`` 只是**换随机种子重抽场景**，这在统计上不是重复——
它不改变任何数据，只改变噪声实现。于是「重复间方差」衡量的是噪声，不是
「决策对插补结果有多敏感」，而后者才是 R200–R203 要回答的问题。

B1 已经产出了 300 个真正的协议单元（5 折 × 20 重复 × 3 遮蔽几何），
每个单元对应一次完整的「遮蔽 → 插补」过程。本模块把它们转成
**逐省逐组的价格位移**，供 B2 构造「基于插补价格的决策实例」。

## 价格位移怎么算

合同里的组价是 ``price_cny_kg`` 的**跨年均值**（2016–2024，取可用年份）。
所以一个被遮蔽的**单年**单元格，其插补误差要被年数稀释：

```
shift(p, g) = Σ_{单元内被遮蔽的 (p,g) 单元格} w_c · (prediction − truth)
              ────────────────────────────────────────────────────────
                        n_years(p, g) × price_mean(p, g)
```

``w_c = 1 / 该组的品类数``（G06 有猪/牛/羊三个品类，等权近似，见下方局限）。
``n_years`` 是该 (省, 组) 在合同里实际有价的年份数。

**为什么不能直接用相对误差。** 若某年被遮蔽、插补高估 40%，直接施加 40% 会
把组价说成涨了 40%；实际组价是 9 年均值，只涨 ``40%/9 ≈ 4.4%``。
第一版就是这么写的，实测位移被放大 9 倍，已修正。

这个公式在三种遮蔽几何下都自洽：

* ``single_cell``（单年）→ ``shift ≈ δ/9``，稀释 9 倍；
* ``consecutive_years``（连续 k 年）→ ``shift ≈ Σδ/9``；
* ``province_group``（整组全被遮蔽）→ ``shift ≈ mean(δ)``，无稀释——
  因为此时 ``n_masked = n_years``，分子分母同时被年数约掉。

## 两个必须声明的近似

**（1）多品类组按等权处理。** G06 由猪/牛/羊三个品类加权而成，但合同里
只有**组级**价格，没有品类级价格，无法做精确的加权替换。这里把
``w_c = 1/3`` 当作近似。若三品类的消费权重差异大，这个近似会有偏差。

**（2）只做一阶传播。** 忽略「插补让原本缺失的年份进入均值」这一结构性变化
（本项目合同用的是观测年均值，不含插补年份，故此项为零）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.b2_scenarios import B1_METHOD_DEFAULT, B1_MASK_DEFAULT, B1_RUN_DEFAULT, _group_raw_to_id

MASK_TYPES = ("single_cell", "consecutive_years", "province_group")


@dataclass
class ProtocolCell:
    """一个协议单元：某折、某重复、某遮蔽几何下的插补结果。"""

    fold: int
    repeat: int
    mask_type: str
    shift: pd.DataFrame  # index=province, columns=group_id, 相对位移

    @property
    def label(self) -> str:
        return f"f{self.fold}r{self.repeat}"


def _group_category_counts() -> dict[str, int]:
    """每个组由几个价格品类合成（用于等权近似）。"""
    from src.ontology import ONTOLOGY

    return {str(g["group_id"]): max(1, len(g["price_categories"])) for g in ONTOLOGY}


def build_shifts(
    run_dir: str | Path,
    method: str = B1_METHOD_DEFAULT,
    mask_type: str = B1_MASK_DEFAULT,
    provinces: list[str] | None = None,
    groups: list[str] | None = None,
    price_csv: str | Path | None = None,
) -> dict[tuple[int, int], pd.DataFrame]:
    """算出每个 ``(fold, repeat)`` 的逐省逐组价格相对位移。

    返回 ``{(fold, repeat): DataFrame(index=province, columns=group_id)}``，
    未遮蔽的 (省, 组) 填 0。

    位移按「绝对误差 / 组价总量」传播，见模块文档的公式。
    """
    run_dir = Path(run_dir)
    csv = run_dir / "cell_predictions.csv"
    if not csv.exists():
        raise FileNotFoundError(f"B1 预测表不存在：{csv}")

    df = pd.read_csv(csv)
    sub = df[df["method"].eq(method) & df["mask_type"].eq(mask_type)].copy()
    if sub.empty:
        raise ValueError(
            f"没有 method={method!r} & mask_type={mask_type!r} 的行；"
            f"可用遮蔽：{sorted(df['mask_type'].unique())}"
        )

    sub = sub[np.isfinite(sub["prediction"]) & np.isfinite(sub["truth"])]
    sub["group_id"] = sub["group_raw"].map(_group_raw_to_id())
    sub = sub[sub["group_id"].notna()]
    if provinces is not None:
        sub = sub[sub["province"].isin(provinces)]
    if groups is not None:
        sub = sub[sub["group_id"].isin(groups)]
    if sub.empty:
        raise ValueError("筛选后没有可用的遮蔽单元格")

    # 组价基准：合同口径（跨年均值）与年数
    if price_csv is None:
        price_csv = Path(__file__).resolve().parents[1] / "data" / "processed" / "group_prices.csv"
    gp = pd.read_csv(price_csv)
    gp = gp[np.isfinite(gp["price_cny_kg"])]
    base = (
        gp.groupby(["province", "group_id"])["price_cny_kg"]
        .agg(n_years="count", price_mean="mean")
        .reset_index()
    )

    n_cat = _group_category_counts()
    sub["w"] = sub["group_id"].map(lambda g: 1.0 / n_cat.get(str(g), 1))
    sub["delta_abs"] = sub["w"] * (sub["prediction"] - sub["truth"])

    out: dict[tuple[int, int], pd.DataFrame] = {}
    idx = provinces or sorted(sub["province"].unique().tolist())
    cols = groups or sorted(sub["group_id"].unique().tolist())
    for (fold, rep), chunk in sub.groupby(["fold", "repeat"]):
        agg = chunk.groupby(["province", "group_id"])["delta_abs"].sum().reset_index()
        agg = agg.merge(base, on=["province", "group_id"], how="left")
        agg["shift"] = agg["delta_abs"] / (agg["n_years"] * agg["price_mean"])
        mat = (
            agg.pivot(index="province", columns="group_id", values="shift")
            .reindex(index=idx, columns=cols)
            .fillna(0.0)
        )
        out[(int(fold), int(rep))] = mat
    return out


def protocol_cells(
    run_dir: str | Path = Path("outputs") / B1_RUN_DEFAULT,
    method: str = B1_METHOD_DEFAULT,
    mask_type: str = B1_MASK_DEFAULT,
    folds: int | None = None,
    repeats: int | None = None,
    provinces: list[str] | None = None,
    groups: list[str] | None = None,
    price_csv: str | Path | None = None,
) -> list[ProtocolCell]:
    """按 (fold, repeat) 字典序展开协议单元，``folds``/``repeats`` 可截断（供 smoke）。"""
    shifts = build_shifts(
        run_dir,
        method=method,
        mask_type=mask_type,
        provinces=provinces,
        groups=groups,
        price_csv=price_csv,
    )
    keys = sorted(shifts)
    if folds is not None:
        keys = [k for k in keys if k[0] < folds]
    if repeats is not None:
        keys = [k for k in keys if k[1] < repeats]
    if not keys:
        raise ValueError("截断后没有任何协议单元，检查 --folds/--repeats")
    return [
        ProtocolCell(fold=f, repeat=r, mask_type=mask_type, shift=shifts[(f, r)])
        for f, r in keys
    ]


def apply_shift(prices: np.ndarray, shift: pd.Series) -> np.ndarray:
    """把相对位移施加到价格向量上（保持为正）。"""
    prices = np.asarray(prices, dtype=float)
    delta = np.asarray(shift.to_numpy(dtype=float), dtype=float)
    if prices.shape != delta.shape:
        raise ValueError(f"位移维度 {delta.shape} 与价格维度 {prices.shape} 不一致")
    return prices * (1.0 + delta)


def protocol_shift_summary(cells: list[ProtocolCell]) -> pd.DataFrame:
    """协议单元之间价格位移的离散度——用于回答「插补结果到底移动了多少价格」。"""
    rows = []
    for cell in cells:
        flat = cell.shift.to_numpy(dtype=float).ravel()
        rows.append(
            {
                "fold": cell.fold,
                "repeat": cell.repeat,
                "n_nonzero": int((np.abs(flat) > 1e-12).sum()),
                "n_cells": int(flat.size),
                "abs_shift_mean": float(np.abs(flat).mean()),
                "abs_shift_max": float(np.abs(flat).max()),
                "shift_min": float(flat.min()),
                "shift_max": float(flat.max()),
            }
        )
    return pd.DataFrame(rows)
