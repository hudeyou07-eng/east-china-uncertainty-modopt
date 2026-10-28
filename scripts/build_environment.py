"""生成 B2 数据合同的环境系数文件。

覆盖 docs/EXPERIMENT_PLAN.md 第 3 节的 ``data/processed/environment.csv``：

    impact, group_id, value_per_kg, source, boundary

两套数据并存，用 ``dataset`` 列区分，不混合：

* ``global_pn``  —— Our World in Data 发布的 Poore & Nemecek (2018) 衍生表
  （原始文件见 ``D:/汇总/SRT/原始数据/生态足迹/``）。12 组 × 4 指标全部命中、零缺失，
  且同一来源内部口径一致，**作为主口径**。系统边界为 farm-to-retail
  （含土地利用变化、农场生产、饲料、加工、运输、包装、零售；不含烹饪与家庭浪费）。
* ``china_lca`` —— 6 篇中文学术文献汇总，覆盖 12 组 × 3 指标，但 Nuts and seeds 与
  Tubers, starches 缺 land。各文献系统边界不一，``boundary`` 标为
  ``unspecified_pending_review``，**不满足 Plan §3 的「系统边界统一」要求**，
  只能作为对照，不能单独支撑主结论。

单位统一到 L/kg（china_lca 的淡水为 m3/kg，乘 1000 换算）。

**组内聚合口径**（``aggregation`` 列逐行标注）：

* ``global_pn`` 主口径按**消费结构加权**（仅 G06 红肉），其余组为实体扁平等权。
  依据是组级系数应满足 ``p̄ = Σ p_i·q_i/T``，即权重等于消费份额。
  G06 的三个品类取表观消费份额 猪肉 78.8% / 牛肉 13.6% / 羊肉 7.6%
  （见 ``data/input/external/meat_consumption_structure.csv`` 与 ``src/component_weights.py``）。
  若扁平化等权，牛肉因拆成 beef herd / dairy herd 两个实体会拿到 50% 权重，
  排放被高估约 81%（39.47 → 21.75 kg CO2e/kg）。
* ``china_lca`` 用中位数：同组同指标下有多个文献值，中位数对极端值稳健，
  且这里只需区域对照量级，不需要精细加权。

**已知限制**：G07 水产（Fish (farmed) 与 Prawns (farmed)）仍是实体扁平等权，
把虾的 26.87 与鱼的 13.63 平均成 20.25。水产消费结构缺少可靠公开依据，
不编造权重；此项登记为已知偏差，见 ``model_manifest.json`` 的
``environment_boundary.known_limitations``。

``lower`` / ``upper`` 始终取组内实体的 min / max，表达「实体间差异」，不随权重改变。

用法：
    python scripts/build_environment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ontology import GLOBAL_ENV_METRICS, ONTOLOGY  # noqa: E402
from src.component_weights import COMPONENT_WEIGHTS, WEIGHTED_GROUPS  # noqa: E402

DATA = ROOT / "data" / "input" / "clean_tables"
PROCESSED = ROOT / "data" / "processed"

BOUNDARY_PN = "farm-to-retail (Poore & Nemecek 2018, via Our World in Data)"
BOUNDARY_CN = "unspecified_pending_review"

UNIT_MAP = {
    "ghg": "kg CO2e/kg",
    "freshwater": "L/kg",
    "land": "m2/kg",
    "eutrophication": "g PO4e/kg",
}

PN_COLUMNS = {
    "ghg_kg_co2e_per_kg": "ghg",
    "freshwater_l_per_kg": "freshwater",
    "land_m2_per_kg": "land",
    "eutrophication_g_po4e_per_kg": "eutrophication",
}


def _hierarchical_mean(
    block: pd.DataFrame,
    col: str,
    subgroups: dict[str, list[str]] | None,
    group_id: str,
) -> tuple[float, float, float, int, str]:
    """组级环境系数：先品类内平均，再在品类间加权。

    权重的选择分两种：

    * 组在 ``component_weights.WEIGHTED_GROUPS`` 里（目前只有 G06 红肉）：
      用**消费结构权重**（猪肉 78.8% / 牛肉 13.6% / 羊肉 7.6%，见
      ``data/input/external/meat_consumption_structure.csv``）。
      依据是组级系数应满足 ``p̄ = Σ p_i·q_i/T``，权重等于消费份额。
    * 其余组：品类间等权。这些组要么是单实体，要么是同一品类的不同形态
      （如 Milk / Cheese），没有可靠的消费结构数据可用。

    为什么不统一用实体扁平等权：红肉的牛肉分成 beef herd 与 dairy herd 两个实体，
    扁平化会让牛肉拿到 2/4 = 50% 权重，与实际消费结构差得更远。

    lower/upper 始终取全部实体的 min/max，表达「实体间差异」，不随权重改变。
    """
    if not subgroups:
        vals = block[col].dropna().astype(float)
        if vals.empty:
            return (np.nan, np.nan, np.nan, 0, "none")
        return (float(vals.mean()), float(vals.min()), float(vals.max()), int(len(vals)), "flat")

    sub_means: dict[str, float] = {}
    all_vals: list[float] = []
    for name, ents in subgroups.items():
        v = block.loc[block["entity"].isin(ents), col].dropna().astype(float)
        if v.empty:
            continue
        sub_means[name] = float(v.mean())
        all_vals.extend(v.tolist())
    if not sub_means:
        return (np.nan, np.nan, np.nan, 0, "none")

    if group_id in WEIGHTED_GROUPS:
        weights = {k: COMPONENT_WEIGHTS[k] for k in sub_means}
        method = "structure_weighted(" + "/".join(f"{k}={v:.3f}" for k, v in weights.items()) + ")"
    else:
        weights = {k: 1.0 for k in sub_means}
        method = f"hierarchical_equal({len(sub_means)} subgroups)"

    wsum = sum(weights.values())
    value = sum(sub_means[k] * weights[k] for k in sub_means) / wsum
    return (float(value), float(min(all_vals)), float(max(all_vals)), int(len(all_vals)), method)


def build_global_pn() -> pd.DataFrame:
    g = pd.read_csv(DATA / "global_environment.csv", encoding="utf-8-sig")
    rows = []
    for group in ONTOLOGY:
        ents = [e for e in group["global_env_entities"] if e in set(g["entity"])]
        if not ents:
            continue
        block = g[g["entity"].isin(ents)]
        subgroups = group.get("global_env_subgroups")
        for col, impact in PN_COLUMNS.items():
            value, lower, upper, n, method = _hierarchical_mean(block, col, subgroups, group["group_id"])
            if n == 0:
                continue
            rows.append(
                {
                    "impact": impact,
                    "group_id": group["group_id"],
                    "value_per_kg": value,
                    "lower": lower,
                    "upper": upper,
                    "unit": UNIT_MAP[impact],
                    "source": "data/input/clean_tables/global_environment.csv",
                    "boundary": BOUNDARY_PN,
                    "dataset": "global_pn",
                    "aggregation": method,
                    "n_records": n,
                    "n_sources": int(block["source_file"].nunique()),
                    "n_group_average_proxy": 0,
                }
            )
    return pd.DataFrame(rows)


def build_china_lca() -> pd.DataFrame:
    lca = pd.read_csv(DATA / "china_lca.csv", encoding="utf-8-sig")
    rows = []
    for group in ONTOLOGY:
        block = lca[lca["food_group"].isin(group["lca_groups"])]
        if block.empty:
            continue
        for impact in ["ghg", "freshwater", "land"]:
            vals = block.loc[block["metric"].eq(impact), "value"].dropna().astype(float)
            if vals.empty:
                continue
            if impact == "freshwater":
                vals = vals * 1000.0  # m3 -> L
            rows.append(
                {
                    "impact": impact,
                    "group_id": group["group_id"],
                    "value_per_kg": float(vals.median()),
                    "lower": float(vals.quantile(0.25)),
                    "upper": float(vals.quantile(0.75)),
                    "unit": UNIT_MAP[impact],
                    "source": "data/input/clean_tables/china_lca.csv",
                    "boundary": BOUNDARY_CN,
                    "dataset": "china_lca",
                    "aggregation": "median",
                    "n_records": int(len(vals)),
                    "n_sources": int(block.loc[block["metric"].eq(impact), "data_source"].nunique()),
                    "n_group_average_proxy": int(
                        block.loc[block["metric"].eq(impact), "is_group_average_proxy"].astype(bool).sum()
                    ),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    pn = build_global_pn()
    cn = build_china_lca()
    out = pd.concat([pn, cn], ignore_index=True)

    dup = out.duplicated(["dataset", "impact", "group_id"])
    if dup.any():
        raise ValueError(f"环境系数存在重复键 {int(dup.sum())} 行")
    if (out["value_per_kg"].dropna() < 0).any():
        raise ValueError("环境系数出现负值")

    path = PROCESSED / "environment.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")

    print(f"[environment] {len(out)} 行 | 数据集 {out['dataset'].nunique()} 套 | 指标 {out['impact'].nunique()}")
    for ds, sub in out.groupby("dataset"):
        cov = sub.groupby("group_id")["impact"].nunique()
        full = (cov == sub["impact"].nunique()).sum()
        print(f"  {ds:<10} {len(sub):>3} 行 | 组 {sub['group_id'].nunique()} | 指标 {sub['impact'].nunique()} | 全指标覆盖组 {full}")
        print(f"             边界: {sub['boundary'].iloc[0]}")

    print("\n主口径（global_pn）各组 ghg 与 land:")
    piv = pn[pn["impact"].isin(["ghg", "land"])].pivot(index="group_id", columns="impact", values="value_per_kg")
    print(piv.round(2).to_string())

    missing_cn = cn.groupby("group_id")["impact"].nunique()
    lack = missing_cn[missing_cn < 3]
    if not lack.empty:
        print(f"\nchina_lca 指标不全的组: {lack.to_dict()}")


if __name__ == "__main__":
    main()
