"""按 docs/EXPERIMENT_PLAN.md 第 3 节逐条验收 B2 数据合同。

"文件存在" 不等于 "gate 通过"。本脚本把 Plan 第 3 节表格里每个文件的
gate 条件翻译成可执行断言，输出 PASS / FAIL 与具体反例行。

七个 gate：
    G1 group_audit.csv          每个 include=1 的组通过全部覆盖规则
    G2 baseline_consumption.csv 无负值；主结论组有可识别基线
    G3 group_prices.csv         只有定义匹配的最终组单位价格
    G4 nutrients.csv            所有硬营养素覆盖率 100%
    G5 environment.csv          所有主目标覆盖率 100%，系统边界统一
    G6 decision_bounds.csv      有限、冻结、lower <= upper
    G7 model_manifest.json      hashes / units / ontology_version / timestamp 齐备

用法：
    python scripts/check_contract_gates.py

退出码 0 表示 7/7 通过，1 表示存在 FAIL。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ontology import (  # noqa: E402
    ENV_METRICS,
    HARD_NUTRIENTS,
    MIN_CELL_PRICE_YEARS,
    MIN_PRICE_OBSERVATIONS,
    MIN_PRICE_REGIONS,
    ONTOLOGY,
    PROVINCES,
)

PROCESSED = ROOT / "data" / "processed"

results: list[dict] = []


def record(
    gate: str,
    name: str,
    ok: bool,
    detail: str,
    warnings: list[str] | None = None,
) -> None:
    """登记一条 gate 结果。

    ``ok`` 只反映**可以修的违规**（非正值、缺价、口径退化……）。
    ``warnings`` 用于记录**改不了的数据限制**（如源数据本身缺年）——
    这类问题不该让 gate 变 FAIL（否则只会被整体豁免），但也不能静默通过，
    必须显式打印并进 JSON，逼着论文数据节去披露。
    """
    warnings = warnings or []
    results.append({
        "gate": gate, "file": name, "ok": bool(ok),
        "detail": detail, "warnings": warnings,
    })
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {gate} {name}\n       {detail}")
    for w in warnings:
        print(f"       [WARN] {w}")


def check_group_audit() -> None:
    path = PROCESSED / "group_audit.csv"
    audit = pd.read_csv(path, encoding="utf-8-sig")
    included = audit[audit["include"].astype(bool)]

    gate_cols = ["price_gate", "consumption_gate", "nutrition_gate", "environment_gate"]
    bad = included[included[gate_cols].astype(int).sum(axis=1) < len(gate_cols)]
    detail = (
        f"include=1 共 {len(included)} 组 {sorted(included['group_id'])}；"
        f"四门未全通过 {len(bad)} 组"
    )
    if len(bad):
        detail += f" -> {bad['group_id'].tolist()}"
    record("G1", "group_audit.csv", len(bad) == 0 and len(included) > 0, detail)


def check_baseline() -> None:
    base = pd.read_csv(PROCESSED / "baseline_consumption.csv", encoding="utf-8-sig")
    neg = base[base["value_g_day"].notna() & (base["value_g_day"] < 0)]
    audit = pd.read_csv(PROCESSED / "group_audit.csv", encoding="utf-8-sig")
    main_groups = set(audit.loc[audit["include"].astype(bool), "group_id"])

    has_base = (
        base[base["group_id"].isin(main_groups) & base["observed"]]
        .groupby("group_id")
        .size()
    )
    no_base = sorted(main_groups - set(has_base.index))
    ok = len(neg) == 0 and not no_base
    detail = (
        f"{len(base)} 行 / 观测 {int(base['observed'].sum())} / "
        f"省 {base['province'].nunique()} / 组 {base['group_id'].nunique()}；"
        f"负值 {len(neg)} 行；主结论组无基线 {no_base}"
    )
    record("G2", "baseline_consumption.csv", ok, detail)


def check_prices() -> None:
    px = pd.read_csv(PROCESSED / "group_prices.csv", encoding="utf-8-sig")
    audit = pd.read_csv(PROCESSED / "group_audit.csv", encoding="utf-8-sig")
    included = set(audit.loc[audit["include"].astype(bool), "group_id"])

    sub = px[px["group_id"].isin(included)]
    nonpos = sub[sub["observed"] & ~(sub["price_cny_kg"] > 0)]
    missing_cells = sub[sub["observed"] & sub["price_cny_kg"].isna()]

    per_group = (
        sub[sub["observed"]]
        .groupby("group_id")
        .agg(n_obs=("price_cny_kg", "size"), n_region=("province", "nunique"))
    )
    thin = per_group[
        (per_group["n_obs"] < MIN_PRICE_OBSERVATIONS) | (per_group["n_region"] < MIN_PRICE_REGIONS)
    ]

    bad_prov = sorted(set(px["province"]) - set(PROVINCES))

    # 多品类组的主口径不得退化为"取某一品类"（等价于取最低价，会系统性低估组价）。
    #
    # **2026-10-27 修订（CHANGELOG §31）**：`collapsed` 只在**完整结构行**上算。
    # 旧版把 `structure_weighted_partial` 的行也算进来，而那些行恰恰就是
    # 「缺品类、权重被归一」的行，等于用被缺陷污染的指标去检查缺陷——
    # 实测 23/23 的「等于最低价」全部来自 `pork=1.000`，排除后是 0.000。
    multi = sub[sub["n_categories"] > 1]
    observed_multi = multi[multi["observed"]]
    degenerate = multi[multi["aggregation"] == "dominant_category"]
    strict = observed_multi[
        ~observed_multi["aggregation"].str.startswith("structure_weighted_partial")
    ]
    collapsed = (
        (strict["price_cny_kg"].round(6) == strict["price_min"].round(6)).mean()
        if len(strict)
        else 0.0
    )

    # 单元级覆盖率：组级 `thin` 看不见「某省某组只有 1 年观测」。
    # 门槛取 5 年，与 src/masking.py 的 `min_series_observations` 同一约定。
    cells = (
        sub.groupby(["province", "group_id"])
        .agg(n_years=("year", "size"), n_price_years=("price_cny_kg", lambda s: int(s.notna().sum())))
        .reset_index()
    )
    thin_cells = cells[cells["n_price_years"] < MIN_CELL_PRICE_YEARS]
    no_obs_cells = cells[cells["n_price_years"].eq(0)]

    ok = (
        nonpos.empty
        and missing_cells.empty
        and thin.empty
        and not bad_prov
        and degenerate.empty
        and collapsed < 0.5
    )
    detail = (
        f"主结论组 {sorted(included)}；非正值 {len(nonpos)}；"
        f"observed=True 但缺价 {len(missing_cells)}；"
        f"组级低于门槛(obs>={MIN_PRICE_OBSERVATIONS}, 省>={MIN_PRICE_REGIONS}) {thin.index.tolist()}；"
        f"省份异常 {bad_prov}；多品类组取单品类 {len(degenerate)} 行；"
        f"完整结构行的「等于最低价」比例 {collapsed:.0%}（需 <50%，"
        f"分母 {len(strict)} 行、已排除部分结构行）"
    )
    warnings: list[str] = []
    if len(thin_cells):
        worst = (
            thin_cells.sort_values("n_price_years")
            .head(6)
            .apply(lambda r: f"{r['province']}/{r['group_id']}={int(r['n_price_years'])}年", axis=1)
            .tolist()
        )
        warnings.append(
            f"单元级覆盖率不足：{len(thin_cells)}/{len(cells)} 个 (省,组) 单元有价年份 <"
            f"{MIN_CELL_PRICE_YEARS}（共 9 年）。最薄的：{', '.join(worst)}。"
            f"这些单元的组价是「若干年均值」，不是 9 年均价，论文数据节必须披露。"
        )
    if len(no_obs_cells):
        names = [
            f"{r['province']}/{r['group_id']}"
            for _, r in no_obs_cells.iterrows()
        ]
        warnings.append(
            f"零观测单元 {len(no_obs_cells)} 个（价格全靠批发价桥接回退）：{names}"
        )

    # 上面的检查只覆盖 `include=1`（合同口径 K=4）。**模型实际用的是 decision_scope**，
    # 而 k6_price 比 K=4 多了 G04 与 G07——恰好是覆盖率最薄的两个组。
    # 只按 K=4 报覆盖率会低估问题，所以再按决策口径报一次。
    try:
        from src.b2_problem import Contract

        cfg = yaml.safe_load((ROOT / "configs" / "default.yaml").read_text(encoding="utf-8"))
        scope = (cfg.get("optimization") or {}).get("decision_scope")
        contract = Contract.load_scope(scope)
        usable, _ = contract.complete_provinces()
        dsub = px[px["group_id"].isin(contract.groups) & px["province"].isin(usable)]
        dcells = (
            dsub.groupby(["province", "group_id"])
            .agg(n_price_years=("price_cny_kg", lambda s: int(s.notna().sum())))
            .reset_index()
        )
        dthin = dcells[dcells["n_price_years"] < MIN_CELL_PRICE_YEARS]
        if len(dthin):
            worst = (
                dthin.sort_values("n_price_years")
                .head(6)
                .apply(
                    lambda r: f"{r['province']}/{r['group_id']}={int(r['n_price_years'])}年",
                    axis=1,
                )
                .tolist()
            )
            warnings.append(
                f"决策口径 {scope}（{len(contract.groups)} 组 × {len(usable)} 省 = "
                f"{len(dcells)} 单元）覆盖率不足 {len(dthin)} 个：{', '.join(worst)}。"
                f"这一组数字才是模型实际用到的；上面 K=4 的那条是合同口径。"
            )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"决策口径覆盖率未能检查（{type(exc).__name__}: {exc}）")

    record("G3", "group_prices.csv", ok, detail, warnings)


def check_nutrients() -> None:
    nut = pd.read_csv(PROCESSED / "nutrients.csv", encoding="utf-8-sig")
    audit = pd.read_csv(PROCESSED / "group_audit.csv", encoding="utf-8-sig")
    included = set(audit.loc[audit["include"].astype(bool), "group_id"])

    sub = nut[nut["group_id"].isin(included)]
    missing_nutrients = sorted(set(HARD_NUTRIENTS) - set(sub["nutrient"]))
    uncovered = sub[sub["nutrient"].isin(HARD_NUTRIENTS) & sub["value_per_kg"].isna()]
    incomplete = sub[~sub["coverage_complete"].astype(bool)]

    ok = not missing_nutrients and uncovered.empty and incomplete.empty
    detail = (
        f"主结论组 {sorted(included)} × 硬营养素 {len(HARD_NUTRIENTS)}；"
        f"缺营养素列 {missing_nutrients}；值缺失 {len(uncovered)} 格；"
        f"coverage_complete=False {len(incomplete)} 格"
    )
    if len(incomplete):
        detail += f" -> {incomplete[['group_id', 'nutrient']].head(5).values.tolist()}"
    record("G4", "nutrients.csv", ok, detail)


def check_environment() -> None:
    env = pd.read_csv(PROCESSED / "environment.csv", encoding="utf-8-sig")
    audit = pd.read_csv(PROCESSED / "group_audit.csv", encoding="utf-8-sig")
    included = set(audit.loc[audit["include"].astype(bool), "group_id"])

    sub = env[(env["dataset"] == "global_pn") & (env["group_id"].isin(included))]
    piv = sub.pivot_table(index="group_id", columns="impact", values="value_per_kg")
    missing_impact = sorted(set(ENV_METRICS) - set(sub["impact"]))
    holes = piv[piv[list(set(ENV_METRICS) & set(piv.columns))].isna().any(axis=1)]
    boundaries = sorted(sub["boundary"].unique())
    nonpos = sub[~(sub["value_per_kg"] > 0)]

    ok = not missing_impact and holes.empty and len(boundaries) == 1 and nonpos.empty
    detail = (
        f"主口径 global_pn / 主结论组 {sorted(included)}；缺指标 {missing_impact}；"
        f"缺格组 {holes.index.tolist()}；边界口径 {boundaries}（需唯一）；非正值 {len(nonpos)}"
    )
    record("G5", "environment.csv", ok, detail)


def check_decision_bounds() -> None:
    db = pd.read_csv(PROCESSED / "decision_bounds.csv", encoding="utf-8-sig")
    nonfinite = db[~(db["lower_g_day"].notna() & db["upper_g_day"].notna())]
    inverted = db[db["lower_g_day"] > db["upper_g_day"]]
    negative = db[(db["lower_g_day"] < 0) | (db["upper_g_day"] < 0)]
    dup = db.duplicated(subset=["province", "scenario", "group_id"]).sum()

    bad_type = db[~db["bound_type"].isin(["single", "joint"])] if "bound_type" in db else db

    # 联合约束的 group_id 形如 G05+G06，展开后每个省×情景必须覆盖全部 12 组
    all_groups = [g["group_id"] for g in ONTOLOGY]
    uncovered = []
    for (prov, sc), sub in db.groupby(["province", "scenario"]):
        covered: set[str] = set()
        for label in sub["group_id"]:
            covered.update(str(label).split("+"))
        missing = sorted(set(all_groups) - covered)
        if missing:
            uncovered.append(f"{prov}/{sc}:{missing}")

    n_joint = int((db["bound_type"] == "joint").sum()) if "bound_type" in db else 0

    ok = (
        nonfinite.empty
        and inverted.empty
        and negative.empty
        and dup == 0
        and bad_type.empty
        and not uncovered
    )
    detail = (
        f"{len(db)} 行；情景 {sorted(db['scenario'].unique())}；单组 {len(db) - n_joint} / 联合 {n_joint}；"
        f"非有限 {len(nonfinite)}；lower>upper {len(inverted)}；负值 {len(negative)}；"
        f"重复键 {dup}；非法 bound_type {len(bad_type)}；未覆盖组合 {uncovered if uncovered else '无'}"
    )
    record("G6", "decision_bounds.csv", ok, detail)


def check_manifest() -> None:
    man = json.loads((PROCESSED / "model_manifest.json").read_text(encoding="utf-8"))
    required = [
        "manifest_version",
        "generated_at_utc",
        "ontology_version",
        "weights_version",
        "units",
        "artifacts",
        "contract_status",
    ]
    absent = [k for k in required if k not in man]
    status = man.get("contract_status", {})
    gate_ready = bool(status.get("gate_ready"))

    # 逐条核对 manifest 记录的 hash 与磁盘现值一致
    import hashlib

    drift = []
    for name, rec in man.get("artifacts", {}).items():
        path = PROCESSED / name
        if not path.exists():
            drift.append(f"{name}: 缺失")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != rec["sha256"]:
            drift.append(f"{name}: hash 漂移")

    ok = not absent and gate_ready and not drift
    detail = (
        f"缺字段 {absent}；contract_status.gate_ready={gate_ready}；"
        f"hash 漂移 {drift if drift else '无'}；"
        f"记录 {len(man.get('artifacts', {}))} 个产物"
    )
    record("G7", "model_manifest.json", ok, detail)


def run_all(verbose: bool = True) -> list[dict]:
    """执行七条 gate，返回结果列表。verbose=False 时静默，供 build_contract_files 调用。"""
    global results
    results = []
    checks = [
        check_group_audit,
        check_baseline,
        check_prices,
        check_nutrients,
        check_environment,
        check_decision_bounds,
        check_manifest,
    ]
    if not verbose:
        import contextlib
        import io

        sink = io.StringIO()
        with contextlib.redirect_stdout(sink):
            for fn in checks:
                fn()
        return results

    print("=" * 78)
    print("B2 数据合同 gate 验收（EXPERIMENT_PLAN.md §3）")
    print("=" * 78)
    for fn in checks:
        fn()
    return results


def write_report(results: list[dict], path: Path) -> int:
    passed = sum(1 for r in results if r["ok"])
    path.write_text(
        json.dumps(
            {
                "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                "passed": passed,
                "total": len(results),
                "all_passed": passed == len(results),
                "gates": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return passed


def main() -> int:
    results = run_all(verbose=True)
    passed = write_report(results, PROCESSED / "contract_gate_report.json")
    print("=" * 78)
    print(f"结果：{passed}/{len(results)} gate 通过")
    print(f"报告：{(PROCESSED / 'contract_gate_report.json').relative_to(ROOT)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
