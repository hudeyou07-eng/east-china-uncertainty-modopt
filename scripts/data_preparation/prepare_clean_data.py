from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(r"D:\汇总\SRT\模型优化工作\优化模型\数据汇总（NEW）\数据汇总")
OUT = Path(r"D:\汇总\SRT\outputs\01a04628-f38f-7ac3-8642-569e5fee67e1")
CSV_DIR = OUT / "clean_csv"
INTERMEDIATE = OUT / "intermediate"


def text(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    value = unicodedata.normalize("NFKC", str(value))
    return re.sub(r"\s+", " ", value).strip()


def number(value: object) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (int, float, np.number)):
        result = float(value)
        return result if math.isfinite(result) else None
    cleaned = text(value)
    if not cleaned or cleaned in {"—", "-", "Tr", "TR", "tr"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned.replace(",", ""))
    return float(match.group()) if match else None


def unit(value: object) -> str:
    value = text(value).replace("ug", "μg").replace("µg", "μg")
    mapping = {"KJ": "kJ", "G": "g", "MG": "mg", "ΜG": "μg", "%": "%"}
    return mapping.get(value.upper(), value)


def unit_from_raw(value: object) -> str:
    raw = text(value).replace("µg", "μg")
    match = re.search(r"(kJ|kcal|μg|mg|g|%)$", raw, flags=re.IGNORECASE)
    return unit(match.group(1)) if match else ""


def records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def model_group(food: str) -> tuple[str, bool, str]:
    rules = (
        ("alcohol", ("啤酒", "白酒", "苹果酒")),
        ("other_beverage", ("可口可乐", "茶汤", "苹果汁", "胡萝卜汁")),
        ("processed", ("蛋糕", "汉堡", "果泥")),
        ("grains_legumes", ("麦片", "玉米淀粉", "木薯淀粉", "艾窝窝")),
        ("tubers", ("马铃薯", "甘薯")),
        ("soybeans_nuts", ("黄豆", "黑豆", "青豆", "扁豆", "兰香豆", "花生", "白果", "菠萝蜜子", "豆奶粉")),
        ("vegetables", ("白萝卜", "茄子", "草菇", "大红菇", "海带", "胡萝卜")),
        ("fruits", ("苹果", "葡萄", "桃")),
        ("dairy", ("牛乳", "酸奶", "奶粉")),
        ("eggs", ("鸡蛋", "鸭蛋", "鹅蛋")),
        ("red_meat", ("猪", "牛", "羊")),
        ("poultry", ("鸡", "鸭", "鹅")),
        ("seafood", ("草鱼", "河虾", "河蟹")),
        ("sugar", ("糖",)),
    )
    for group, tokens in rules:
        if any(token in food for token in tokens):
            eligible = group not in {"alcohol", "other_beverage", "processed"}
            reason = "进入静态膳食优化候选集" if eligible else "酒精、含糖饮料或高度加工食品，仅保留数据不进入优化"
            return group, eligible, reason
    return "other", False, "未匹配到当前论文食物组，保留数据但不进入优化"


PRICE_CATEGORY = {
    "蔬菜": ("vegetables", "CNY/kg"),
    "猪肉": ("pork", "CNY/kg"),
    "鸡蛋": ("eggs", "CNY/kg"),
    "水产品(不含虾蟹)": ("seafood", "CNY/kg"),
    "水果": ("fruits", "CNY/kg"),
    "禽类": ("poultry", "CNY/kg"),
    "粮食平均价(大米,面粉)": ("grains", "CNY/kg"),
    "牛肉(后腿)": ("beef", "CNY/kg"),
    "羊肉(后腿)": ("mutton", "CNY/kg"),
    "食用油(升)": ("oils", "CNY/L"),
    "糖": ("sugar", "CNY/kg"),
    "乳制品": ("dairy", "CNY/kg"),
    "坚果": ("nuts", "CNY/kg"),
    "薯类(马铃薯)": ("tubers", "CNY/kg"),
}


CONSUMPTION_METRICS = {
    "粮食": ("grain_consumption", "grains_legumes"),
    "食用油": ("oil_consumption", "oils"),
    "蔬菜及食用菌": ("vegetable_mushroom_consumption", "vegetables"),
    "肉类": ("meat_consumption", "red_meat"),
    "禽类": ("poultry_consumption", "poultry"),
    "水产品": ("aquatic_food_consumption", "seafood"),
    "蛋类": ("egg_consumption", "eggs"),
    "奶类": ("dairy_consumption", "dairy"),
    "鲜瓜果": ("fresh_fruit_consumption", "fruits"),
    "食糖": ("sugar_consumption", "sugar"),
}


