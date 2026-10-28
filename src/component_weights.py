"""G06 红肉组内三个品类的消费结构权重。

**来源**：``data/input/external/meat_consumption_structure.csv``
表观消费 = 国家统计局 2023 年产量 + 海关总署 2023 年进口。

**为什么需要它**：组级系数应当是组内各品类的加权平均，权重等于消费结构
（``p̄ = Σ p_i · q_i/T``）。消费表只有组级 ``red_meat``，权重不可观测，
此前用等权作中性先验。等权隐含"三品类等量消费"，而实际猪肉占近八成，
会把红肉的排放高估约 81%（39.47 → 21.75 kg CO2e/kg）。

**为什么不按省取权重**：分省可得的是**产量**，而产量反映生产布局不是消费布局。
山东产猪外调、上海几乎不产猪但消费量大，用分省产量会把两地的消费结构算反。
因此对七个省统一使用全国消费结构。

**已知偏差**：
1. 忽略出口与库存变化（量级远小于 7500 万吨总量）。
2. 表观消费含流通与损耗，不等于摄入量；但作为**结构比例**的代理是可用的。
3. 住户调查只统计家庭购买，不含在外就餐；餐饮中牛肉占比更高，
   故真实牛肉权重可能略高于 13.6%，本权重偏保守。
4. 单年（2023）结构；2016 与 2023 的产量结构几乎一致（猪肉 82.2% vs 81.9%），
   年际稳定性可接受。2019–2020 非洲猪瘟为异常年，不采用。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "input" / "external" / "meat_consumption_structure.csv"

# 三个维度的品类标签 -> 统一 component 键
COMPONENT_BY_PRICE = {"猪肉": "pork", "牛肉(后腿)": "beef", "羊肉(后腿)": "lamb"}
COMPONENT_BY_NUTRITION = {"猪": "pork", "牛": "beef", "羊": "lamb"}
COMPONENT_BY_ENV_ENTITY = {
    "Pig Meat": "pork",
    "Beef (beef herd)": "beef",
    "Beef (dairy herd)": "beef",
    "Lamb & Mutton": "lamb",
}
COMPONENT_BY_ZH = {"猪肉": "pork", "牛肉": "beef", "羊肉": "lamb"}

# 只有红肉组需要按品类结构加权；其余组都是单一品类或同质实体
WEIGHTED_GROUPS = {"G06"}


def load_weights() -> dict[str, float]:
    df = pd.read_csv(SOURCE, encoding="utf-8-sig")
    weights = {COMPONENT_BY_ZH[r.component]: float(r.share) for r in df.itertuples()}
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"消费结构权重之和不为 1：{total}")
    return weights


COMPONENT_WEIGHTS: dict[str, float] = load_weights()


def weights_for(group_id: str, keys: list[str], mapping: dict[str, str]) -> dict[str, float] | None:
    """返回 ``{key: weight}``；该组不需要结构加权时返回 None。

    ``keys`` 是实际参与聚合的品类/实体标签，``mapping`` 把它们映射到 component 键。
    """
    if group_id not in WEIGHTED_GROUPS:
        return None
    out: dict[str, float] = {}
    for key in keys:
        comp = mapping.get(key)
        if comp is None:
            raise ValueError(f"{group_id} 的品类 {key!r} 未映射到 component")
        out[key] = COMPONENT_WEIGHTS[comp]
    return out
