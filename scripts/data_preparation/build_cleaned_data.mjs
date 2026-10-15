import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "D:/汇总/SRT/模型优化工作/优化模型/数据汇总（NEW）/数据汇总";
const out = "D:/汇总/SRT/outputs/01a04628-f38f-7ac3-8642-569e5fee67e1";
const sources = [
  "营养素数据.xlsx",
  "各省份消费量.xlsx",
  "零售价格表.xlsx",
  "环境足迹汇总.xlsx",
  "Chinese Food Life Cycle Assessment Database.xlsx",
];

async function inspectSources() {
  await fs.mkdir(path.join(out, "source_previews"), { recursive: true });
  for (const file of sources) {
    const blob = await FileBlob.load(path.join(root, file));
    const workbook = await SpreadsheetFile.importXlsx(blob);
    const summary = await workbook.inspect({
      kind: "workbook,sheet,table",
      maxChars: 8000,
      tableMaxRows: 5,
      tableMaxCols: 12,
      tableMaxCellChars: 100,
    });
    console.log(`SOURCE ${file}\n${summary.ndjson}`);
    const sheetInfo = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 6000 });
    console.log(`SHEETS ${file}\n${sheetInfo.ndjson}`);
    const names = [...sheetInfo.ndjson.matchAll(/"name":"([^"]+)"/g)].map((match) => match[1]);
    for (const sheetName of names) {
      const preview = await workbook.render({ sheetName, range: "A1:L40", scale: 0.8, format: "png" });
      const safe = `${path.parse(file).name}_${sheetName}`.replace(/[\\/:*?"<>|]/g, "_");
      await fs.writeFile(path.join(out, "source_previews", `${safe}.png`), new Uint8Array(await preview.arrayBuffer()));
    }
  }
}

async function inspectConsumptionFormulas() {
  const blob = await FileBlob.load(path.join(root, "各省份消费量.xlsx"));
  const workbook = await SpreadsheetFile.importXlsx(blob);
  const result = await workbook.inspect({
    kind: "formula,region",
    sheetId: "Sheet1",
    range: "A1:K95",
    maxChars: 12000,
    tableMaxRows: 20,
    tableMaxCols: 11,
  });
  console.log(result.ndjson);
}

const headerFormat = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  verticalAlignment: "center",
};