def clean_nutrition() -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    source = pd.read_excel(ROOT / "营养素数据.xlsx")
    provisional = []
    for source_row, row in source.iterrows():
        source_u = unit(row.get("单位"))
        raw_u = unit_from_raw(row.get("含量原文"))
        raw_value = text(row.get("含量原文"))
        trace = source_u.lower() == "tr" or raw_value.lower() == "tr" or text(row.get("含量")).lower() == "tr"
        numeric = number(row.get("含量"))
        nutrient_original = text(row.get("营养项目"))
        nutrient_cn = re.sub(r"\([^)]*\)", "", nutrient_original).strip()
        provisional.append({
            "food_name": text(row.get("食品名称")),
            "nutrient_category": text(row.get("营养分类")),
            "nutrient_name": nutrient_cn,
            "nutrient_name_original": nutrient_original,
            "value_per_100g": numeric,
            "source_unit": source_u,
            "unit_from_raw_text": raw_u,
            "raw_value_text": raw_value,
            "value_status": "trace" if trace else "observed" if numeric is not None else "missing",
            "peer_rank": number(row.get("同类排名")),
            "peer_mean_raw": text(row.get("同类均值")),
            "source_file": "营养素数据.xlsx",
            "source_sheet": "Sheet1",
            "source_row": int(source_row + 2),
        })
    frame = pd.DataFrame(provisional)
    unit_candidates = frame.loc[
        frame["unit_from_raw_text"].ne("") | frame["source_unit"].isin(["%", "g", "mg", "μg", "kJ", "kcal"])
    ].copy()
    unit_candidates["candidate_unit"] = unit_candidates["unit_from_raw_text"].where(
        unit_candidates["unit_from_raw_text"].ne(""), unit_candidates["source_unit"]
    )
    dominant = unit_candidates.groupby("nutrient_name")["candidate_unit"].agg(
        lambda s: s.value_counts().index[0] if not s.empty else ""
    )
    frame["standard_unit"] = frame["unit_from_raw_text"]
    frame.loc[frame["standard_unit"].eq(""), "standard_unit"] = frame.loc[
        frame["standard_unit"].eq(""), "source_unit"
    ]
    invalid_unit = ~frame["standard_unit"].isin(["%", "g", "mg", "μg", "kJ", "kcal"])
    frame.loc[invalid_unit, "standard_unit"] = frame.loc[invalid_unit, "nutrient_name"].map(dominant).fillna("")
    frame["unit_conflict"] = (
        frame["source_unit"].isin(["%", "g", "mg", "μg", "kJ", "kcal"])
        & frame["unit_from_raw_text"].ne("")
        & frame["source_unit"].ne(frame["unit_from_raw_text"])
    )
    frame["basis"] = np.where(frame["nutrient_name"].eq("食部"), "percent_edible", "per_100g_edible_portion")
    frame["quality_flag"] = "ok"
    frame.loc[frame["value_status"].eq("trace"), "quality_flag"] = "trace_not_zero"
    frame.loc[frame["value_status"].eq("missing"), "quality_flag"] = "missing_value"
    frame.loc[frame["unit_conflict"], "quality_flag"] = "unit_conflict_raw_text_preferred"
    frame.insert(0, "nutrition_record_id", [f"N{i:04d}" for i in range(1, len(frame) + 1)])
    frame = frame[[
        "nutrition_record_id", "food_name", "nutrient_category", "nutrient_name", "nutrient_name_original",
        "value_per_100g", "standard_unit", "basis", "value_status", "quality_flag", "unit_conflict",
        "source_unit", "unit_from_raw_text", "raw_value_text", "peer_rank", "peer_mean_raw",
        "source_file", "source_sheet", "source_row",
    ]]

    foods = []
    for food in sorted(frame["food_name"].unique()):
        group, eligible, reason = model_group(food)
        foods.append({
            "food_name": food,
            "model_food_group": group,
            "eligible_for_model": eligible,
            "decision_reason": reason,
            "nutrition_record_count": int((frame["food_name"] == food).sum()),
            "nutrition_observed_count": int(((frame["food_name"] == food) & frame["value_status"].eq("observed")).sum()),
            "nutrition_missing_or_trace_count": int(((frame["food_name"] == food) & ~frame["value_status"].eq("observed")).sum()),
            "source_file": "营养素数据.xlsx",
        })
    crosswalk = pd.DataFrame(foods)

    findings = [
        {
            "severity": "High",
            "dataset": "Nutrition_Long",
            "issue": "含量字段存在缺失或痕量值",
            "evidence": f"共{int((frame['value_status'] != 'observed').sum())}条为missing/trace；未将Tr替换为0",
            "action": "保留空值并用value_status区分missing与trace",
            "risk": "错误填0会低估营养摄入",
        },
        {
            "severity": "High",
            "dataset": "Nutrition_Long",
            "issue": "单位列与原文后缀存在冲突",
            "evidence": f"检测到{int(frame['unit_conflict'].sum())}条冲突",
            "action": "标准单位优先采用含量原文中的明确后缀，并保留原单位与冲突标志",
            "risk": "μg误作g会产生百万倍量纲错误",
        },
    ]
    return frame, crosswalk, findings


