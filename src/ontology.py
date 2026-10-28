"""食物组本体与冻结口径的单一来源。

本模块是仓库内唯一的组定义。此前 ``scripts/build_group_audit.py`` 与
``scripts/scenario_decision_space.py`` 各自硬编码了一份 ONTOLOGY，且价格品类名
对不上（``水产品`` vs ``水产品(不含虾蟹)``、``食糖`` vs ``糖``、``大豆|坚果`` vs
``坚果``），导致两份审计结果不可比。现统一到这里。

任何对组定义、硬营养素清单或门槛常数的修改，必须同时提升 ``ONTOLOGY_VERSION``，
并在 ``data/processed/model_manifest.json`` 中留下新版本记录。
"""

from __future__ import annotations

ONTOLOGY_VERSION = "onto-v1.0.0"

# 硬营养素：进入机会约束、必须 100% 覆盖
HARD_NUTRIENTS = [
    "能量", "蛋白质", "脂肪", "碳水化合物",
    "钙", "铁", "锌", "硒",
    "核黄素", "硫胺素", "烟酸",
]

# 环境指标：中国 LCA 与全球表各一套
ENV_METRICS = ["ghg", "freshwater", "land"]
GLOBAL_ENV_METRICS = [
    "ghg_kg_co2e_per_kg",
    "freshwater_l_per_kg",
    "land_m2_per_kg",
    "eutrophication_g_po4e_per_kg",
]

# 组级准入门槛（冻结值，改动需升版本）
MIN_PRICE_REGIONS = 3
MIN_PRICE_OBSERVATIONS = 18
MIN_CONSUMPTION_REGIONS = 7

# 单元级覆盖率门槛（省 × 组）：9 年里至少要有几年有价，才算「组价」而非「某一年」。
# 取 5 与 src/masking.py 的 `min_series_observations` 同一约定（序列过半）。
# 这是**披露性**门槛，不是准入：源数据本身缺年，FAIL 也修不出来，
# 所以 G3 把它报成 WARN（见 scripts/check_contract_gates.py）。
MIN_CELL_PRICE_YEARS = 5

