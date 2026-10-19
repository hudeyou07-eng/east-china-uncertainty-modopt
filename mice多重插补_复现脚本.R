# ============================================================
# 食品批发价缺失值 —— MICE 多重插补复现脚本（R / mice 包）
# 方法：PMM 预测均值匹配，m=5，maxit=20，seed=20261019
# 说明：按品类分别建立跨省面板，避免不同价格水平互相污染；
#       仅插补单点/局部随机缺失，结构性缺失保留空白。
# 运行：Rscript mice多重插补_复现脚本.R （需先 install.packages("mice")）
# ============================================================
library(readxl)
library(mice)

years <- paste0(2016:2024, "年")
f1 <- "D:/汇总/SRT/数据汇总/华东华中7省食品零售价_商务预报_分省批发价.xlsx"
provs <- c("江苏","上海","浙江","山东","安徽","江西","福建")

# 读取某品类的跨省面板（行=省，列=年份）
build_panel <- function(cat, drop_prov = NULL) {
  rows <- list()
  for (sn in provs) {
    d <- read_excel(f1, sheet = sn, skip = 1)
    i <- which(d$品类 == cat)[1]
    if (is.na(i)) next
    rows[[length(rows)+1]] <- data.frame(
      省份 = sn, matrix(as.numeric(d[i, years]), nrow = 1), check.names = FALSE)
  }
  df <- do.call(rbind, rows); names(df)[2:10] <- years
  if (!is.null(drop_prov)) df <- df[!(df$省份 %in% drop_prov), ]
  rownames(df) <- NULL; df
}

# 对单个面板跑 mice，返回每个缺失格的 5 次插补均值/范围
impute_panel <- function(df, cat) {
  set.seed(20261019)
  imp <- mice(df[, years], m = 5, maxit = 20, method = "pmm",
              seed = 20261019, print = FALSE)
  comps <- lapply(1:5, function(k) complete(imp, k))
  nap <- which(is.na(df[, years]), arr.ind = TRUE)
  out <- list()
  for (idx in seq_len(nrow(nap))) {
    r <- nap[idx,"row"]; c <- nap[idx,"col"]; yr <- years[c]
    vals <- sapply(comps, function(cc) cc[r, yr])
    out[[length(out)+1]] <- data.frame(
      省份 = df$省份[r], 品类 = cat, 年份 = yr,
      均值 = round(mean(vals), 2),
      五次 = paste(round(vals, 4), collapse = "/"),
      最小 = round(min(vals), 2), 最大 = round(max(vals), 2))
  }
  do.call(rbind, out)
}

# 牛肉/羊肉排除福建整行结构性全缺；鸡蛋7省全留
res <- rbind(
  impute_panel(build_panel("牛肉(后腿)", drop_prov = "福建"), "牛肉(后腿)"),
  impute_panel(build_panel("羊肉(后腿)", drop_prov = "福建"), "羊肉(后腿)"),
  impute_panel(build_panel("鸡蛋"), "鸡蛋")
)
print(res)