def clean_consumption() -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    raw = pd.read_excel(ROOT / "各省份消费量.xlsx", header=None)
    rows = []
    for region_row in raw.index[raw[0].astype(str).str.startswith("地区：")]:
        region = text(raw.iloc[region_row, 0]).replace("地区:", "").replace("地区：", "").strip()
        header_row = region_row + 2
        year_cols = {}
        for col in range(1, raw.shape[1]):
            header = text(raw.iloc[header_row, col])
            match = re.search(r"(20\d{2})", header)
            if match:
                year_cols[int(match.group(1))] = col
        for metric_row in range(header_row + 1, min(header_row + 11, raw.shape[0])):
            metric_name = text(raw.iloc[metric_row, 0])
            metric_key = next((token for token in CONSUMPTION_METRICS if token in metric_name), "")
            metric_code, food_group = CONSUMPTION_METRICS.get(metric_key, ("unmapped", "unmapped"))
            for year in range(2016, 2026):
                col = year_cols.get(year)
                raw_value = raw.iloc[metric_row, col] if col is not None else None
                value = number(raw_value)
                rows.append({
                    "region": region,
                    "year": year,
                    "metric_code": metric_code,
                    "metric_name": metric_name.replace("(千克)", "").strip(),
                    "food_group": food_group,
                    "value_kg_person_year": value,
                    "g_person_day": value * 1000.0 / 365.0 if value is not None else None,
                    "coverage_status": "complete_period" if year <= 2024 else "incomplete_2025_period",
                    "include_in_cross_region_analysis": bool(value is not None and year <= 2024),
                    "quality_flag": "ok" if value is not None and year <= 2024 else "incomplete_2025" if year == 2025 else "missing_value",
                    "source_value_raw": text(raw_value),
                    "source_file": "各省份消费量.xlsx",
                    "source_sheet": "Sheet1",
                    "source_row": int(metric_row + 1),
                })
    frame = pd.DataFrame(rows).sort_values(["region", "year", "metric_code"]).reset_index(drop=True)
    if frame.duplicated(["region", "year", "metric_code"]).any():
        raise ValueError("消费数据在地区×年份×指标粒度存在重复")
    frame.insert(0, "consumption_record_id", [f"C{i:04d}" for i in range(1, len(frame) + 1)])
    coverage = frame.groupby("year").agg(
        expected_regions=("region", "nunique"),
        regions_with_any_value=("value_kg_person_year", lambda s: int(s.notna().groupby(frame.loc[s.index, "region"]).any().sum())),
        observed_cells=("value_kg_person_year", lambda s: int(s.notna().sum())),
        expected_cells=("value_kg_person_year", "size"),
    ).reset_index()
    coverage["cell_completeness_rate"] = coverage["observed_cells"] / coverage["expected_cells"]
    coverage["analysis_status"] = np.where(coverage["year"].eq(2025), "exclude_cross_region_incomplete", "usable")
    findings = [{
        "severity": "High",
        "dataset": "Consumption_Long",
        "issue": "2025年地区覆盖不完整",
        "evidence": f"2025年仅{int(coverage.loc[coverage['year'].eq(2025),'regions_with_any_value'].iloc[0])}/7个地区有值",
        "action": "保留2025原值但标记incomplete_2025，并排除跨地区比较",
        "risk": "直接横向比较会把缺失误判为低消费",
    }]
    return frame, coverage, findings


