"""用批发价桥接零售价缺口（跨源换算，不是插补）。

## 问题

零售价面板 ``data/input/price/price_panel_clean.xlsx`` 是**省 × 品类 × 年**的稀疏面板。
浙江的情况最严重：禽类（G05）在 2016–2024 **全部 9 年零观测**——不是个别年份缺，
而是「浙江」工作表根本没有这一行（``仍缺数据`` 登记为 ``整块缺失-品类``，P0）。
因此浙江无法进入 K=4 的决策模型，七省故事只能缩成六省。

## 为什么不删浙江

删掉会损失一个东部沿海省份，且浙江在禽类消费上与江苏/上海可比，
没有理由因为一个品类的采集缺口让整个省出局。

## 桥接方法

1. **批发价工作簿**（``华东华中7省食品零售价_商务预报_分省批发价_mice插补.xlsx``）
   有浙江 9 个品类 × 9 年的批发价，且绝大多数是实测
   （``采样市场数(年累计)`` 非空即实测；仅浙江羊肉 2018–2020/2023、牛肉 2023 为 MICE 插补）。
2. 零售价与批发价**不同源、不同环节**，口径说明明确写着「请勿直接混用」。
   因此不能直接替换，必须用**零售/批发比价**换算：
   ``ratio = retail_kg / wholesale_kg``。
3. 比价在**同时有两套价格的省-年**上估计，按**品类**取中位数。
   比价有强品类效应（鸡蛋 1.10 vs 薯类 1.67），所以不能跨品类池化。
4. ``零售价桥接值 = 批发价 × 该品类比价中位数``。

## 口径一致性（重要）

零售侧**必须**用 ``src.data_audit.load_clean_price_panel`` 读取，
即 ``年均值表`` 的 ``年均值`` 列 + 单位换算（元/500g ×2、元/升 ÷ 油密度）。
不能读 ``清洗长表`` 的 ``数值`` 列：那是另一套聚合，且同表还有 ``换算值``
（对元/500g 行是 ÷2）干扰，两者混用会把比价系统性算错
（实测：混用基准得到比价中位数 1.693，正确基准下禽类是 1.558）。

## 不确定性

比价的省间/年际离散度不小（品类内 10%–90% 分位约 1.10–2.09）。
输出带 ``ratio_q10`` / ``ratio_q90`` 与 ``retail_low`` / ``retail_high``，
供 B4 做桥接敏感性。**桥接值不是实测值**，
``group_prices.csv`` 会用 ``price_source = "bridged_from_wholesale"`` 标记，
``truth_eligible`` 一律为 False（不能用于「真值」参照）。

用法：
    python scripts/build_price_bridge.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_audit import load_clean_price_panel  # noqa: E402

DATA = ROOT / "data" / "input"
RETAIL = DATA / "price" / "price_panel_clean.xlsx"
CATALOG = DATA / "price" / "price_category_catalog.xlsx"
WHOLESALE = ROOT / "华东华中7省食品零售价_商务预报_分省批发价_mice插补.xlsx"
OUT = DATA / "external" / "price_bridge_wholesale.csv"

OIL_DENSITY = 0.92

# 批发源只有 9 个品类；乳制品/水果/水产品/糖/坚果 在批发源里不存在，无法桥接。
BRIDGEABLE = (
    "鸡蛋",
    "禽类",
    "猪肉",
    "牛肉(后腿)",
    "羊肉(后腿)",
    "蔬菜",
    "粮食(大米/面粉)",
    "薯类(马铃薯)",
    "食用油(升)",
)

MIN_RATIO_PAIRS = 8  # 品类比价的省-年配对少于这个数就不桥接该品类


def load_retail() -> pd.DataFrame:
    """零售面板（元/公斤），只保留有观测的格。"""
    panel = load_clean_price_panel(RETAIL, OIL_DENSITY, CATALOG)
    sub = panel[panel["observed"]].copy()
    return sub.rename(columns={"group_raw": "category", "value": "retail_kg"})[
        ["province", "category", "year", "retail_kg"]
    ]


def load_wholesale() -> pd.DataFrame:
    """批发面板（元/公斤）。``wholesale_imputed`` 为 True 表示该格是 MICE 插补值。"""
    raw = pd.read_excel(WHOLESALE, sheet_name="年均值表")
    out = raw.rename(
        columns={
            "省份": "province",
            "品类": "category",
            "年份": "year",
            "年均值": "wholesale_kg",
            "采样市场数(年累计)": "markets",
        }
    )[["province", "category", "year", "wholesale_kg", "markets"]].copy()
    out["year"] = pd.to_numeric(out["year"], errors="raise").astype(int)
    out["wholesale_kg"] = pd.to_numeric(out["wholesale_kg"], errors="coerce")
    out["wholesale_imputed"] = out["markets"].isna()
    return out[out["category"].isin(BRIDGEABLE)]


def estimate_ratios(retail: pd.DataFrame, wholesale: pd.DataFrame) -> pd.DataFrame:
    """按品类估计零售/批发比价。只用两套价格都存在、且批发为实测的省-年。"""
    paired = retail.merge(
        wholesale[["province", "category", "year", "wholesale_kg", "wholesale_imputed"]],
        on=["province", "category", "year"],
        how="inner",
    )
    paired = paired[
        (~paired["wholesale_imputed"])
        & paired["retail_kg"].gt(0)
        & paired["wholesale_kg"].gt(0)
    ].copy()
    paired["ratio"] = paired["retail_kg"] / paired["wholesale_kg"]

    rows = []
    for cat, block in paired.groupby("category"):
        if len(block) < MIN_RATIO_PAIRS:
            continue
        per_prov = block.groupby("province")["ratio"].median()
        rows.append(
            {
                "category": cat,
                "ratio_median": float(block["ratio"].median()),
                "ratio_q10": float(block["ratio"].quantile(0.10)),
                "ratio_q90": float(block["ratio"].quantile(0.90)),
                "ratio_n_pairs": int(len(block)),
                "ratio_n_provinces": int(per_prov.size),
                "ratio_prov_min": float(per_prov.min()),
                "ratio_prov_max": float(per_prov.max()),
            }
        )
    if not rows:
        raise ValueError("没有任何品类满足比价配对下限")
    return pd.DataFrame(rows)


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (桥接表, 比价表)。桥接表只包含「零售缺、批发有」的格。"""
    retail = load_retail()
    wholesale = load_wholesale()
    ratios = estimate_ratios(retail, wholesale)

    grid = (
        wholesale.merge(
            retail[["province", "category", "year"]].assign(retail_observed=True),
            on=["province", "category", "year"],
            how="left",
        )
        .merge(ratios, on="category", how="inner")
        .query("retail_observed != True and wholesale_kg > 0")  # noqa: E712
        .copy()
    )
    if grid.empty:
        raise ValueError("没有需要桥接的格")

    grid["retail_bridged_kg"] = grid["wholesale_kg"] * grid["ratio_median"]
    grid["retail_low_kg"] = grid["wholesale_kg"] * grid["ratio_q10"]
    grid["retail_high_kg"] = grid["wholesale_kg"] * grid["ratio_q90"]
    grid["method"] = "wholesale × category_ratio(median)"
    grid["source"] = f"{WHOLESALE.name}（批发价） + {RETAIL.name}（比价）"
    grid["note"] = (
        "零售源表该省-品类-年缺失；本值为批发价经品类比价换算，非实测零售价，"
        "truth_eligible=False"
    )
    grid = grid.sort_values(["province", "category", "year"]).reset_index(drop=True)
    cols = [
        "province",
        "category",
        "year",
        "wholesale_kg",
        "wholesale_imputed",
        "ratio_median",
        "ratio_q10",
        "ratio_q90",
        "ratio_n_pairs",
        "ratio_n_provinces",
        "ratio_prov_min",
        "ratio_prov_max",
        "retail_bridged_kg",
        "retail_low_kg",
        "retail_high_kg",
        "method",
        "source",
        "note",
    ]
    return grid[cols], ratios


def main() -> None:
    grid, ratios = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    grid.to_csv(OUT, index=False, encoding="utf-8-sig")

    print(f"[bridge] 桥接 {len(grid)} 格 -> {OUT.relative_to(ROOT)}")
    print("\n品类比价（零售/批发，中位数与 10–90 分位）:")
    show = ratios.copy()
    show.columns = ["品类", "中位数", "q10", "q90", "配对数", "省数", "省最小", "省最大"]
    print(show.round(3).to_string(index=False))

    print("\n按省汇总桥接格数:")
    print(grid.groupby("province").size().to_string())
    print(f"\n其中批发基座为 MICE 插补的格: {int(grid['wholesale_imputed'].sum())}")
    bad = grid[grid["wholesale_imputed"]]
    if not bad.empty:
        print(bad[["province", "category", "year"]].to_string(index=False))

    zj = grid[grid["province"].eq("浙江") & grid["category"].eq("禽类")]
    if not zj.empty:
        print("\n浙江禽类（G05）桥接结果（元/公斤）:")
        print(
            zj[["year", "wholesale_kg", "retail_bridged_kg", "retail_low_kg", "retail_high_kg"]]
            .round(2)
            .to_string(index=False)
        )


if __name__ == "__main__":
    main()
