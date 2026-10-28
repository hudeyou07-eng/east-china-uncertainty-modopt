"""生成 B2 数据合同的决策边界文件。

覆盖 docs/EXPERIMENT_PLAN.md 第 3 节的 ``data/processed/decision_bounds.csv``：

    province, scenario, group_id, lower_g_day, upper_g_day

在 Plan 要求的五列之外，本文件额外提供 ``bound_type`` 列以区分两类约束：

* ``single`` —— 单组上下界，对应 ``group_id`` 是一个组（如 ``G08``）。
* ``joint``  —— 联合上下界，对应 ``group_id`` 是 ``+`` 连接的组集合
  （如 ``G05+G06``），表示这些组的**合计**落在区间内，组间分配不受限。

**为什么不把指南类别硬拆到 ontology 的组上**

ontology 的 12 组是从价格/营养/环境三个维度并出来的，与两份指南的类别并不一一对应。
此前版本为了让「畜禽肉 40–75 g」落到 G05 与 G06 两个变量上，按一个假设的消费结构
（猪肉六成、禽肉两成半）拆成红肉 25–45、禽肉 15–30。这个比例在仓库内没有任何数据支撑，
是纯粹的解释性选择，会悄悄决定 B2 的红肉结论。

现在改为联合约束 ``G05+G06 ∈ [40, 75]``：既忠实于指南原文（指南确实不区分畜肉与禽肉），
又不引入任何编造的拆分比例。代价是组间分配由模型在成本/营养/环境目标下自行决定，
因此 **CDG 情景下的红肉结果不能解读为「指南推荐的红肉量」**——这一点必须随结果报告。

三种情景的来源与构造规则（**全部为预注册设定，B2 之后不得改动**）：

* ``CDG``       —— 中国居民膳食指南（2022）平衡膳食宝塔的组级推荐范围。
* ``EAT``       —— Willett et al. (2019) EAT-Lancet 参考膳食的目标值与上下限。
* ``HEAL_base`` —— 本工作定义：以 ``baseline_consumption.csv`` 的省级基线为锚，
  下界 0、上界 2 倍基线；无基线的组（G10 薯类、G12 大豆坚果）退化为 2 倍 CDG 上限。

**仍存在的三处类别错配（无法用联合约束消除，只能声明）**

1. CDG 的「谷类 200–300 g」不含豆类，而 G04 是 ``grains_legumes``（谷物+豆类）。
   因此 200–300 对 G04 而言偏紧，实际允许的 G04 总量应更高。
2. EAT 的 whole grains 232 g 同样只对应谷物部分，映射到 G04 有同样的偏紧问题。
3. EAT 的 legumes 与 nuts 是两类，而 G12 合并为「大豆及坚果」，二者只能合并映射。

用法：
    python scripts/build_decision_bounds.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ontology import ONTOLOGY, PROVINCES  # noqa: E402

PROCESSED = ROOT / "data" / "processed"

JOINT_SEP = "+"
ALL_GROUPS = [g["group_id"] for g in ONTOLOGY]

SRC_CDG = "China Dietary Guidelines 2022, balanced diet pagoda"
SRC_EAT = "Willett et al. 2019, EAT-Lancet reference diet"
SRC_HEAL = "derived in this work: 0 to 2x provincial baseline"
SRC_TECH = (
    "technical bound: 0 to 2x provincial baseline; "
    "CDG does not separate red meat from poultry"
)

# CDG 单组约束：group_id -> (lower, upper, note)
CDG_SINGLE: dict[str, tuple[float, float, str]] = {
    "G01": (300, 500, "奶及奶制品 300-500 g"),
    "G02": (40, 50, "蛋类 40-50 g"),
    "G03": (200, 350, "水果 200-350 g"),
    "G04": (200, 300, "谷类 200-300 g（含全谷物和杂豆 50-150）；G04 还含豆类，此区间对 G04 偏紧"),
    "G07": (40, 75, "水产品 40-75 g"),
    "G08": (300, 500, "蔬菜 300-500 g"),
    "G09": (0, 50, "添加糖每日不超过 50 g（最好 25 g 以下）"),
    "G10": (50, 100, "薯类 50-100 g"),
    "G11": (25, 30, "烹调油 25-30 g"),
    "G12": (25, 35, "大豆及坚果 25-35 g"),
}

# CDG 联合约束：group 集合（+ 连接）-> (lower, upper, note)
CDG_JOINT: dict[str, tuple[float, float, str]] = {
    "G05+G06": (
        40,
        75,
        "畜禽肉 40-75 g；指南不区分畜肉与禽肉，故设为联合约束，组间分配由模型决定",
    ),
}

# 联合约束的成员组在 CDG 情景下仍需各自的技术边界，否则 LP 中变量无界。
CDG_JOINT_MEMBERS = ["G05", "G06"]

EAT_BOUNDS: dict[str, tuple[float, float, str]] = {
    "G01": (0, 500, "dairy 250 g 目标，范围 0-500 g"),
    "G02": (0, 25, "eggs 13 g 目标，范围 0-25 g"),
    "G03": (100, 300, "fruits 200 g 目标，范围 100-300 g"),
    "G04": (0, 400, "whole grains 232 g 目标，上限按 60% 能量折算约 400 g；G04 含豆类，偏紧"),
    "G05": (0, 58, "poultry 29 g 目标，范围 0-58 g"),
    "G06": (0, 28, "red meat 14 g 目标，范围 0-28 g"),
    "G07": (0, 100, "fish 28 g 目标，范围 0-100 g"),
    "G08": (200, 600, "vegetables 300 g 目标，范围 200-600 g"),
    "G09": (0, 31, "added sugar 31 g 上限，范围 0-31 g"),
    "G10": (0, 100, "tubers 50 g 目标，范围 0-100 g"),
    "G11": (39, 78, "added fats 51 g 目标，范围 39-78 g"),
    "G12": (0, 175, "legumes 50 + nuts 50 合计 100 g 目标，范围 0-175 g"),
}


def _rec(
    province: str,
    scenario: str,
    group_id: str,
    bound_type: str,
    lo: float,
    hi: float,
    source: str,
    note: str,
) -> dict:
    return {
        "province": province,
        "scenario": scenario,
        "group_id": group_id,
        "bound_type": bound_type,
        "lower_g_day": float(lo),
        "upper_g_day": float(hi),
        "source": source,
        "note": note,
    }


def build() -> pd.DataFrame:
    baseline = pd.read_csv(PROCESSED / "baseline_consumption.csv", encoding="utf-8-sig")
    base_mean = baseline.groupby(["province", "group_id"])["value_g_day"].mean()

    rows: list[dict] = []
    for province in PROVINCES:
        # --- CDG：单组约束 ---
        for gid, (lo, hi, note) in CDG_SINGLE.items():
            rows.append(_rec(province, "CDG", gid, "single", lo, hi, SRC_CDG, note))

        # --- CDG：联合约束 ---
        for gid, (lo, hi, note) in CDG_JOINT.items():
            rows.append(_rec(province, "CDG", gid, "joint", lo, hi, SRC_CDG, note))

        # --- CDG：联合成员的技术边界（数据驱动，非指南） ---
        for gid in CDG_JOINT_MEMBERS:
            b = base_mean.get((province, gid))
            if pd.notna(b):
                hi = float(b) * 2.0
                note = f"技术边界，基线 {b:.1f} g/day 的 2 倍；实际受限的合计区间见 G05+G06 行"
            else:
                hi = 150.0
                note = "技术边界，无消费基线，取 150 g；实际受限的合计区间见 G05+G06 行"
            rows.append(_rec(province, "CDG", gid, "single", 0.0, hi, SRC_TECH, note))

        # --- EAT：12 组单组约束 ---
        for gid, (lo, hi, note) in EAT_BOUNDS.items():
            rows.append(_rec(province, "EAT", gid, "single", lo, hi, SRC_EAT, note))

        # --- HEAL_base：12 组单组约束 ---
        for gid in ALL_GROUPS:
            b = base_mean.get((province, gid))
            if pd.notna(b):
                lo, hi = 0.0, float(b) * 2.0
                note = f"基线 {b:.1f} g/day，上界取 2 倍"
            else:
                cdg_hi = CDG_SINGLE[gid][1]
                lo, hi = 0.0, float(cdg_hi) * 2.0
                note = f"无消费基线，退化为 2 倍 CDG 上限（{cdg_hi * 2:.0f} g）"
            rows.append(_rec(province, "HEAL_base", gid, "single", lo, hi, SRC_HEAL, note))

    out = (
        pd.DataFrame(rows)
        .sort_values(["scenario", "province", "bound_type", "group_id"])
        .reset_index(drop=True)
    )
    validate(out)
    return out


def expand_groups(label: str) -> list[str]:
    """把 ``G05+G06`` 这类联合标签展开成组列表。"""
    return [part.strip() for part in str(label).split(JOINT_SEP) if part.strip()]


def validate(out: pd.DataFrame) -> None:
    dup = out.duplicated(["province", "scenario", "group_id"])
    if dup.any():
        raise ValueError(f"决策边界存在重复键 {int(dup.sum())} 行")

    bad = out[out["lower_g_day"] > out["upper_g_day"]]
    if not bad.empty:
        raise ValueError(f"存在 lower > upper 的行:\n{bad}")

    if (out[["lower_g_day", "upper_g_day"]] < 0).any().any():
        raise ValueError("决策边界出现负值")

    unknown = set()
    for label in out["group_id"]:
        for gid in expand_groups(label):
            if gid not in ALL_GROUPS:
                unknown.add(gid)
    if unknown:
        raise ValueError(f"决策边界引用了本体中不存在的组: {sorted(unknown)}")

    # 每个省×情景必须覆盖全部 12 组（单组约束或被联合约束覆盖）
    for (province, scenario), sub in out.groupby(["province", "scenario"]):
        covered = set()
        for label in sub["group_id"]:
            covered.update(expand_groups(label))
        missing = sorted(set(ALL_GROUPS) - covered)
        if missing:
            raise ValueError(f"{province}/{scenario} 未覆盖组 {missing}")


def main() -> None:
    out = build()
    path = PROCESSED / "decision_bounds.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")

    n_single = int((out["bound_type"] == "single").sum())
    n_joint = int((out["bound_type"] == "joint").sum())
    print(
        f"[decision_bounds] {len(out)} 行 = {out['scenario'].nunique()} 情景 × "
        f"{out['province'].nunique()} 省；单组约束 {n_single} 行，联合约束 {n_joint} 行"
    )

    for sc, sub in out.groupby("scenario"):
        print(f"\n{sc}（{sub['source'].iloc[0]}）")
        tbl = (
            sub[sub["province"] == PROVINCES[0]][["group_id", "bound_type", "lower_g_day", "upper_g_day"]]
            .set_index("group_id")
            .round(1)
        )
        print(tbl.to_string())

    print("\n联合约束（CDG）:")
    joint = out[(out["scenario"] == "CDG") & (out["bound_type"] == "joint")]
    print(joint[["province", "group_id", "lower_g_day", "upper_g_day"]].to_string(index=False))

    print("\nHEAL_base 上界随省变化示例（G08 蔬菜）:")
    print(
        out[(out.scenario == "HEAL_base") & (out.group_id == "G08")][["province", "upper_g_day"]]
        .round(1)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