def clean_prices() -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    raw = pd.read_excel(ROOT / "零售价格表.xlsx")
    category_col = raw.columns[5]
    province_cols = list(raw.columns[6:])
    rows = []
    for source_row, row in raw.iterrows():
        category = text(row[category_col])
        category_code, standard_unit = PRICE_CATEGORY.get(category, ("unmapped", "unknown"))
        national_values = []
        for col in province_cols:
            raw_value = text(row[col])
            if "全国" in raw_value:
                parsed = number(raw_value)
                if parsed is not None:
                    national_values.append(parsed)
        for col in province_cols:
            region = text(col)
            raw_value = text(row[col])
            value = None if "全国" in raw_value else number(row[col])
            rows.append({
                "category": category,
                "category_code": category_code,
                "region": region,
                "price_value": value,
                "standard_unit": standard_unit,
                "source_scope": "province",
                "quality_flag": "ok" if value is not None else "missing_provincial_price",
                "source_value_raw": raw_value,
                "source_file": "零售价格表.xlsx",
                "source_sheet": "Sheet1",
                "source_row": int(source_row + 2),
            })
        if national_values:
            rows.append({
                "category": category,
                "category_code": category_code,
                "region": "全国",
                "price_value": float(np.mean(national_values)),
                "standard_unit": standard_unit,
                "source_scope": "national_average",
                "quality_flag": "national_proxy",
                "source_value_raw": ";".join(str(v) for v in national_values),
                "source_file": "零售价格表.xlsx",
                "source_sheet": "Sheet1",
                "source_row": int(source_row + 2),
            })
    frame = pd.DataFrame(rows)
    frame.insert(0, "price_record_id", [f"P{i:03d}" for i in range(1, len(frame) + 1)])
    summary = frame.groupby(["category", "category_code", "standard_unit"], as_index=False).agg(
        provincial_values=("price_value", lambda s: int(s[frame.loc[s.index, "source_scope"].eq("province")].notna().sum())),
        provincial_mean=("price_value", lambda s: float(s[frame.loc[s.index, "source_scope"].eq("province")].mean()) if s[frame.loc[s.index, "source_scope"].eq("province")].notna().any() else None),
        national_proxy=("price_value", lambda s: float(s[frame.loc[s.index, "source_scope"].eq("national_average")].mean()) if s[frame.loc[s.index, "source_scope"].eq("national_average")].notna().any() else None),
    )
    summary["recommended_value"] = summary["provincial_mean"].fillna(summary["national_proxy"])
    summary["recommended_scope"] = np.where(summary["provincial_mean"].notna(), "mean_of_available_provinces", "national_proxy")
    findings = [{
        "severity": "Medium",
        "dataset": "Price_Long",
        "issue": "省级价格存在缺失，坚果和薯类仅有全国均价",
        "evidence": f"98个省级槽位中缺失{int((frame['source_scope'].eq('province') & frame['price_value'].isna()).sum())}个；另有{int(frame['source_scope'].eq('national_average').sum())}条全国代理",
        "action": "全国值从江苏列移出并单列为region=全国；不冒充江苏价格",
        "risk": "把全国值当成江苏会扭曲区域成本比较",
    }]
    return frame, summary, findings