# group_id -> 各数据域中的原始标签。
# price_categories 的取值必须与 price_panel_clean.xlsx 的「品类」列逐字一致，
# 否则 price_stats 会静默匹配到 0 条观测。
ONTOLOGY: list[dict] = [
    {
        "group_id": "G01", "group_en": "dairy", "group_zh": "乳及乳制品",
        "price_categories": ["乳制品"],
        "consumption_groups": ["dairy"],
        "nutrition_groups": ["dairy"],
        "lca_groups": ["Dairy"],
        "global_env_entities": ["Milk", "Cheese"],
        "notes": "",
    },
    {
        "group_id": "G02", "group_en": "eggs", "group_zh": "蛋类",
        "price_categories": ["鸡蛋"],
        "consumption_groups": ["eggs"],
        "nutrition_groups": ["eggs"],
        "lca_groups": ["Eggs"],
        "global_env_entities": ["Eggs"],
        "notes": "",
    },
    {
        "group_id": "G03", "group_en": "fruits", "group_zh": "水果",
        "price_categories": ["水果"],
        "consumption_groups": ["fruits"],
        "nutrition_groups": ["fruits"],
        "lca_groups": ["Fruit"],
        "global_env_entities": [
            "Apples", "Bananas", "Berries & Grapes", "Citrus Fruit", "Other Fruit",
        ],
        "notes": "",
    },
    {
        "group_id": "G04", "group_en": "grains_legumes", "group_zh": "谷物及豆类",
        "price_categories": ["粮食(大米/面粉)"],
        "consumption_groups": ["grains_legumes"],
        "nutrition_groups": ["grains_legumes"],
        "lca_groups": ["Cereals", "Legumes"],
        "global_env_entities": [
            "Barley", "Maize", "Rice", "Wheat & Rye", "Oatmeal", "Peas", "Other Pulses",
        ],
        "notes": "",
    },
    {
        "group_id": "G05", "group_en": "poultry", "group_zh": "禽肉",
        "price_categories": ["禽类"],
        "consumption_groups": ["poultry"],
        "nutrition_groups": ["poultry"],
        "lca_groups": ["Poultry"],
        "global_env_entities": ["Poultry Meat"],
        "notes": "",
    },
    {
        "group_id": "G06", "group_en": "red_meat", "group_zh": "红肉（猪牛羊）",
        "price_categories": ["猪肉", "牛肉(后腿)", "羊肉(后腿)"],
        "consumption_groups": ["red_meat"],
        "nutrition_groups": ["red_meat"],
        "lca_groups": ["Meat"],
        "global_env_entities": [
            "Beef (beef herd)", "Beef (dairy herd)", "Lamb & Mutton", "Pig Meat",
        ],
        # 环境表的实体粒度比价格/营养更细：牛肉分成肉牛与奶牛两个 herd。
        # 若直接扁平化等权，牛肉会拿到 2/4 = 50% 权重，而价格与营养维度里牛肉只占 1/3。
        # 声明品类子结构后，聚合改为「先品类内平均、再品类间等权」，与另两个维度对齐。
        "global_env_subgroups": {
            "beef": ["Beef (beef herd)", "Beef (dairy herd)"],
            "lamb": ["Lamb & Mutton"],
            "pork": ["Pig Meat"],
        },
        "notes": "唯一由三个价格品类合成的组；环境实体需按品类子结构聚合，不能扁平等权",
    },
    {
        "group_id": "G07", "group_en": "seafood", "group_zh": "水产品",
        "price_categories": ["水产品(不含虾蟹)"],
        "consumption_groups": ["seafood"],
        "nutrition_groups": ["seafood"],
        "lca_groups": ["Aquatic products"],
        "global_env_entities": ["Fish (farmed)", "Prawns (farmed)"],
        "notes": "价格口径排除虾蟹，营养篮子仅含淡水鱼，边界不一致",
    },
    {
        "group_id": "G08", "group_en": "vegetables", "group_zh": "蔬菜",
        "price_categories": ["蔬菜"],
        "consumption_groups": ["vegetables"],
        "nutrition_groups": ["vegetables"],
        "lca_groups": ["Vegetables"],
        "global_env_entities": [
            "Brassicas", "Onions & Leeks", "Other Vegetables", "Tomatoes", "Root Vegetables",
        ],
        "notes": "",
    },
    {
        "group_id": "G09", "group_en": "sugar", "group_zh": "糖",
        "price_categories": ["糖"],
        "consumption_groups": ["sugar"],
        "nutrition_groups": ["sugar"],
        "lca_groups": ["Sugars and preserves"],
        "global_env_entities": ["Beet Sugar", "Cane Sugar"],
        "notes": "",
    },
    {
        "group_id": "G10", "group_en": "tubers", "group_zh": "薯类",
        "price_categories": ["薯类(马铃薯)"],
        "consumption_groups": [],
        "nutrition_groups": ["tubers"],
        "lca_groups": ["Tubers, starches"],
        "global_env_entities": ["Potatoes", "Cassava"],
        "notes": "消费表无 tubers 分组，组级消费基线缺失",
    },
    {
        "group_id": "G11", "group_en": "oils", "group_zh": "食用油",
        "price_categories": ["食用油(升)"],
        "consumption_groups": ["oils"],
        "nutrition_groups": [],
        "lca_groups": ["Fats and oils", "fats and oils"],
        "global_env_entities": ["soybean oil"],
        "notes": "营养表无 oils 分组，硬营养素系数全缺",
    },
    {
        "group_id": "G12", "group_en": "soybeans_nuts", "group_zh": "大豆及坚果",
        "price_categories": ["坚果"],
        "consumption_groups": [],
        "nutrition_groups": ["soybeans_nuts"],
        "lca_groups": ["Nuts and seeds"],
        "global_env_entities": ["Groundnuts", "Nuts", "Tofu", "Soy milk"],
        "notes": "价格与消费均仅覆盖坚果，大豆既无价格观测也无消费基线",
    },
]

GROUP_ZH: dict[str, str] = {g["group_id"]: g["group_zh"] for g in ONTOLOGY}
GROUP_EN: dict[str, str] = {g["group_id"]: g["group_en"] for g in ONTOLOGY}
GROUP_PRICE_CATEGORIES: dict[str, list[str]] = {
    g["group_id"]: g["price_categories"] for g in ONTOLOGY
}

# 消费表 food_group 标签 -> group_id
CONSUMPTION_TO_GROUP: dict[str, str] = {
    label: g["group_id"] for g in ONTOLOGY for label in g["consumption_groups"]
}

# 营养交叉表 model_food_group -> group_id
NUTRITION_TO_GROUP: dict[str, str] = {
    label: g["group_id"] for g in ONTOLOGY for label in g["nutrition_groups"]
}

# 省份全称 -> 价格面板使用的简称。价格面板与 B1 校准结果统一用简称，
# 消费表用全称，落盘前必须归一。
PROVINCE_CANONICAL: dict[str, str] = {
    "上海市": "上海", "上海": "上海",
    "江苏省": "江苏", "江苏": "江苏",
    "浙江省": "浙江", "浙江": "浙江",
    "安徽省": "安徽", "安徽": "安徽",
    "福建省": "福建", "福建": "福建",
    "江西省": "江西", "江西": "江西",
    "山东省": "山东", "山东": "山东",
}

PROVINCES: list[str] = ["上海", "江苏", "浙江", "安徽", "福建", "江西", "山东"]

# 预注册的三种膳食情景
SCENARIOS: list[str] = ["HEAL_base", "CDG", "EAT"]


def canonical_province(name: object) -> str:
    """把省份名归一为价格面板使用的简称；未知名称原样返回。"""
    text = str(name).strip()
    return PROVINCE_CANONICAL.get(text, text)