function columnLetter(index) {
  let value = index + 1;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

function toMatrix(rows, columns) {
  return rows.map((row) => columns.map((column) => row[column] ?? null));
}

function styleDataSheet(sheet, columns, rowCount, options = {}) {
  const lastCol = columnLetter(columns.length - 1);
  const lastRow = rowCount + 1;
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  sheet.getRange(`A1:${lastCol}1`).format = headerFormat;
  sheet.getRange(`A1:${lastCol}1`).format.rowHeight = 32;
  sheet.getRange(`A1:${lastCol}${lastRow}`).format.font = { name: "Aptos", size: 10 };
  sheet.getRange(`A2:${lastCol}${lastRow}`).format.verticalAlignment = "top";

  columns.forEach((column, index) => {
    const letter = columnLetter(index);
    const width = options.widths?.[column] ?? 16;
    const range = sheet.getRange(`${letter}1:${letter}${lastRow}`);
    range.format.columnWidth = Math.min(width, 52);
    if (options.wrap?.includes(column)) range.format.wrapText = true;
    if (options.numberFormats?.[column]) range.format.numberFormat = options.numberFormats[column];
  });

  const qualityIndex = columns.indexOf("quality_flag");
  if (qualityIndex >= 0 && rowCount > 0) {
    const letter = columnLetter(qualityIndex);
    const range = sheet.getRange(`${letter}2:${letter}${lastRow}`);
    range.conditionalFormats.add("containsText", { text: "missing", format: { fill: "#FEE2E2", font: { color: "#991B1B" } } });
    range.conditionalFormats.add("containsText", { text: "conflict", format: { fill: "#FEF3C7", font: { color: "#92400E" } } });
    range.conditionalFormats.add("containsText", { text: "proxy", format: { fill: "#E0E7FF", font: { color: "#3730A3" } } });
    range.conditionalFormats.add("containsText", { text: "incomplete", format: { fill: "#FEE2E2", font: { color: "#991B1B" } } });
  }
}

function addDataSheet(workbook, sheetName, rows, tableName, options = {}) {
  const sheet = workbook.worksheets.add(sheetName);
  const columns = options.columns ?? (rows.length ? Object.keys(rows[0]) : []);
  if (!columns.length) return sheet;
  sheet.getRangeByIndexes(0, 0, 1, columns.length).values = [columns];
  if (rows.length) sheet.getRangeByIndexes(1, 0, rows.length, columns.length).values = toMatrix(rows, columns);
  styleDataSheet(sheet, columns, rows.length, options);
  if (rows.length) {
    const lastCol = columnLetter(columns.length - 1);
    const table = sheet.tables.add(`A1:${lastCol}${rows.length + 1}`, true, tableName);
    table.style = "TableStyleMedium2";
    table.showBandedRows = true;
    table.showFilterButton = true;
  }
  return sheet;
}

async function buildWorkbook() {
  const payload = JSON.parse(await fs.readFile(path.join(out, "intermediate", "cleaned_data.json"), "utf8"));
  const workbook = Workbook.create();

  const readme = workbook.worksheets.add("README");
  readme.showGridLines = false;
  readme.getRange("A1:H1").merge();
  readme.getRange("A1").values = [["膳食模型清洗数据包"]];
  readme.getRange("A1:H1").format = { fill: "#0F766E", font: { bold: true, color: "#FFFFFF", size: 18 }, verticalAlignment: "center" };
  readme.getRange("A1:H1").format.rowHeight = 36;
  readme.getRange("A3:B6").values = payload.readme;
  readme.getRange("A3:A6").format = { fill: "#D1FAE5", font: { bold: true, color: "#065F46" }, verticalAlignment: "top" };
  readme.getRange("A3:B6").format.wrapText = true;
  readme.getRange("A8:C8").values = [["工作表", "内容", "建议用途"]];
  readme.getRange("A8:C8").format = headerFormat;
  const sheetIndex = [
    ["Quality_Report", "数据质量问题、证据、处理和风险", "先读"],
    ["Data_Dictionary", "字段级定义", "建模/复核"],
    ["Transformation_Log", "清洗步骤及影响", "复现清洗"],
    ["Nutrition_Long", "食品×营养项目长表", "营养矩阵"],
    ["Food_Crosswalk", "食品组和模型准入规则", "食物映射"],
    ["Consumption_Long", "地区×年份×指标长表", "消费分析"],
    ["Consumption_Coverage", "年度覆盖率", "筛选可用年份"],
    ["Price_Long", "类别×地区价格长表", "成本参数"],
    ["Price_Summary", "地区均价与全国代理", "模型价格"],
    ["Global_Env", "全球食品足迹", "环境回退"],
    ["China_LCA", "中国LCA清洗长表", "主要环境系数"],
    ["LCA_Summary", "三类LCA清洗统计", "质量审计"],
  ];
  readme.getRangeByIndexes(8, 0, sheetIndex.length, 3).values = sheetIndex;
  readme.getRange(`A9:C${8 + sheetIndex.length}`).format.borders = { preset: "insideHorizontal", style: "thin", color: "#D1D5DB" };
  readme.getRange("A3:A20").format.columnWidth = 23;
  readme.getRange("B3:B20").format.columnWidth = 58;
  readme.getRange("C8:C20").format.columnWidth = 20;
  readme.freezePanes.freezeRows(1);

  const dictionary = addDataSheet(workbook, "Data_Dictionary", payload.data_dictionary, "DataDictionaryTable", {
    widths: { sheet: 22, field: 32, definition: 62 }, wrap: ["definition"]
  });
  const transform = addDataSheet(workbook, "Transformation_Log", payload.transformations, "TransformationLogTable", {
    widths: { step: 9, dataset: 22, rule: 64, effect: 46 }, wrap: ["rule", "effect"], numberFormats: { step: "0" }
  });

  const nutritionColumns = ["nutrition_record_id", "food_name", "nutrient_category", "nutrient_name", "nutrient_name_original", "value_per_100g", "standard_unit", "basis", "value_status", "quality_flag", "unit_conflict", "source_unit", "unit_from_raw_text", "raw_value_text", "peer_rank", "peer_mean_raw", "source_file", "source_sheet", "source_row"];
  const nutrition = addDataSheet(workbook, "Nutrition_Long", payload.nutrition, "NutritionLongTable", {
    columns: nutritionColumns,
    widths: { nutrition_record_id: 15, food_name: 18, nutrient_category: 18, nutrient_name: 18, nutrient_name_original: 26, value_per_100g: 16, standard_unit: 13, basis: 23, value_status: 14, quality_flag: 30, raw_value_text: 16, peer_mean_raw: 16, source_file: 20, source_sheet: 14, source_row: 11 },
    wrap: ["nutrient_name_original", "quality_flag"],
    numberFormats: { value_per_100g: "0.0000", peer_rank: "0", source_row: "0" }
  });
  const foodCrosswalk = addDataSheet(workbook, "Food_Crosswalk", payload.food_crosswalk, "FoodCrosswalkTable", {
    widths: { food_name: 20, model_food_group: 22, eligible_for_model: 18, decision_reason: 58, nutrition_record_count: 20, nutrition_observed_count: 22, nutrition_missing_or_trace_count: 28, source_file: 20 },
    wrap: ["decision_reason"], numberFormats: { nutrition_record_count: "0", nutrition_observed_count: "0", nutrition_missing_or_trace_count: "0" }
  });

  const consumptionColumns = ["consumption_record_id", "region", "year", "metric_code", "metric_name", "food_group", "value_kg_person_year", "g_person_day", "coverage_status", "include_in_cross_region_analysis", "quality_flag", "source_value_raw", "source_file", "source_sheet", "source_row"];
  const consumption = addDataSheet(workbook, "Consumption_Long", payload.consumption, "ConsumptionLongTable", {
    columns: consumptionColumns,
    widths: { consumption_record_id: 17, region: 13, year: 10, metric_code: 34, metric_name: 34, food_group: 22, value_kg_person_year: 22, g_person_day: 18, coverage_status: 28, include_in_cross_region_analysis: 31, quality_flag: 22, source_value_raw: 17, source_file: 22, source_sheet: 14, source_row: 11 },
    wrap: ["metric_name", "coverage_status"],
    numberFormats: { year: "0", value_kg_person_year: "0.0", g_person_day: "0.00", source_row: "0" }
  });
  consumption.getRange("H2").formulas = [["=IF(G2=\"\",\"\",G2*1000/365)"]];
  consumption.getRange(`H2:H${payload.consumption.length + 1}`).fillDown();

  const consumptionCoverage = addDataSheet(workbook, "Consumption_Coverage", payload.consumption_coverage, "ConsumptionCoverageTable", {
    widths: { year: 11, expected_regions: 20, regions_with_any_value: 24, observed_cells: 18, expected_cells: 18, cell_completeness_rate: 24, analysis_status: 36 },
    numberFormats: { year: "0", expected_regions: "0", regions_with_any_value: "0", observed_cells: "0", expected_cells: "0", cell_completeness_rate: "0.0%" }
  });
  consumptionCoverage.getRange(`F2:F${payload.consumption_coverage.length + 1}`).conditionalFormats.add("colorScale", { colors: ["#FCA5A5", "#FDE68A", "#86EFAC"], thresholds: ["min", "50%", "max"] });

  const priceColumns = ["price_record_id", "category", "category_code", "region", "price_value", "standard_unit", "source_scope", "quality_flag", "source_value_raw", "source_file", "source_sheet", "source_row"];
  const prices = addDataSheet(workbook, "Price_Long", payload.prices, "PriceLongTable", {
    columns: priceColumns,
    widths: { price_record_id: 14, category: 28, category_code: 18, region: 13, price_value: 14, standard_unit: 14, source_scope: 22, quality_flag: 28, source_value_raw: 18, source_file: 20, source_sheet: 14, source_row: 11 },
    wrap: ["category", "quality_flag"], numberFormats: { price_value: "0.00", source_row: "0" }
  });
  const priceSummaryColumns = ["category", "category_code", "standard_unit", "provincial_values", "provincial_mean", "national_proxy", "recommended_value", "recommended_scope"];
  const priceSummary = addDataSheet(workbook, "Price_Summary", payload.price_summary, "PriceSummaryTable", {
    columns: priceSummaryColumns,
    widths: { category: 28, category_code: 18, standard_unit: 14, provincial_values: 19, provincial_mean: 18, national_proxy: 18, recommended_value: 20, recommended_scope: 34 },
    numberFormats: { provincial_values: "0", provincial_mean: "0.00", national_proxy: "0.00", recommended_value: "0.00" }
  });
  if (payload.price_summary.length) {
    const last = payload.price_summary.length + 1;
    priceSummary.getRange("D2").formulas = [["=COUNTIFS('Price_Long'!$B$2:$B$101,A2,'Price_Long'!$G$2:$G$101,\"province\",'Price_Long'!$E$2:$E$101,\">0\")"]];
    priceSummary.getRange("E2").formulas = [["=IF(D2=0,\"\",SUMIFS('Price_Long'!$E$2:$E$101,'Price_Long'!$B$2:$B$101,A2,'Price_Long'!$G$2:$G$101,\"province\")/D2)"]];
    priceSummary.getRange("F2").formulas = [["=IF(COUNTIFS('Price_Long'!$B$2:$B$101,A2,'Price_Long'!$G$2:$G$101,\"national_average\")=0,\"\",SUMIFS('Price_Long'!$E$2:$E$101,'Price_Long'!$B$2:$B$101,A2,'Price_Long'!$G$2:$G$101,\"national_average\")/COUNTIFS('Price_Long'!$B$2:$B$101,A2,'Price_Long'!$G$2:$G$101,\"national_average\"))"]];
    priceSummary.getRange("G2").formulas = [["=IF(E2<>\"\",E2,F2)"]];
    priceSummary.getRange("H2").formulas = [["=IF(E2<>\"\",\"mean_of_available_provinces\",\"national_proxy\")"]];
    ["D", "E", "F", "G", "H"].forEach((letter) => priceSummary.getRange(`${letter}2:${letter}${last}`).fillDown());
  }

  const globalEnv = addDataSheet(workbook, "Global_Env", payload.global_environment, "GlobalEnvTable", {
    widths: { global_env_record_id: 19, entity: 28, reference_year: 15, eutrophication_g_po4e_per_kg: 31, freshwater_l_per_kg: 24, ghg_kg_co2e_per_kg: 25, land_m2_per_kg: 20, quality_flag: 30, unit_note: 58, source_file: 22, source_sheet: 38 },
    wrap: ["quality_flag", "unit_note"], numberFormats: { reference_year: "0", eutrophication_g_po4e_per_kg: "0.00", freshwater_l_per_kg: "0.00", ghg_kg_co2e_per_kg: "0.00", land_m2_per_kg: "0.00" }
  });

  const chinaLcaColumns = ["lca_record_id", "food_code", "food_item", "food_subgroup", "food_group", "metric", "value", "standard_unit", "data_source", "journal_language", "study_year", "source_url", "is_group_average_proxy", "duplicate_count", "quality_flag", "source_file", "source_sheet", "first_source_row"];
  const chinaLca = addDataSheet(workbook, "China_LCA", payload.china_lca, "ChinaLcaTable", {
    columns: chinaLcaColumns,
    widths: { lca_record_id: 15, food_code: 15, food_item: 28, food_subgroup: 28, food_group: 22, metric: 14, value: 15, standard_unit: 20, data_source: 52, journal_language: 18, study_year: 14, source_url: 48, is_group_average_proxy: 25, duplicate_count: 18, quality_flag: 30, source_file: 36, source_sheet: 28, first_source_row: 16 },
    wrap: ["food_item", "food_subgroup", "data_source", "source_url", "quality_flag"],
    numberFormats: { value: "0.0000", study_year: "0", duplicate_count: "0", first_source_row: "0" }
  });
  const lcaSummary = addDataSheet(workbook, "LCA_Summary", payload.lca_summary, "LcaSummaryTable", {
    widths: { source_sheet: 30, metric: 15, raw_rows: 14, clean_unique_rows: 22, normalized_duplicates_collapsed: 34, missing_direct_url_rows: 28, group_average_proxy_rows: 29 },
    numberFormats: { raw_rows: "0", clean_unique_rows: "0", normalized_duplicates_collapsed: "0", missing_direct_url_rows: "0", group_average_proxy_rows: "0" }
  });

  const quality = workbook.worksheets.add("Quality_Report");
  quality.showGridLines = false;
  quality.getRange("A1:F1").merge();
  quality.getRange("A1").values = [["数据质量报告"]];
  quality.getRange("A1:F1").format = { fill: "#0F766E", font: { bold: true, color: "#FFFFFF", size: 16 }, verticalAlignment: "center" };
  quality.getRange("A3:D3").values = [["数据集", "清洗后记录数", "可用/观测记录", "核心说明"]];
  quality.getRange("A3:D3").format = headerFormat;
  quality.getRange("A4:A9").values = [["Nutrition_Long"], ["Food_Crosswalk"], ["Consumption_Long"], ["Price_Long"], ["Global_Env"], ["China_LCA"]];
  quality.getRange("B4").formulas = [[`=COUNTA('Nutrition_Long'!$A$2:$A$${payload.nutrition.length + 1})`]];
  quality.getRange("B5").formulas = [[`=COUNTA('Food_Crosswalk'!$A$2:$A$${payload.food_crosswalk.length + 1})`]];
  quality.getRange("B6").formulas = [[`=COUNTA('Consumption_Long'!$A$2:$A$${payload.consumption.length + 1})`]];
  quality.getRange("B7").formulas = [[`=COUNTA('Price_Long'!$A$2:$A$${payload.prices.length + 1})`]];
  quality.getRange("B8").formulas = [[`=COUNTA('Global_Env'!$A$2:$A$${payload.global_environment.length + 1})`]];
  quality.getRange("B9").formulas = [[`=COUNTA('China_LCA'!$A$2:$A$${payload.china_lca.length + 1})`]];
  quality.getRange("C4").formulas = [[`=COUNTIF('Nutrition_Long'!$I$2:$I$${payload.nutrition.length + 1},\"observed\")`]];
  quality.getRange("C5").formulas = [[`=COUNTA('Food_Crosswalk'!$A$2:$A$${payload.food_crosswalk.length + 1})-COUNTIF('Food_Crosswalk'!$B$2:$B$${payload.food_crosswalk.length + 1},\"alcohol\")-COUNTIF('Food_Crosswalk'!$B$2:$B$${payload.food_crosswalk.length + 1},\"other_beverage\")-COUNTIF('Food_Crosswalk'!$B$2:$B$${payload.food_crosswalk.length + 1},\"processed\")`]];
  quality.getRange("C6").formulas = [[`=COUNTIF('Consumption_Long'!$C$2:$C$${payload.consumption.length + 1},\"<=2024\")`]];
  quality.getRange("C7").formulas = [[`=COUNT('Price_Long'!$E$2:$E$${payload.prices.length + 1})`]];
  quality.getRange("C8").formulas = [[`=COUNT('Global_Env'!$D$2:$D$${payload.global_environment.length + 1})`]];
  quality.getRange("C9").formulas = [[`=COUNT('China_LCA'!$G$2:$G$${payload.china_lca.length + 1})`]];
  quality.getRange("D4:D9").values = [["Tr/缺失不填0，原文单位优先"], ["显式模型准入和排除理由"], ["2016-2024完整；2025为0/7地区"], ["省级缺失保留；全国代理独立"], ["木薯淡水0值保留并标记"], ["标准化后重复折叠；代理与缺URL标记"]];
  quality.getRange("A12:F12").values = [["严重度", "数据集", "问题", "证据", "处理", "下游风险"]];
  quality.getRange("A12:F12").format = headerFormat;
  quality.getRangeByIndexes(12, 0, payload.quality_findings.length, 6).values = payload.quality_findings.map((row) => [row.severity, row.dataset, row.issue, row.evidence, row.action, row.risk]);
  quality.getRange(`A13:F${12 + payload.quality_findings.length}`).format.wrapText = true;
  quality.getRange(`A13:A${12 + payload.quality_findings.length}`).conditionalFormats.add("containsText", { text: "High", format: { fill: "#FEE2E2", font: { bold: true, color: "#991B1B" } } });
  quality.getRange(`A13:A${12 + payload.quality_findings.length}`).conditionalFormats.add("containsText", { text: "Medium", format: { fill: "#FEF3C7", font: { bold: true, color: "#92400E" } } });
  quality.getRange("A1:A20").format.columnWidth = 18;
  quality.getRange("B1:B20").format.columnWidth = 22;
  quality.getRange("C1:C20").format.columnWidth = 38;
  quality.getRange("D1:F20").format.columnWidth = 46;
  quality.freezePanes.freezeRows(1);

  const qualityTable = quality.tables.add(`A12:F${12 + payload.quality_findings.length}`, true, "QualityFindingsTable");
  qualityTable.style = "TableStyleMedium2";

  await fs.mkdir(path.join(out, "final_previews"), { recursive: true });
  const previewRanges = {
    README: "A1:H20", Quality_Report: "A1:F19", Data_Dictionary: "A1:C40", Transformation_Log: "A1:D12",
    Nutrition_Long: "A1:S40", Food_Crosswalk: "A1:H40", Consumption_Long: "A1:O40", Consumption_Coverage: "A1:G12",
    Price_Long: "A1:L40", Price_Summary: "A1:H16", Global_Env: "A1:K40", China_LCA: "A1:R40", LCA_Summary: "A1:G6",
  };
  for (const [sheetName, range] of Object.entries(previewRanges)) {
    const preview = await workbook.render({ sheetName, range, scale: 0.8, format: "png" });
    await fs.writeFile(path.join(out, "final_previews", `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
  }

  const checks = [];
  for (const [sheetId, range] of [["Quality_Report", "A1:F19"], ["Consumption_Coverage", "A1:G12"], ["Price_Summary", "A1:H16"], ["Nutrition_Long", "A1:S8"]]) {
    const inspected = await workbook.inspect({ kind: "table", sheetId, range, include: "values,formulas", tableMaxRows: 20, tableMaxCols: 20, maxChars: 9000 });
    checks.push(`${sheetId}\n${inspected.ndjson}`);
  }
  console.log(checks.join("\n---\n"));
  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 300 }, maxChars: 5000 });
  console.log(`FORMULA_ERRORS\n${errors.ndjson}`);

  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  await xlsx.save(path.join(out, "膳食模型_清洗数据包.xlsx"));
}

if (process.argv[2] === "inspect") {
  await inspectSources();
} else if (process.argv[2] === "consumption") {
  await inspectConsumptionFormulas();
} else if (process.argv[2] === "build") {
  await buildWorkbook();
}