def clean_global_environment() -> tuple[pd.DataFrame, list[dict]]:
    raw = pd.read_excel(ROOT / "环境足迹汇总.xlsx")
    frame = pd.DataFrame({
        "entity": raw["Entity"].map(text),
        "reference_year": pd.to_numeric(raw["Year"], errors="coerce"),
        "eutrophication_g_po4e_per_kg": pd.to_numeric(raw["Eutrophying emissions per kilogram"], errors="coerce"),
        "freshwater_l_per_kg": pd.to_numeric(raw["Freshwater withdrawals per kilogram"], errors="coerce"),
        "ghg_kg_co2e_per_kg": pd.to_numeric(raw["Greenhouse gas emissions per kilogram"], errors="coerce"),
        "land_m2_per_kg": pd.to_numeric(raw["Land use per kilogram"], errors="coerce"),
    })
    frame["quality_flag"] = np.where(frame["freshwater_l_per_kg"].eq(0), "zero_freshwater_check_source", "ok")
    frame["unit_note"] = "单位按项目内Poore/Nemecek衍生表解释：g PO4e、L、kg CO2e、m2，均为每kg食物"
    frame["source_file"] = "环境足迹汇总.xlsx"
    frame["source_sheet"] = "eutrophying-emissions-per-kilog"
    frame.insert(0, "global_env_record_id", [f"G{i:02d}" for i in range(1, len(frame) + 1)])
    findings = [{
        "severity": "Medium",
        "dataset": "Global_Env",
        "issue": "木薯淡水取用值为0",
        "evidence": f"非正值共{int((frame[['eutrophication_g_po4e_per_kg','freshwater_l_per_kg','ghg_kg_co2e_per_kg','land_m2_per_kg']] <= 0).sum().sum())}个，定位为Cassava淡水取用",
        "action": "保留原值并增加zero_freshwater_check_source标志，不自动改写",
        "risk": "若0代表缺失而非真实零值，会低估木薯水足迹",
    }]
    return frame, findings


def clean_china_lca() -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    path = ROOT / "Chinese Food Life Cycle Assessment Database.xlsx"
    specs = {
        "Greenhouse Gas Emission": ("ghg", "kg CO2e/kg food"),
        "Water Use": ("freshwater", "m3/kg food"),
        "Land Use": ("land", "m2/kg food"),
    }
    cleaned = []
    sheet_summary = []
    for sheet, (metric, standard_unit) in specs.items():
        raw = pd.read_excel(path, sheet_name=sheet)
        raw["_source_row"] = np.arange(2, len(raw) + 2)
        content = raw.drop(columns=["_source_row"])
        raw = raw.loc[content.apply(lambda col: col.map(lambda value: text(value) != "")).any(axis=1)].copy()
        value_col = next(col for col in raw.columns if "kg food as consumed" in col)
        base = pd.DataFrame({
            "food_code": raw.iloc[:, 0].map(lambda v: text(v).replace(".0", "")),
            "food_item": raw["Food item"].map(text),
            "food_subgroup": raw["Food sub-group"].map(lambda v: text(v).replace("，", ", ").lower()),
            "food_group": raw["Food group"].map(text),
            "metric": metric,
            "value": pd.to_numeric(raw[value_col], errors="coerce"),
            "standard_unit": standard_unit,
            "data_source": raw["Data source"].map(text),
            "journal_language": raw["Language of journal"].map(text),
            "study_year": pd.to_numeric(raw.get("Year of study (not year of journal publication)"), errors="coerce") if "Year of study (not year of journal publication)" in raw.columns else np.nan,
            "source_url": raw["Direct URL to data"].map(text),
            "source_sheet": sheet,
            "source_row": raw["_source_row"].to_numpy(),
        })
        key_cols = ["food_code", "food_item", "food_subgroup", "food_group", "metric", "value", "standard_unit", "data_source", "journal_language", "study_year", "source_url"]
        grouped = base.groupby(key_cols, dropna=False, as_index=False).agg(
            duplicate_count=("source_row", "size"),
            first_source_row=("source_row", "min"),
        )
        grouped["is_group_average_proxy"] = grouped["data_source"].str.lower().str.contains("average of food group", na=False)
        grouped["quality_flag"] = "ok"
        grouped.loc[grouped["source_url"].eq(""), "quality_flag"] = "missing_direct_url"
        grouped.loc[grouped["is_group_average_proxy"], "quality_flag"] = "group_average_proxy"
        grouped.loc[grouped["duplicate_count"].gt(1), "quality_flag"] = grouped.loc[grouped["duplicate_count"].gt(1), "quality_flag"].where(
            grouped.loc[grouped["duplicate_count"].gt(1), "quality_flag"].ne("ok"), "exact_duplicate_collapsed"
        )
        grouped["source_file"] = "Chinese Food Life Cycle Assessment Database.xlsx"
        grouped["source_sheet"] = sheet
        cleaned.append(grouped)
        sheet_summary.append({
            "source_sheet": sheet,
            "metric": metric,
            "raw_rows": int(len(raw)),
            "clean_unique_rows": int(len(grouped)),
            "normalized_duplicates_collapsed": int(len(raw) - len(grouped)),
            "missing_direct_url_rows": int(grouped["source_url"].eq("").sum()),
            "group_average_proxy_rows": int(grouped["is_group_average_proxy"].sum()),
        })
    frame = pd.concat(cleaned, ignore_index=True)
    frame.insert(0, "lca_record_id", [f"L{i:05d}" for i in range(1, len(frame) + 1)])
    frame = frame[[
        "lca_record_id", "food_code", "food_item", "food_subgroup", "food_group", "metric", "value",
        "standard_unit", "data_source", "journal_language", "study_year", "source_url", "is_group_average_proxy",
        "duplicate_count", "quality_flag", "source_file", "source_sheet", "first_source_row",
    ]]
    summary = pd.DataFrame(sheet_summary)
    findings = [{
        "severity": "High",
        "dataset": "China_LCA",
        "issue": "存在精确重复记录和大量缺少直接URL的组均值代理",
        "evidence": f"文本标准化后合并重复{int(summary['normalized_duplicates_collapsed'].sum())}条；清洗后缺直接URL{int(summary['missing_direct_url_rows'].sum())}条",
        "action": "标准化后重复记录折叠并记录duplicate_count；组均值代理与缺URL分别标记",
        "risk": "未去重会让重复研究在中位数/均值汇总中获得额外权重",
    }]
    return frame, summary, findings


