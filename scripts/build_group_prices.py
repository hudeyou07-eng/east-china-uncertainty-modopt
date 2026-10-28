"""生成 B2 数据合同的组级价格文件。

覆盖 docs/EXPERIMENT_PLAN.md 第 3 节的 ``data/processed/group_prices.csv``：

    province, year, group_id, price_cny_kg, observed, source

单品类组直接取该品类价格。G06 红肉由猪肉/牛肉/羊肉三个品类合成，而消费表只有
组级 ``red_meat``、没有品类拆分，因此组级价格必须是组内各品类价格的加权平均。

主口径取**消费结构加权**：权重为表观消费份额 猪肉 0.788 / 牛肉 0.136 / 羊肉 0.076
（``data/input/external/meat_consumption_structure.csv``）。依据是每公斤红肉的
平均支出恰为 ``Σ w_i·p_i``。该权重与营养、环境维度共用，保证三个维度口径一致。

不取"主导品类（猪肉）"的原因：猪肉是三品类里最便宜的，取它等于取最低价
（已核实 ``price_min`` 与猪肉价在 G06 全部观测行相等），会系统性低估组价，
进而让优化器高估红肉的可负担量。

价格面板本身不完整（G06 的 51 个省-年观测中仅 27 行三品类齐全），
缺失品类按**已观测品类重新归一**（条件期望），不丢数据也不退化。
另输出 ``price_equal_weight``（旧等权口径）与 ``price_complete_equal``
（仅品类齐全时的严格等权），供 B2/B4 做口径敏感性。
``aggregation`` 列逐行标注实际发生的聚合方式，便于审计。

## 桥接回退（观测优先）

浙江的禽类（G05）在零售源表里 9 年全部缺失（``整块缺失-品类``），
导致浙江无法进入 K=4 决策模型。``scripts/build_price_bridge.py`` 用批发价
× 品类比价换算出桥接值（**非实测**）。

本脚本对桥接采取**最小扰动**策略：

* ``price_cny_kg``（主口径）：组内只要有一个**观测**就用观测，
  与未接入桥接时的结果完全一致；**仅当整组零观测**时才回退到桥接值。
  这样既让浙江重回七省，又不改动其他省份已冻结的系数。
* ``price_cny_kg_full``：观测 + 桥接混合的完整版本。
  **自 2026-10-27 起（CHANGELOG §31）它与 ``price_cny_kg`` 逐行相同**——
  因为主口径也改成「观测 + 桥接补全」了。列保留仅为向后兼容与审计，
  不再是一个独立的敏感性口径；不要再拿它做「换面板」对比。
* ``price_source``：``observed`` / ``bridged`` / ``missing``，逐行可审。
* ``truth_eligible``：桥接行一律 False（不能当「真值」参照）。

用法：
    python scripts/build_price_bridge.py   # 先跑，生成 external/price_bridge_wholesale.csv
    python scripts/build_group_prices.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.component_weights import COMPONENT_BY_PRICE, weights_for  # noqa: E402
from src.data_audit import load_clean_price_panel  # noqa: E402
from src.ontology import ONTOLOGY  # noqa: E402

DATA = ROOT / "data" / "input"
PROCESSED = ROOT / "data" / "processed"
OIL_DENSITY = 0.92
SOURCE = "data/input/price/price_panel_clean.xlsx"
BRIDGE = DATA / "external" / "price_bridge_wholesale.csv"

# 多品类组的主口径聚合规则。
#
# 组级价格应当是组内各品类价格的**加权平均**，权重等于消费结构：
# 若一户在红肉上按 w_i 的比例购买三个品类，则每公斤红肉的平均支出
# 恰为 Σ w_i·p_i。取主导品类（猪肉）等价于取三品类最低价——已核实
# price_min == 猪肉价在 G06 全部观测行成立——会系统性低估组价，
# 进而让优化器高估红肉的可负担量。等权则相反，会高估组价。
#
# 权重来自 data/input/external/meat_consumption_structure.csv
# （猪肉 0.788 / 牛肉 0.136 / 羊肉 0.076），与营养、环境维度共用同一套权重，
# 保证同一个组在三个维度上说的是同一件事。
#
# 价格面板本身不完整：G06 的 51 个省-年观测里只有 27 行三品类齐全，
# 24 行缺品类。**缺品类时先用批发价桥接补全，再按完整结构加权**（CHANGELOG §31）：
#   price_cny_kg                 = 完整结构加权（观测 + 桥接补全）（主口径）
#   price_structure_renormalized = 缺失品类按已观测品类归一（旧口径，仅审计用）
#   price_equal_weight           = 对可用品类等权（旧口径，敏感性用）
#   price_complete_equal         = 仅品类齐全时的等权值（严格口径，敏感性用）
#   aggregation                  = 逐行标注实际发生了什么，便于审计
#
# 为什么不再用「重新归一」当主口径：把牛肉/羊肉的权重直接丢掉，
# 等价于宣称「红肉里只有猪肉」，会让组价系统性偏低——实测权重质量损失 21.2%、
# 组价低估中位 21.7%（§28.2）。21 行可用桥接补全，仅 3 行（福建）桥接也没有，
# 那 3 行标 lowerbound，明确它是下界而不是估计。
DOMINANT_CATEGORY = {"G06": "猪肉"}


def build_panel() -> pd.DataFrame:
    return load_clean_price_panel(
        DATA / "price" / "price_panel_clean.xlsx",
        OIL_DENSITY,
        DATA / "price" / "price_category_catalog.xlsx",
    )


def load_bridge() -> dict[tuple[str, str, int], float]:
    """读取批发价桥接表，返回 {(省, 品类, 年): 桥接零售价(元/kg)}。

    文件不存在时返回空字典（桥接是可选增强，不阻断主流程）。
    """
    if not BRIDGE.exists():
        return {}
    bridge = pd.read_csv(BRIDGE, encoding="utf-8-sig")
    bridge = bridge[bridge["retail_bridged_kg"].notna() & bridge["retail_bridged_kg"].gt(0)]
    return {
        (str(r.province), str(r.category), int(r.year)): float(r.retail_bridged_kg)
        for r in bridge.itertuples()
    }


def _label(weights: dict[str, float], wsum: float) -> str:
    """把权重字典渲染成审计标签，**按权重降序、同权重按短名**规范排序。

    规范化是必要的：`full_values` 的键顺序取决于哪些品类是桥接补的，
    不排序会让同一种聚合产生两种标签（实测 20 行 `beef/lamb/pork`、
    1 行 `lamb/beef/pork`），审计时会被误读成两种规则。
    """
    ordered = sorted(weights.items(), key=lambda kv: (-kv[1], COMPONENT_BY_PRICE[kv[0]]))
    return "/".join(f"{COMPONENT_BY_PRICE[k]}={w / wsum:.3f}" for k, w in ordered)


def _weighted(values: dict[str, float], group_id: str) -> tuple[float, str]:
    """按组口径把品类价聚合成组价，返回 (组价, 权重标签)。"""
    if not values:
        return float("nan"), ""
    weights = weights_for(group_id, list(values), COMPONENT_BY_PRICE)
    if weights:
        wsum = sum(weights.values())
        price = float(sum(values[k] * w for k, w in weights.items()) / wsum)
        return price, _label(weights, wsum)
    return float(sum(values.values()) / len(values)), ""


def build_group_prices() -> pd.DataFrame:
    panel = build_panel()
    bridge = load_bridge()
    rows = []

    for group in ONTOLOGY:
        gid = group["group_id"]
        cats = group["price_categories"]
        sub = panel[panel["group_raw"].isin(cats)]

        for (province, year), block in sub.groupby(["province", "year"]):
            observed_block = block[block["observed"] & block["value"].notna()]
            values = observed_block.set_index("group_raw")["value"]

            n_obs = int(len(values))
            n_cats = len(cats)
            equal_weight = float(values.mean()) if n_obs else float("nan")
            pmin = float(values.min()) if n_obs else float("nan")
            pmax = float(values.max()) if n_obs else float("nan")
            complete = bool(n_obs == n_cats and n_cats > 0)

            # ---- 桥接补全 ----------------------------------------------------
            # bridged: 本组在该省-年没有观测的品类，用批发价桥接值补上。
            bridged_values = {
                c: bridge[(str(province), c, int(year))]
                for c in cats
                if c not in values.index and (str(province), c, int(year)) in bridge
            }
            full_values = {**bridged_values, **values.to_dict()}
            price_full, full_label = _weighted(full_values, gid)
            n_missing = n_cats - n_obs
            fully_bridged = n_missing > 0 and len(bridged_values) == n_missing

            # 结构加权。**主口径优先用完整结构权重**（CHANGELOG §31）：
            #   - 三品类齐全            → 观测值按完整结构加权；
            #   - 缺品类但都能桥接补全   → 「观测 + 桥接」按完整结构加权；
            #   - 缺品类且桥接也补不上   → 退化为按已观测品类重新归一，
            #     并在 aggregation 里标 lowerbound——组价是真实组价的**下界**
            #     （缺的牛肉/羊肉都比猪肉贵），不是无偏估计。
            # weights_for 只对 WEIGHTED_GROUPS（目前 G06）返回权重，其余组返回 None，
            # 退化为等权，等价于原来的行为。
            weights = weights_for(gid, list(values.index), COMPONENT_BY_PRICE) if n_obs else None
            if weights:
                wsum = sum(weights.values())
                struct_renorm = float(sum(values[k] * w for k, w in weights.items()) / wsum)
                wlabel = _label(weights, wsum)
            else:
                struct_renorm, wlabel = equal_weight, ""

            dominant = DOMINANT_CATEGORY.get(gid)
            if n_obs == 0:
                price, method = float("nan"), "no_observation"
            elif weights and complete:
                price, method = price_full, f"structure_weighted_complete({full_label})"
            elif weights and fully_bridged:
                price, method = price_full, f"structure_weighted_bridged({full_label})"
            elif weights:
                price = struct_renorm
                method = f"structure_weighted_partial_lowerbound({wlabel})"
            elif n_obs == 1:
                price, method = float(values.iloc[0]), "single_category"
            elif complete:
                price, method = equal_weight, "equal_weight_complete"
            else:
                price, method = equal_weight, "equal_weight_partial"

            rows.append(
                {
                    "province": province,
                    "year": int(year),
                    "group_id": gid,
                    "price_cny_kg": price,
                    "observed": bool(n_obs > 0),
                    # truth_eligible 的判据是**组价里有没有非实测成分**，不是「有没有观测」。
                    # 2026-10-27 修订（CHANGELOG §32）：旧版只要求 n_obs>0，于是
                    # `structure_weighted_bridged` 的 20 行（含 21.2% 桥接质量）被标成
                    # True，与 build_price_bridge.py 的「桥接行一律 False」直接冲突。
                    # 现在要求 complete（全部品类实测）才算真值可用：
                    #   - bridged（缺品类用桥接补） → False
                    #   - partial_lowerbound（只观测到 1 个品类，组价是下界）→ False
                    "truth_eligible": bool(complete and observed_block["truth_eligible"].any()),
                    "truth_eligible_reason": (
                        "complete" if complete
                        else ("bridged" if fully_bridged
                              else ("partial_lowerbound" if weights else "partial"))
                    ),
                    "source": SOURCE,
                    "n_categories": n_cats,
                    "n_observed_categories": n_obs,
                    "aggregation": method,
                    "price_structure_weighted": (
                        price if weights and np.isfinite(price) else float("nan")
                    ),
                    "price_structure_renormalized": (
                        struct_renorm if weights else float("nan")
                    ),
                    "price_complete_equal": equal_weight if complete else float("nan"),
                    "price_equal_weight": equal_weight,
                    "price_min": pmin,
                    "price_max": pmax,
                    "price_dominant_category": dominant or "",
                    "price_dominant": (
                        float(values.loc[dominant])
                        if dominant and dominant in values.index
                        else float("nan")
                    ),
                    "price_source": "observed" if n_obs else "missing",
                    "n_bridged_categories": len(bridged_values),
                    "price_cny_kg_full": price_full,
                }
            )

    out = pd.DataFrame(rows).sort_values(["province", "year", "group_id"]).reset_index(drop=True)

    # ---- 组级整体缺失才回退到桥接 --------------------------------------------
    # 只在「某省某组 9 年全部零观测」时启用桥接，保证其他省份的年度均值
    # 逐位不变（否则桥接值会混进已冻结的省-组均值，扰动全部系数）。
    # 浙江 G05 禽类就是唯一的触发点。
    group_has_obs = out.groupby(["province", "group_id"])["observed"].transform("any")
    fallback = (~group_has_obs) & out["price_cny_kg_full"].notna()
    out.loc[fallback, "price_cny_kg"] = out.loc[fallback, "price_cny_kg_full"]
    out.loc[fallback, "price_source"] = "bridged"
    out.loc[fallback, "aggregation"] = "bridged_group_level_fallback"

    dup = out.duplicated(["province", "year", "group_id"])
    if dup.any():
        raise ValueError(f"组级价格存在重复键 {int(dup.sum())} 行")
    if (out["price_cny_kg"].dropna() <= 0).any():
        raise ValueError("组级价格出现非正值")
    return out


def main() -> None:
    out = build_group_prices()
    path = PROCESSED / "group_prices.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")

    obs = out["observed"]
    print(f"[group_prices] {len(out)} 行 | 有观测 {int(obs.sum())} | 无观测 {int((~obs).sum())}")
    print(f"  省 {out['province'].nunique()} | 组 {out['group_id'].nunique()} | 年 {out['year'].min()}-{out['year'].max()}")
    print("\n按组统计（主口径 price_cny_kg = 消费结构加权）:")
    stat = out.groupby("group_id").agg(
        有观测=("observed", "sum"),
        n=("price_cny_kg", "size"),
        均价=("price_cny_kg", "mean"),
        等权价=("price_equal_weight", "mean"),
        严格等权价=("price_complete_equal", "mean"),
        最低价=("price_min", "mean"),
    ).round(2)
    print(stat.to_string())

    g06 = out[(out["group_id"] == "G06") & out["observed"]]
    if not g06.empty:
        strict = g06["price_complete_equal"].dropna()
        print(f"\nG06 观测 {len(g06)} 行，其中品类齐全 {len(strict)} 行")
        print(f"  主口径(结构加权)     {g06['price_cny_kg'].mean():.2f} 元/kg")
        print(f"  等权(旧口径)         {g06['price_equal_weight'].mean():.2f} 元/kg")
        print(f"  严格等权(仅齐全行)   {strict.mean():.2f} 元/kg")
        print(f"  最低价(≈猪肉)        {g06['price_min'].mean():.2f} 元/kg")
        print(f"  结构加权 / 最低价 = {g06['price_cny_kg'].mean() / g06['price_min'].mean():.2f}x")
        print("  聚合方式分布:", g06["aggregation"].str.split("(").str[0].value_counts().to_dict())

    # ---- 桥接回退报告 ----------------------------------------------------
    print("\n价格来源分布:")
    print(out["price_source"].value_counts().to_string())
    bridged = out[out["price_source"].eq("bridged")]
    if not bridged.empty:
        print(f"\n桥接回退 {len(bridged)} 行（非实测，truth_eligible 全为 False）:")
        print(bridged.groupby(["province", "group_id"]).size().to_string())
        print("\n桥接值 vs 观测均值（同省同组，仅供量级核对）:")
        cmp = out[out["observed"]].groupby(["province", "group_id"])["price_cny_kg"].mean()
        for (prov, gid), block in bridged.groupby(["province", "group_id"]):
            obs_mean = cmp.get((prov, gid), float("nan"))
            print(
                f"  {prov} {gid}: 桥接 {block['price_cny_kg'].mean():.2f} | "
                f"观测均值 {obs_mean:.2f} | 比值 {block['price_cny_kg'].mean() / obs_mean:.2f}x"
            )

    # ---- 决策组完整性 ----------------------------------------------------
    decision = ["G02", "G05", "G06", "G08"]
    wide = out[out["group_id"].isin(decision)].pivot_table(
        index="province", columns="group_id", values="price_cny_kg"
    )
    ready = wide.dropna().index.tolist()
    blocked = {p: [g for g in decision if pd.isna(wide.at[p, g])] for p in wide.index}
    blocked = {p: g for p, g in blocked.items() if g}
    print(f"\nK=4 决策组齐全的省份 {len(ready)} 个: {ready}")
    if blocked:
        print(f"  仍被排除: {blocked}")


if __name__ == "__main__":
    main()
