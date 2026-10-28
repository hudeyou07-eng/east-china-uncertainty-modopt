"""生成 B2 数据合同中的冻结记录（docs/EXPERIMENT_PLAN.md 第 3 节，共七个文件）。

本脚本不生产全部数据，而是做两件事：

1. 调用 build_group_audit 生成两个预注册口径的审计表（primary / sensitivity）；
2. 汇总 data/processed/ 下七个合同文件的 sha256 与字节数，写入
   model_manifest.json，并按第 9 节要求落一个 R002 run 目录。

七个文件由以下脚本分别生产：

    group_audit.csv / group_audit_k3_strict.csv
    group_audit_sensitivity_c0.90.csv / group_audit_trace_c0.95.csv
                                                          <- 本脚本调用 build_audit
    baseline_consumption.csv                             <- 本脚本 build_baseline_consumption
    group_prices.csv                                     <- scripts/build_group_prices.py
    nutrients.csv                                        <- scripts/build_nutrients.py
    environment.csv                                      <- scripts/build_environment.py
    decision_bounds.csv                                  <- scripts/build_decision_bounds.py
    model_manifest.json                                  <- 本脚本

若某个产物缺失，本脚本只告警、不阻断，并把缺口写进 manifest 的
contract_status，避免用不完整的合同启动 B2。

用法：
    python scripts/build_contract_files.py
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_group_audit import build_audit  # noqa: E402
from src.ontology import (  # noqa: E402
    CONSUMPTION_TO_GROUP,
    ONTOLOGY_VERSION,
    PROVINCES,
    canonical_province,
)

DATA = ROOT / "data" / "input"
PROCESSED = ROOT / "data" / "processed"
CONFIG = ROOT / "configs" / "default.yaml"

# 预注册的冻结口径。
#
# primary 从 K=3 改为 K=4（纳入 G06 红肉）的原因见 docs/EXPERIMENT_PLAN.md 修订 R-2026-10-26-b：
# CDG 情景的约束对象是「畜禽肉合计 40-75 g」，而 7 省中 6 省的红肉单独消费已达
# 82.9–94.4 g/天，畜禽肉合计 91.8–130.6 g/天，全部超过上限 75。
# 若红肉不作为决策变量（固定在实际基线），禽肉须满足的剩余区间为负数（如上海 [-46.5, -11.5]），
# 即 CDG 情景在 K=3 下不可满足，而不是「缺一条约束」。
# 因此红肉必须进入模型才能让 CDG 情景成立。
# 代价：需把痕量（Tr）视为有效近零，G06 羊肉碳水化合物为痕量，否则营养门 10/11 不过。
# 原 K=3 口径保留为 preregistered_k3，用于对照与偏离说明。
SCOPES = {
    "primary": {
        "label": "trace_as_near_zero_all_four_domains",
        "description": (
            "痕量（value_status=trace）视为真实近零并按 0 计入，"
            "营养硬系数全或无规则（min_cell_coverage=1.0）"
        ),
        "params": {"trace_as_valid": True, "min_cell_coverage": 1.0, "min_mapping_ratio": None},
        "audit_file": "group_audit.csv",
        "role": "main",
    },
    "preregistered_k3": {
        "label": "strict_no_trace_k3",
        "description": (
            "原始预注册口径：痕量不算有效观测，红肉因 10/11 被排除，K=3。"
            "该口径下 CDG 畜禽肉约束不可满足，仅作对照"
        ),
        "params": {"trace_as_valid": False, "min_cell_coverage": 1.0, "min_mapping_ratio": None},
        "audit_file": "group_audit_k3_strict.csv",
        "role": "preregistered_reference",
    },
    "sensitivity_cell_coverage_090": {
        "label": "cell_coverage_0.90",
        "description": "组内营养格子可用比例 >= 0.90，用于检验阈值选择对结论范围的影响",
        "params": {"trace_as_valid": False, "min_cell_coverage": 0.90, "min_mapping_ratio": None},
        "audit_file": "group_audit_sensitivity_c0.90.csv",
        "role": "sensitivity",
    },
    # 2026-10-27 修订后的**决策口径**（不是新的合同文件口径）。
    #
    # 正式合同文件仍是 group_audit.csv（Plan 第 3 节七个文件之一，K=4）；
    # 本口径只改变「哪些组进入优化模型」，因此只替换审计表，其余六个合同文件不变
    # （实测与 data/processed 逐字节相同，见 CHANGELOG §20）。
    #
    # 为什么从 K=4 改为 K=6：R307b 的 2×2 因子分解证明
    #   - G04（谷物豆类）解决山东的硬不可行（碳水 offset 275.75 -> 39.55）；
    #   - G07（水产品）恢复价格传导（D1 相对 D0 的位移从 0/7 省变为 3/6 省）；
    #   - 两者都与 K 的大小无关（K=5 只加 G04 时价格传导仍为 0）。
    # 即「价格传导」这条目标链需要 G07 作为替代品才能显形，K=4 下不存在可行替代。
    #
    # 代价（必须随结果报告）：上海在 G07 上源表整块缺失（price_source=missing，
    # 批发价源亦无水产品品类，仓库内无法桥接），故本口径只覆盖 6 省。
    "k6_price": {
        "label": "trace_as_near_zero_plus_coverage_0.95",
        "description": (
            "决策口径（2026-10-27 修订）：痕量视为近零，营养硬系数按组内格子比例 >= 0.95。"
            "纳入 G04 谷物豆类与 G07 水产品，K=6。"
            "相对正式合同口径 K=4 的变化是『G04 解决山东硬不可行 + G07 恢复价格传导』，"
            "不是单纯的阈值放松"
        ),
        "params": {"trace_as_valid": True, "min_cell_coverage": 0.95, "min_mapping_ratio": None},
        "audit_file": "group_audit_trace_c0.95.csv",
        "role": "decision_main",
    },
}

UNITS = {
    "price": "CNY/kg",
    "consumption": "g/person/day",
    "nutrient": "per kg food (converted from per 100 g)",
    "environment": "per kg food",
    "year": "calendar year",
    "province": "prefecture-level province, canonical short name",
}

# EXPERIMENT_PLAN.md 第 3 节明确列出的七个合同文件（顺序即合同顺序）。
PLAN_SEVEN = [
    "group_audit.csv",
    "baseline_consumption.csv",
    "group_prices.csv",
    "nutrients.csv",
    "environment.csv",
    "decision_bounds.csv",
    "model_manifest.json",
]
# 不在 Plan 七个之列、但同样随合同一起冻结的附属产物。
CONTRACT_EXTRA = [
    "ontology.csv",  # crosswalk 本体，group_audit 的生成依据
    "group_audit_k3_strict.csv",  # 原预注册 K=3 口径，用于偏离对照
    "group_audit_sensitivity_c0.90.csv",  # 预注册敏感性口径
    "group_audit_trace_c0.95.csv",  # 2026-10-27 决策口径 k6_price 的审计表
]
CONTRACT_FILES = PLAN_SEVEN + CONTRACT_EXTRA

# EXPERIMENT_PLAN.md 第 3 节列名 -> 实际列名。合同语义一致，命名保持向后兼容。
PLAN_COLUMN_MAPPING = {
    "group_id": "group_id",
    "label": "group_zh",
    "baseline_source": "baseline_source",
    "price_obs": "price_observations",
    "price_regions": "price_regions",
    "nutrient_coverage": "nutrition_min_hard_coverage",
    "environment_coverage": "environment_gate（布尔）；细分见 lca_metrics_count / global_env_metrics_count",
    "include": "include",
    "reason": "reason",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(path: Path) -> dict:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def build_baseline_consumption() -> pd.DataFrame:
    """组级消费基线。

    只保留 include_in_cross_region_analysis=True 的记录（2016–2024 完整期），
    2025 不完整期整段剔除。observed 为 False 表示该格在源表即为空。
    """
    raw = pd.read_csv(DATA / "clean_tables" / "consumption.csv", encoding="utf-8-sig")
    usable = raw[raw["include_in_cross_region_analysis"].astype(bool)].copy()

    usable["province"] = usable["region"].map(canonical_province)
    usable["group_id"] = usable["food_group"].map(CONSUMPTION_TO_GROUP)

    unknown_prov = sorted(set(usable["province"]) - set(PROVINCES))
    if unknown_prov:
        raise ValueError(f"省份名未能归一: {unknown_prov}")
    unmapped = usable[usable["group_id"].isna()]
    if not unmapped.empty:
        raise ValueError(f"存在未映射的消费组: {sorted(unmapped['food_group'].unique())}")

    out = usable.rename(columns={"g_person_day": "value_g_day"})
    out["observed"] = out["value_g_day"].notna()
    out = out[["province", "year", "group_id", "value_g_day", "observed"]]
    out["year"] = out["year"].astype(int)
    out = out.sort_values(["province", "year", "group_id"]).reset_index(drop=True)

    if (out["value_g_day"].dropna() < 0).any():
        raise ValueError("消费基线出现负值")
    return out


def write_run_record(manifest: dict, artifacts: dict, audit: pd.DataFrame) -> Path:
    """按 EXPERIMENT_PLAN.md 第 9 节写 R002 的 run 目录。

    ``audit`` 是正式合同文件 ``group_audit.csv``（K=4）。决策口径（K=6）另行
    记在 ``metrics["decision_scope"]``，两者不可混为一谈：前者是合同，后者是模型输入。
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ROOT / "outputs" / f"R002_group_freeze_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    gate_cols = ["price_gate", "consumption_gate", "nutrition_gate", "environment_gate"]
    ranked = audit.copy()
    ranked["gates_passed"] = ranked[gate_cols].astype(int).sum(axis=1)
    rank_rows = (
        ranked.sort_values(["include", "gates_passed", "group_id"], ascending=[False, False, True])
        [["group_id", "group_zh", "gates_passed", "include"]]
        .to_dict("records")
    )

    metrics = {
        "run_id": "R002",
        "milestone": "M0",
        "purpose": "food-group freeze",
        "ontology_version": manifest["ontology_version"],
        "ontology_groups": int(len(audit)),
        "gate_pass_rank": rank_rows,
        "scopes": {
            key: {
                "role": spec["role"],
                "included_k": spec["included_k"],
                "included_group_ids": spec["included_group_ids"],
                "excluded_k": len(spec["excluded_group_ids"]),
            }
            for key, spec in manifest["frozen_scopes"].items()
        },
        # 决策口径与合同口径是两件事：合同文件固定为 K=4，模型按 decision_scope 取组。
        "decision_scope": manifest["decision_scope"],
        "coverage": {
            "price_gate_pass": int(audit["price_gate"].sum()),
            "consumption_gate_pass": int(audit["consumption_gate"].sum()),
            "nutrition_gate_pass": int(audit["nutrition_gate"].sum()),
            "environment_gate_pass": int(audit["environment_gate"].sum()),
            "mapping_verdict": audit["mapping_verdict"].value_counts().to_dict(),
        },
        "artifacts": artifacts,
        "contract_status": manifest["contract_status"],
        "gate_verification": manifest.get("gate_verification", {}),
    }

    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "command": "python scripts/build_contract_files.py",
                "scopes": manifest["frozen_scopes"],
                "decision_scope": manifest["decision_scope"]["scope"],
                "units": manifest["units"],
                "seed": manifest["seed"],
                "config_sha256": manifest["config_sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "environment.json").write_text(
        json.dumps(manifest["environment"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "DONE").write_text("", encoding="utf-8")

    # gate 报告随 run 一起留档，保证 run 目录自包含、可独立复核
    gate_report = PROCESSED / "contract_gate_report.json"
    if gate_report.exists():
        (run_dir / "contract_gate_report.json").write_text(
            gate_report.read_text(encoding="utf-8"), encoding="utf-8"
        )

    print(f"[run] wrote {run_dir.relative_to(ROOT)}")
    return run_dir


def summarize_environment(artifacts: dict) -> dict:
    """environment.csv 的口径说明。

    两套数据集系统边界不同，不能混用：global_pn 是 farm-to-retail 统一口径，
    china_lca 的边界在原文中各异且未逐篇标注，只能做对照。
    """
    if "environment.csv" not in artifacts:
        return {"status": "missing"}
    env = pd.read_csv(PROCESSED / "environment.csv", encoding="utf-8-sig")

    per_dataset = {}
    for name, sub in env.groupby("dataset"):
        per_dataset[name] = {
            "rows": int(len(sub)),
            "impacts": sorted(sub["impact"].unique().tolist()),
            "boundary": sorted(sub["boundary"].unique().tolist()),
            "n_sources": int(sub["source"].nunique()),
            "aggregation": sub["aggregation"].value_counts().to_dict(),
            "proxy_rows": int((sub["n_group_average_proxy"] > 0).sum()),
            "proxy_records": int(sub["n_group_average_proxy"].sum()),
            "complete_groups": int(
                sub.groupby("group_id")["impact"].nunique().eq(len(sub["impact"].unique())).sum()
            ),
            "units": sub["unit"].unique().tolist(),
        }

    return {
        "primary_dataset": "global_pn",
        "primary_rationale": (
            "OWID / Poore & Nemecek (2018) 全球表 12 组 × 4 指标零缺失，"
            "同一文献同一系统边界，满足 Plan 第 3 节『系统边界统一』的要求"
        ),
        "secondary_dataset": "china_lca",
        "secondary_rationale": (
            "中国本地化文献边界各异（部分 cradle-to-gate、部分未声明），"
            "boundary 列标为 unspecified_pending_review，仅作区域对照，不进入主目标"
        ),
        "aggregation_rule": {
            "global_pn": (
                "G06 红肉按消费结构加权（猪肉 0.788 / 牛肉 0.136 / 羊肉 0.076）；"
                "其余组为实体扁平等权。依据是组级系数应满足 p̄ = Σ p_i·q_i/T，"
                "权重等于消费份额，见 data/input/external/meat_consumption_structure.csv"
            ),
            "china_lca": "中位数，对同组同指标的多个文献值稳健",
            "why_structure_weighted_for_G06": (
                "等权隐含『三品类等量消费』，实际猪肉占近八成。等权把红肉 ghg 高估 81%"
                "（39.47 vs 21.75 kg CO2e/kg），并同时虚高 land（137.7 vs 66.9 m2/kg）。"
                "三个维度的权重语义必须一致，否则同一个组会在成本端便宜、在排放端昂贵"
            ),
            "weights_source": (
                "国家统计局 2023 年肉类产量 + 海关总署 2023 年进口量，"
                "表观消费 = 产量 + 进口，忽略出口与库存变化"
            ),
            "column": "aggregation 列逐行标注实际使用的方法",
        },
        "known_limitations": [
            "G07 水产（Fish (farmed) 13.63 与 Prawns (farmed) 26.87）仍为实体扁平等权，"
            "平均成 20.25 kg CO2e/kg；虾的排放高于鱼，而鱼类消费量更大，故 20.25 可能偏高。"
            "水产消费结构缺少可靠公开依据，不编造权重",
            "G06 权重为全国口径，未按省拆分。分省可得的是产量而非消费量，"
            "产量反映生产布局（山东产猪外调、上海不产猪但消费量大），按省套用会把结构算反",
            "权重为 2023 单年；2019–2020 非洲猪瘟为异常年已排除，2016 与 2023 产量结构接近（82.2% vs 81.9%）",
        ],
        "interval_semantics": (
            "lower / upper 始终取组内实体的 min / max，表达『实体间差异』，"
            "不随聚合权重改变，可直接用于 B2 的口径敏感性"
        ),
        "unit_conversions": {"freshwater": "m3 -> L（×1000）"},
        "datasets": per_dataset,
        "note": (
            "proxy_rows / proxy_records 表示该行/该指标由组内多个食物取平均得到，"
            "而非组级单一实体；china_lca 大量行依赖组均值代理，这是它只作对照的另一个理由"
        ),
    }


def summarize_decision_bounds(
    artifacts: dict,
    decision_groups: list[str] | None = None,
    provinces: list[str] | None = None,
) -> dict:
    """decision_bounds.csv 的口径说明，含联合约束的设计理由。

    ``decision_groups`` 传入决策口径的入组集合时，会**逐省逐情景实际核对**
    联合约束的成员是否齐备，而不是只写一段说明文字——说明文字会和口径脱钩，
    核对结果不会。
    """
    if "decision_bounds.csv" not in artifacts:
        return {"status": "missing"}
    db = pd.read_csv(PROCESSED / "decision_bounds.csv", encoding="utf-8-sig")

    per_scenario = {}
    for name, sub in db.groupby("scenario"):
        n_joint = int((sub["bound_type"] == "joint").sum())
        per_scenario[name] = {
            "rows": int(len(sub)),
            "single_rows": int(len(sub)) - n_joint,
            "joint_rows": n_joint,
            "joint_labels": sorted(sub.loc[sub["bound_type"] == "joint", "group_id"].unique().tolist()),
            "source": sorted(sub["source"].unique().tolist()),
            "provinces": int(sub["province"].nunique()),
            "bounded": bool(
                (sub["lower_g_day"] >= 0).all() and (sub["lower_g_day"] <= sub["upper_g_day"]).all()
            ),
        }

    joint_check: dict = {"decision_groups": decision_groups, "status": "not_checked"}
    if decision_groups is not None:
        applied, skipped = [], []
        scoped = db if provinces is None else db[db["province"].isin(provinces)]
        for (prov, scen), sub in scoped.groupby(["province", "scenario"]):
            for label in sub.loc[sub["bound_type"].eq("joint"), "group_id"].unique():
                members = [m for m in str(label).split("+") if m]
                rec = {"province": prov, "scenario": scen, "constraint": label, "members": members}
                (applied if set(members).issubset(set(decision_groups)) else skipped).append(rec)
        joint_check = {
            "decision_groups": list(decision_groups),
            "provinces_checked": sorted(scoped["province"].unique().tolist()),
            "provinces_excluded_at_scope_level": sorted(
                set(db["province"].unique()) - set(scoped["province"].unique())
            ),
            "status": "checked",
            "applied": applied,
            "skipped": skipped,
            "all_applied": bool(applied) and not skipped,
            "note": (
                "applied 表示该省该情景下联合约束的全部成员组都在决策集内，"
                "约束按 b2_problem 的 extra_constraints 施加；skipped 表示成员不全、整条跳过。"
                "provinces_excluded_at_scope_level 是省份本身进不了模型（数据缺口），"
                "与联合约束无关"
            ),
        }

    return {
        "schema": "province, scenario, group_id, bound_type, lower_g_day, upper_g_day, source, note",
        "bound_type": {
            "single": "单组上下界，group_id 为一个组",
            "joint": "联合上下界，group_id 形如 G05+G06，表示合计落在区间内，组间分配不受限",
        },
        "scenarios": per_scenario,
        "HEAL_base_derivation": (
            "本工作自行构造：下界 0，上界 2× 该省该组基线（2016–2024 均值）；"
            "无基线组退化为 2× CDG 上限。属可行域包络，非推荐量"
        ),
        "CDG_source": "中国居民膳食指南 2022（平衡膳食宝塔），按 g/day 区间直接取值",
        "EAT_source": "Willett et al. 2019, EAT-Lancet reference diet（g/day 区间）",
        "no_forced_split": (
            "CDG 的『畜禽肉 40-75 g』不区分畜肉与禽肉，因此设为 G05+G06 的联合约束，"
            "不再按假设的消费结构硬拆成红肉与禽肉两个区间。"
            "代价：CDG 情景下红肉与禽肉的分配由模型在成本/营养/环境目标下自行决定，"
            "故 CDG 情景的红肉结果不能解读为『指南推荐的红肉量』，必须随结果报告"
        ),
        "joint_constraint_application_rule": (
            "联合约束只在 group_id 展开后的全部成员组都进入模型时才施加。"
            "若成员不全（例如某口径只有 G05 而无 G06），必须整条跳过，"
            "绝不能把 40-75 退化成对单个成员（禽肉）的约束——那会把『畜禽肉合计』"
            "误读成『禽肉单独』，把 G05 下界从 15 抬到 40，等于凭空收紧。"
            "跳过后该情景的畜禽肉约束缺失，必须在结果中显式标注。"
        ),
        "joint_constraint_impact": (
            "决策口径 k6_price（G02/G04/G05/G06/G07/G08）同时含 G05 与 G06，联合约束生效，"
            "CDG 情景三个受约束组齐备。原预注册口径 K=3 不含 G06，联合约束只能整条跳过，"
            "此时禽肉剩余区间为负（上海 [-46.5,-11.5]），CDG 情景不可满足——"
            "这是主口径先改为 K=4 的直接原因（Plan 修订 R-2026-10-26-b）"
        ),
        "joint_constraint_check": joint_check,
        "cdg_feasibility_finding": (
            "7 省中 6 省红肉单独消费 82.9-94.4 g/天已超 CDG 畜禽肉上限 75 g；"
            "畜禽肉合计 91.8-130.6 g/天全部超上限（山东 91.8 亦超）。"
            "因此 CDG 情景必然要求红肉下降，红肉必须是决策变量"
        ),
        "residual_mismatches": {
            "G04_grains_legumes": (
                "CDG 谷类 200-300 与 EAT whole grains 均不含豆类，而 G04 是谷物+豆类，"
                "因此这两个上界对 G04 偏紧，无法用联合约束消除"
            ),
            "G12_legumes_nuts": "EAT 的 legumes 与 nuts 是两类，G12 合并为大豆及坚果，只能合并映射",
        },
        "review_required": (
            "联合约束是忠实于指南原文的处理，但仍需人工确认："
            "是否接受『组间分配由模型决定』这一自由度；若不接受，需引入外部消费结构数据"
        ),
    }


def resolve_decision_scope(scopes_out: dict) -> dict:
    """解析并校验决策口径。

    单一事实来源是 ``configs/default.yaml`` 的 ``optimization.decision_scope``，
    manifest 只做记录与交叉校验，不自行定义。校验三件事：

    1. 配置里写了的口径必须在 :data:`SCOPES` 中；
    2. 该口径的审计表必须真的被本次构建产出；
    3. ``SCOPES``（本脚本）与 ``SCOPE_AUDITS``（``src/b2_problem.py``）两张
       注册表对同一个口径名必须指向**同一张审计表**——两处写歪会静默跑出
       不同的 K，且日志里看不出来，属于必须硬失败的错误。
    """
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    scope = (cfg.get("optimization") or {}).get("decision_scope")
    if not scope:
        raise ValueError(
            "configs/default.yaml 缺 optimization.decision_scope。"
            "决策口径必须显式声明，不允许隐式默认为某个历史口径"
        )
    if scope not in SCOPES:
        raise ValueError(f"decision_scope={scope!r} 不在 SCOPES 中，可选：{sorted(SCOPES)}")

    audit_file = SCOPES[scope]["audit_file"]
    if scope not in scopes_out:
        raise ValueError(f"decision_scope={scope!r} 的审计表本次未产出")

    from src.b2_problem import SCOPE_AUDITS, Contract  # 延迟导入，避免循环

    if scope not in SCOPE_AUDITS:
        raise ValueError(
            f"decision_scope={scope!r} 未登记到 src/b2_problem.py 的 SCOPE_AUDITS，"
            "run_b2 --scope 无法加载该口径"
        )
    if SCOPE_AUDITS[scope] != audit_file:
        raise ValueError(
            f"口径 {scope!r} 的审计表两处注册不一致："
            f"build_contract_files.SCOPES={audit_file!r} vs "
            f"b2_problem.SCOPE_AUDITS={SCOPE_AUDITS[scope]!r}"
        )

    # 实际装配一次，记录该口径能覆盖哪些省——缺口必须写进 manifest，
    # 否则「7 省研究」会悄悄变成 6 省而不留痕。
    contract = Contract.load_scope(scope)
    usable, skipped = contract.complete_provinces()

    return {
        "scope": scope,
        "audit_file": audit_file,
        "included_k": scopes_out[scope]["included_k"],
        "included_group_ids": scopes_out[scope]["included_group_ids"],
        "excluded_group_ids": scopes_out[scope]["excluded_group_ids"],
        "params": SCOPES[scope]["params"],
        "role": SCOPES[scope]["role"],
        "usable_provinces": list(usable),
        "n_usable_provinces": len(usable),
        "skipped_provinces": skipped,
        "load_command": f"Contract.load_scope({scope!r})  # 等价于 python scripts/run_b2.py --scope {scope}",
        "why": (
            "K=4 下价格传导目标链不显形（D1 相对 D0 的位移 0/7 省），且山东硬不可行。"
            "R307b 的 2×2 因子分解把原因拆开：G04 解决山东硬不可行，"
            "G07 恢复价格传导，二者都与 K 的大小无关。故决策口径取 K=6"
        ),
        "cost": (
            "上海在 G07 水产品上源表整块缺失（price_source=missing），批发价源亦无水产品品类，"
            "仓库内无法桥接，因此本口径只覆盖 6 省，上海出局"
        ),
        "contract_file_unchanged": (
            "Plan 第 3 节的七个合同文件不变，group_audit.csv 仍是 K=4；"
            "本口径只换审计表，其余六个文件逐字节相同"
        ),
        "precedent": "docs/CHANGELOG_2026-10-26.md §20",
    }


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)

    scopes_out = {}
    primary_audit = None
    for key, spec in SCOPES.items():
        onto, audit, summary = build_audit(**spec["params"])
        audit_path = PROCESSED / spec["audit_file"]
        audit.to_csv(audit_path, index=False, encoding="utf-8-sig")
        if key == "primary":
            onto.to_csv(PROCESSED / "ontology.csv", index=False, encoding="utf-8-sig")
            primary_audit = audit.copy()
        scopes_out[key] = {
            "label": spec["label"],
            "role": spec["role"],
            "description": spec["description"],
            "params": spec["params"],
            "included_k": summary["included_groups"],
            "included_group_ids": summary["included_group_ids"],
            "excluded_group_ids": [r["group_id"] for r in summary["excluded"]],
            "audit_file": spec["audit_file"],
        }
        print(f"[{key}] K={summary['included_groups']} {summary['included_group_ids']}")

    decision_scope = resolve_decision_scope(scopes_out)
    print(
        f"[decision] {decision_scope['scope']} K={decision_scope['included_k']} "
        f"{decision_scope['included_group_ids']} <- {decision_scope['audit_file']}"
    )
    print(
        f"[decision] 可用省 {decision_scope['n_usable_provinces']}/{len(PROVINCES)}；"
        f"跳过 {decision_scope['skipped_provinces']}"
    )

    baseline = build_baseline_consumption()
    baseline_path = PROCESSED / "baseline_consumption.csv"
    baseline.to_csv(baseline_path, index=False, encoding="utf-8-sig")
    print(
        f"[baseline] {len(baseline)} 行 | 观测 {int(baseline['observed'].sum())} | "
        f"省 {baseline['province'].nunique()} | 组 {baseline['group_id'].nunique()}"
    )

    config_text = CONFIG.read_text(encoding="utf-8")
    config_hash = hashlib.sha256(config_text.encode("utf-8")).hexdigest()

    artifacts = {}
    missing = []
    for name in CONTRACT_FILES:
        if name == "model_manifest.json":
            continue  # 自身无法自哈希，由 contract_status 记录
        path = PROCESSED / name
        if path.exists():
            artifacts[name] = artifact_record(path)
        else:
            missing.append(name)
            print(f"[warn] 缺少 {name}，请先运行对应构建脚本")

    plan_missing = [n for n in PLAN_SEVEN if n in missing]
    contract_status = {
        "plan_files_expected": len(PLAN_SEVEN),
        "plan_files_present": len(PLAN_SEVEN) - len(plan_missing),
        "plan_files_missing": plan_missing,
        "extra_files": {n: (n in artifacts) for n in CONTRACT_EXTRA},
        "self_carrier": "model_manifest.json（本文件，自哈希不适用）",
        "gate_ready": not plan_missing,
    }
    if plan_missing:
        print(f"[warn] 合同未闭合，缺 {len(plan_missing)} 个：{plan_missing}")
    else:
        print(f"[contract] 7/7 齐备")

    data_manifest_path = ROOT / "data" / "DATA_MANIFEST.json"
    inputs = []
    if data_manifest_path.exists():
        inputs = json.loads(data_manifest_path.read_text(encoding="utf-8"))["files"]

    environment_summary = summarize_environment(artifacts)
    decision_summary = summarize_decision_bounds(
        artifacts,
        decision_groups=decision_scope["included_group_ids"],
        provinces=decision_scope["usable_provinces"],
    )

    manifest = {
        "manifest_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_by": "scripts/build_contract_files.py",
        "ontology_version": ONTOLOGY_VERSION,
        "weights_version": "w-default-v1",
        "objective_weights": [0.5, 0.1, 0.1, 0.1, 0.1, 0.1],
        "seed": 20261015,
        "config_file": "configs/default.yaml",
        "config_sha256": config_hash,
        "units": UNITS,
        "provinces": PROVINCES,
        "scenarios": ["HEAL_base", "CDG", "EAT"],
        "frozen_scopes": scopes_out,
        "decision_scope": decision_scope,
        "plan_column_mapping": PLAN_COLUMN_MAPPING,
        "contract_status": contract_status,
        "artifacts": artifacts,
        "inputs": inputs,
        "environment_boundary": environment_summary,
        "decision_bounds": decision_summary,
        "trace_handling": {
            "nutrients_csv": "痕量（value_status=trace）视为真实近零，按 0 计入组级系数",
            "group_audit_primary": (
                "主口径 trace_as_valid=True：痕量按有效近零计入，G06 红肉营养门 11/11 通过"
            ),
            "group_audit_k3": (
                "对照口径 trace_as_valid=False：痕量不算有效观测，G06 判 10/11 而排除，K=3"
            ),
            "why_primary_changed": (
                "CDG 情景的约束对象是「畜禽肉合计 40-75 g」，而 7 省中 6 省红肉单独已达 "
                "82.9-94.4 g/天、畜禽肉合计 91.8-130.6 g/天，全部超上限。"
                "若红肉不进入模型，禽肉须满足的剩余区间为负（如上海 [-46.5,-11.5]），"
                "CDG 情景不可满足。故主口径必须纳入 G06。"
                "羊肉碳水化合物标 Tr 是真实近零而非缺失，按 0 计入有依据"
            ),
            "precedent": "docs/EXPERIMENT_PLAN.md 修订 R-2026-10-26-b",
        },
        "consumption_granularity": {
            "why_no_meat_split": (
                "消费表 red_meat 的来源指标是『居民人均肉类消费量』"
                "（metric_name=meat_consumption，source_value_raw 单位 kg/年），"
                "这是国家统计局居民人均主要食品消费量表的原始分类口径——"
                "『肉类』在该表中本身就是猪牛羊肉的合计项，与『禽类』并列，"
                "而禽类已单列为 poultry 组。因此红肉无品类拆分不是本项目的数据丢失，"
                "而是上游统计口径的粒度上限"
            ),
            "consequence": (
                "决策变量只能是组级 red_meat。拆成猪/牛/羊三个变量会使 p+b+l=T 欠定，"
                "优化器将把红肉全部配给目标函数上最划算的品类，产出模型虚构的膳食结构"
            ),
            "how_structure_is_still_used": (
                "不拆决策变量，但组级系数需要组内加权。权重取表观消费份额"
                "（猪肉 0.788 / 牛肉 0.136 / 羊肉 0.076，见 data/input/external/"
                "meat_consumption_structure.csv），三个维度共用同一套权重。"
                "这是『用结构定系数』，不是『用结构定决策』——后者仍被禁止"
            ),
            "what_would_be_needed": (
                "若要把猪/牛/羊作为独立决策变量，必须引入另一套口径的分品类消费数据，"
                "且需同时修正 p+b+l=T 的欠定性（如固定结构比例、或引入价格弹性），"
                "超出当前 Plan 范围，故当前不做"
            ),
        },
        "price_aggregation": {
            "default": "单品类组直接取值；多品类组（仅 G06）按消费结构加权",
            "G06_weights": "猪肉 0.788 / 牛肉 0.136 / 羊肉 0.076（表观消费份额）",
            "G06_rationale": (
                "组级价格是组内各品类价格的加权平均，权重等于消费份额："
                "每公斤红肉的平均支出恰为 Σ w_i·p_i。"
                "不取主导品类（猪肉）的原因：猪肉是三品类最便宜的，取它等价于取最低价"
                "（price_min 与猪肉价在 G06 全部观测行相等），会系统性低估组价，"
                "使优化器高估红肉可负担量；等权则相反，会高估组价（54.43 vs 43.92 元/kg）。"
            ),
            "incomplete_panel_caveat": (
                "G06 的 51 个省-年观测中仅 27 行三品类齐全，23 行只有单品类（且全部是猪肉）。"
                "缺失品类按已观测品类重新归一，故这 23 行的组价仍等于猪肉价。"
                "这不是聚合方法的缺陷，而是价格面板的覆盖缺口，只能靠插补解决。"
            ),
            "residual_limitation": (
                "G3 断言『主口径等于最低价的比例 < 50%』实测 45.1%（23/51），"
                "全部来自上述单品类行，阈值已贴近。若后续面板覆盖改善，该比例应显著下降；"
                "若恶化至 50% 以上，说明 G06 组价已退化为猪肉价，主结论不成立。"
            ),
            "sensitivity_columns": [
                "price_structure_weighted",
                "price_complete_equal",
                "price_equal_weight",
                "price_min",
                "price_max",
                "price_dominant",
            ],
        },
        "nutrient_aggregation": {
            "default": "单品类组取组内 eligible 食物等权平均",
            "G06_weights": "猪肉 0.788 / 牛肉 0.136 / 羊肉 0.076（与价格、环境维度同一套）",
            "G06_rationale": (
                "组级营养密度应满足 n̄ = Σ n_i·q_i/T，权重等于消费份额。"
                "等权隐含『三品类等量消费』，会把脂肪与能量显著高估、蛋白低估。"
                "三个维度共用同一套权重是硬要求：否则同一个组会在成本端按猪肉定价、"
                "在营养端按三分之一牛肉供给，约束两侧说的不是同一种食物"
            ),
            "column": "nutrients.csv 的 aggregation 列逐行标注",
            "note": (
                "lower / upper 仍取组内食物间的 min / max，表达品类间差异，不随权重改变；"
                "sd_per_kg 为未加权标准差，语义是『品类间离散度』"
            ),
        },
        "alternative_sources": {
            "wholesale_price": {
                "path": "华东华中7省食品零售价_商务预报_分省批发价_mice插补.xlsx",
                "role": "supplementary",
                "status": "not_used_in_primary_analysis",
                "coverage": {
                    "categories": 9,
                    "cells": 567,
                    "observed": 513,
                    "mice_imputed": 9,
                    "structural_missing": 45,
                },
                "missing_categories": ["乳制品", "水果", "水产品(不含虾蟹)", "糖", "坚果"],
                "imputed_identification": "年均值有值且『采样市场数(年累计)』为空，即为 MICE 插补值",
                "planned_use": "B4 价格口径敏感性：与零售价面板并跑，检验方向结论对价格体系的稳健性",
                "reason_not_primary": "成本目标为消费者食品支出，应用零售价；批发价属流通环节价格",
                "gate_check": "批发价价格门通过 7 组（含 G10 薯类、无水产品），叠加营养与消费门后仍为 G02/G05/G08",
            },
            "national_weekly_price": {
                "path": "华东华中7省食品零售价_商务预报_全国周度价_mice插补.xlsx",
                "role": "unused",
                "status": "not_used",
                "note": "文件名含『mice插补』但工作簿说明首行写明『本工作簿未做 mice 插补』，且为全国周度口径，无分省信息",
            },
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pandas": pd.__version__,
        },
    }

    manifest_path = PROCESSED / "model_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[manifest] wrote {manifest_path.relative_to(ROOT)}")
    for name, rec in artifacts.items():
        print(f"   {name:<38} {rec['sha256'][:16]}  {rec['bytes']:>7} B")

    # 先落 manifest，再跑 gate 验收，最后把验收结果回写。
    # 回写只改 manifest 自身，不触碰数据文件，因此 artifacts 的 hash 仍然有效。
    from scripts.check_contract_gates import run_all, write_report

    gate_results = run_all(verbose=False)
    passed = write_report(gate_results, PROCESSED / "contract_gate_report.json")
    manifest["gate_verification"] = {
        "script": "scripts/check_contract_gates.py",
        "report": "data/processed/contract_gate_report.json",
        "passed": passed,
        "total": len(gate_results),
        "all_passed": passed == len(gate_results),
        "failed_gates": [r["gate"] for r in gate_results if not r["ok"]],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[gate] {passed}/{len(gate_results)} 通过 -> 回写 manifest")

    write_run_record(manifest, artifacts, primary_audit)


if __name__ == "__main__":
    main()