def dictionary_rows() -> list[dict]:
    schemas = {
        "Nutrition_Long": {
            "nutrition_record_id": "清洗后营养记录唯一ID", "food_name": "食品中文名称", "nutrient_category": "原营养分类",
            "nutrient_name": "去除英文括注后的营养项目", "nutrient_name_original": "原始营养项目名称", "value_per_100g": "每100g可食部的数值；Tr和缺失保持空值",
            "standard_unit": "从含量原文后缀优先恢复的标准单位", "basis": "数值计量基础", "value_status": "observed/trace/missing",
            "quality_flag": "数据质量标志", "unit_conflict": "源单位与原文后缀是否冲突", "source_unit": "原单位列",
            "unit_from_raw_text": "从含量原文解析的单位", "raw_value_text": "原始含量文本", "peer_rank": "同类排名",
            "peer_mean_raw": "同类均值原文", "source_file": "源文件", "source_sheet": "源工作表", "source_row": "源行号",
        },
        "Consumption_Long": {
            "consumption_record_id": "消费记录唯一ID", "region": "省或直辖市", "year": "年份", "metric_code": "标准指标代码",
            "metric_name": "指标中文名称", "food_group": "模型食物组", "value_kg_person_year": "kg/人/年原始值",
            "g_person_day": "由kg/人/年换算的g/人/日", "coverage_status": "年度覆盖状态", "include_in_cross_region_analysis": "是否可用于跨地区比较",
            "quality_flag": "数据质量标志", "source_value_raw": "源单元格文本", "source_file": "源文件", "source_sheet": "源工作表", "source_row": "源行号",
        },
        "Price_Long": {
            "price_record_id": "价格记录唯一ID", "category": "价格类别", "category_code": "标准类别代码", "region": "地区或全国",
            "price_value": "价格数值", "standard_unit": "CNY/kg或CNY/L", "source_scope": "province或national_average",
            "quality_flag": "数据质量标志", "source_value_raw": "源单元格文本", "source_file": "源文件", "source_sheet": "源工作表", "source_row": "源行号",
        },
        "Global_Env": {
            "global_env_record_id": "全球足迹记录唯一ID", "entity": "英文食品实体", "reference_year": "参考年",
            "eutrophication_g_po4e_per_kg": "富营养化g PO4e/kg", "freshwater_l_per_kg": "淡水取用L/kg",
            "ghg_kg_co2e_per_kg": "温室气体kg CO2e/kg", "land_m2_per_kg": "土地m2/kg", "quality_flag": "数据质量标志",
            "unit_note": "单位解释", "source_file": "源文件", "source_sheet": "源工作表",
        },
        "China_LCA": {
            "lca_record_id": "LCA记录唯一ID", "food_code": "中国食物成分表编码", "food_item": "英文食品名称", "food_subgroup": "标准化英文子组",
            "food_group": "英文大类", "metric": "ghg/freshwater/land", "value": "足迹值", "standard_unit": "标准单位",
            "data_source": "文献来源", "journal_language": "文献语言", "study_year": "研究年份（若源表提供）", "source_url": "直接URL",
            "is_group_average_proxy": "是否为食物组均值代理", "duplicate_count": "该清洗记录合并的完全相同源行数", "quality_flag": "数据质量标志",
            "source_file": "源文件", "source_sheet": "源工作表", "first_source_row": "首个源行号",
        },
    }
    rows = []
    for sheet, mapping in schemas.items():
        for field, definition in mapping.items():
            rows.append({"sheet": sheet, "field": field, "definition": definition})
    return rows


