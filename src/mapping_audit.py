"""价格口径与营养表的对应性审计（可复用模块）。

价格面板的「口径构成」列记录了每个观测实际由哪些食物组成。把它与营养表
逐个比对，可以客观回答"这个组的成本参数和营养参数是不是同一种食物"。
"""
from __future__ import annotations

import re

import pandas as pd

# 口径构成里表示"综合/不指明具体品种"的词，不参与缺失判定
GENERIC = {
    "—", "-", "统", "统装", "集贸", "综合", "农贸", "超市", "水产综合",
    "禽类", "水果", "奶制品", "水产", "杂", "散装",
}

# 价格口径用词 -> 营养表食物名。按品类区分，避免"后腿"在猪牛羊之间串味。
CATEGORY_ALIASES: dict[str, dict[str, str]] = {
    "猪肉": {t: "猪" for t in
             ["猪", "猪肉", "精瘦肉", "全瘦", "精瘦", "后腿", "带皮后腿",
              "后座", "排骨", "肋条"]},
    "牛肉(后腿)": {t: "牛" for t in
                ["牛", "牛肉", "牛腩", "牛腱", "牛腿肉", "鲜牛肉", "带骨", "腱子", "后腿"]},
    "羊肉(后腿)": {t: "羊" for t in ["羊", "羊肉", "去骨羊肉", "后腿"]},
    "禽类": {t: "鸡" for t in
             ["鸡", "土鸡", "活仔鸡", "饲料鸡", "白条鸡", "集贸白条鸡",
              "集贸鸡肉", "鸡肉", "仔鸡"]},
    "鸡蛋": {"鸡蛋": "鸡蛋"},
    "水产品(不含虾蟹)": {"草鱼": "草鱼"},
    "水果": {"苹果": "苹果"},
    "糖": {"白砂糖": "糖", "食糖": "糖", "糖": "糖"},
    "乳制品": {"鲜牛奶": "牛乳", "奶制品": "牛乳", "牛奶": "牛乳"},
    "薯类(马铃薯)": {"马铃薯": "马铃薯", "土豆": "马铃薯"},
    "坚果": {"花生": "花生", "花生米": "花生"},
    "粮食(大米/面粉)": {},
    "蔬菜": {},
    "食用油(升)": {},
}

GROUP_PRICE_CATEGORIES: dict[str, list[str]] = {
    "G01": ["乳制品"],
    "G02": ["鸡蛋"],
    "G03": ["水果"],
    "G04": ["粮食(大米/面粉)"],
    "G05": ["禽类"],
    "G06": ["猪肉", "牛肉(后腿)", "羊肉(后腿)"],
    "G07": ["水产品(不含虾蟹)"],
    "G08": ["蔬菜"],
    "G09": ["糖"],
    "G10": ["薯类(马铃薯)"],
    "G11": ["食用油(升)"],
    "G12": ["坚果"],
}

GROUP_ZH = {
    "G01": "乳及乳制品", "G02": "蛋类", "G03": "水果", "G04": "谷物及豆类",
    "G05": "禽肉", "G06": "红肉（猪牛羊）", "G07": "水产品", "G08": "蔬菜",
    "G09": "糖", "G10": "薯类", "G11": "食用油", "G12": "大豆及坚果",
}


def split_tokens(text: object) -> list[str]:
    """把「口径构成」拆成食物词元，去掉集贸/超市等前缀与综合类词。"""
    if not isinstance(text, str):
        return []
    out = []
    for part in re.split(r"[+＋、,，/;；]", text):
        token = part.strip()
        if not token:
            continue
        token = re.sub(r"^(集贸|超市|农贸|散装|桶装|袋装)", "", token).strip()
        if token and token not in GENERIC:
            out.append(token)
    return out


def unmapped_tokens(category: str, composition: object, nut_foods: set[str]) -> list[str]:
    """返回该观测中在营养表里找不到对应食物的词元。"""
    aliases = CATEGORY_ALIASES.get(category, {})
    return [t for t in split_tokens(composition)
            if aliases.get(t, t) not in nut_foods]


def audit_mapping(panel: pd.DataFrame, nut_foods: set[str]) -> pd.DataFrame:
    """逐组统计口径覆盖率。panel 需含「品类」与「口径构成」两列。"""
    panel = panel.copy()
    panel["品类"] = panel["品类"].astype(str)
    rows = []
    for gid, cats in GROUP_PRICE_CATEGORIES.items():
        sub = panel[panel["品类"].isin(cats)]
        n_obs = len(sub)
        if n_obs == 0:
            rows.append({
                "group_id": gid, "group_zh": GROUP_ZH[gid],
                "price_categories": "|".join(cats), "price_observations": 0,
                "observations_fully_mapped": 0, "mapped_ratio": 0.0,
                "distinct_missing_items": 0, "missing_items": "",
                "verdict": "无价格观测",
            })
            continue
        mapped = 0
        missing: dict[str, int] = {}
        for _, row in sub.iterrows():
            bad = unmapped_tokens(row["品类"], row.get("口径构成"), nut_foods)
            if not bad:
                mapped += 1
            for token in bad:
                missing[token] = missing.get(token, 0) + 1
        ratio = mapped / n_obs
        rows.append({
            "group_id": gid, "group_zh": GROUP_ZH[gid],
            "price_categories": "|".join(cats), "price_observations": n_obs,
            "observations_fully_mapped": mapped, "mapped_ratio": round(ratio, 4),
            "distinct_missing_items": len(missing),
            "missing_items": "|".join(sorted(missing)),
            "verdict": ("口径一致" if ratio >= 0.99
                        else "部分错位" if ratio >= 0.5
                        else "严重错位"),
        })
    return pd.DataFrame(rows)