def main() -> None:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    INTERMEDIATE.mkdir(parents=True, exist_ok=True)
    nutrition, crosswalk, f1 = clean_nutrition()
    consumption, consumption_coverage, f2 = clean_consumption()
    prices, price_summary, f3 = clean_prices()
    global_env, f4 = clean_global_environment()
    china_lca, lca_summary, f5 = clean_china_lca()

    datasets = {
        "nutrition": nutrition,
        "food_crosswalk": crosswalk,
        "consumption": consumption,
        "consumption_coverage": consumption_coverage,
        "prices": prices,
        "price_summary": price_summary,
        "global_environment": global_env,
        "china_lca": china_lca,
        "lca_summary": lca_summary,
    }
    for name, frame in datasets.items():
        frame.to_csv(CSV_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")

    transformations = [
        {"step": 1, "dataset": "Nutrition_Long", "rule": "Unicode NFKC、空白和换行标准化；保留原字段", "effect": "名称和文本可稳定匹配"},
        {"step": 2, "dataset": "Nutrition_Long", "rule": "—/空白转为null；Tr标记为trace且不填0", "effect": "避免低估营养摄入"},
        {"step": 3, "dataset": "Nutrition_Long", "rule": "源单位与含量原文冲突时优先原文后缀", "effect": "修复μg被误列为g的量纲风险"},
        {"step": 4, "dataset": "Consumption_Long", "rule": "7个地区块和2016-2025宽表展开为地区×年份×指标长表", "effect": "形成700条唯一记录"},
        {"step": 5, "dataset": "Consumption_Long", "rule": "2025覆盖不完整，保留原值但排除跨地区分析", "effect": "不把缺失误判为低消费"},
        {"step": 6, "dataset": "Price_Long", "rule": "全国均价从江苏列中分离为region=全国；省级缺失保留null", "effect": "防止全国代理被误作江苏价格"},
        {"step": 7, "dataset": "Global_Env", "rule": "统一为g PO4e/kg、L/kg、kg CO2e/kg、m2/kg", "effect": "列名显式包含单位"},
        {"step": 8, "dataset": "China_LCA", "rule": "三张指标表合并为长表；Unicode/空白标准化后相同记录折叠并记录duplicate_count", "effect": "防止重复研究获得额外汇总权重"},
        {"step": 9, "dataset": "Food_Crosswalk", "rule": "按论文食物组建立显式映射和模型准入标志", "effect": "保留排除理由，避免静默删行"},
    ]
    findings = f1 + f2 + f3 + f4 + f5
    payload = {
        "generated_at": "2026-08-28",
        "source_root": str(ROOT),
        "readme": [
            ["用途", "模型输入数据的清洗、标准化与审计；原始工作簿未修改"],
            ["粒度", "营养=食品×营养项目；消费=地区×年份×指标；价格=类别×地区；LCA=食品×来源×指标"],
            ["关键原则", "缺失不填0、Tr不填0、单位写入列名、全国代理不冒充省级值、完全重复折叠且留计数"],
            ["模型边界", "清洗提高可用性但不补造缺失DRI、生物多样性系数或MAgPIE动态反馈"],
        ],
        "quality_findings": findings,
        "transformations": transformations,
        "data_dictionary": dictionary_rows(),
        **{name: records(frame) for name, frame in datasets.items()},
    }
    (INTERMEDIATE / "cleaned_data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "nutrition_rows": len(nutrition),
        "foods": len(crosswalk),
        "consumption_rows": len(consumption),
        "price_rows": len(prices),
        "global_env_rows": len(global_env),
        "china_lca_rows": len(china_lca),
        "lca_duplicates_collapsed": int(lca_summary["normalized_duplicates_collapsed"].sum()),
        "quality_findings": len(findings),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
