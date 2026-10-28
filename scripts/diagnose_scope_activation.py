"""口径激活诊断：K 变大时，哪些营养约束**才开始被真正施加**？

## 要回答的问题

``Instance.active_mask`` 决定哪些营养素进入机会约束。判据是「该营养素在
``box ∩ 联合约束`` 内是否可达 ``[ℓ,u]``」——不可达的会被排除，因为它在每个场景
都必然违反，放进机会约束只会让 ``Σ z_s ≤ floor(εS)`` 直接不可行。

排除本身是对的，但它有一个**副作用**：被排除的约束在模型里等于不存在。
于是「K=4 时可行」可能只意味着「K=4 把某些约束丢掉了」，而不是
「K=4 真的满足更多约束」。

本项目实测到的具体例子（安徽 / CDG）：

| 口径 | 碳水化合物 | 原因 |
|---|---|---|
| K=4 | **非可操作，被排除** | G04 固定在基线，其碳水使最小可达 41.68 g > 剩余上界 18.51 g |
| K=6 | **可操作，进入机会约束** | G04 成为决策变量，碳水可达 |

即 K=4 下「安徽 CDG 硬可行」这条结论里，**CDG 的谷类碳水约束根本没被施加**。
这不是 bug，是「把最大碳水来源钉死」的必然结果；但它意味着
**K=4 与 K=6 的可行率不可直接比较**。

## 输出

- ``activation_matrix.csv``：逐 (口径, 省, 情景, 营养素) 的 active / 原因 / 有效上下界 / 可达范围
- ``masked_by_scope.csv``：只在 k4 非可操作、在 k6 可操作的那些 (省, 情景, 营养素)
- ``scope_summary.csv``：逐口径的硬可行省数、冲突集、被排除约束数

## 证据等级

``structural``：不含任何求解，只读契约装配结果，可逐行复核。

用法：
    python scripts/diagnose_scope_activation.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.b2_problem import SCOPE_AUDITS, Contract, reachable_bounds  # noqa: E402
from src.io_utils import create_run_dir, finalize_run  # noqa: E402

SCENARIOS = ("HEAL_base", "CDG", "EAT")
SCOPES = ("k4_official", "k6_price", "k5_notrace", "k3_prereg")


def _rows_for(scope: str, scenario: str) -> tuple[list[dict], dict]:
    contract = Contract.load_scope(scope)
    usable, skipped = contract.complete_provinces()
    rows: list[dict] = []
    summary = {"scope": scope, "audit_file": SCOPE_AUDITS[scope], "k": len(contract.groups),
               "groups": list(contract.groups), "skipped_provinces": skipped}

    for province in usable:
        inst = contract.instance(province, scenario)
        # 复算可达范围：Instance 只存了判定结论，不存判定依据。
        # 注意 ``nutrient_coeff`` 在 instance() 里**已经**折算成「每 g」
        # （见 b2_problem: ``nutrient_coeff = (nut / 1000.0)``），
        # 这里不能再除一次 1000，否则可达范围会缩小 1000 倍、与 reason 文本对不上。
        n_mat = inst.nutrient_coeff[0]
        lo, hi = reachable_bounds(n_mat, inst.q_lower, inst.q_upper, inst.extra_constraints)
        reasons = dict(inst.non_actionable)
        for j, nutrient in enumerate(inst.nutrients):
            rows.append({
                "scope": scope,
                "scenario": scenario,
                "province": province,
                "nutrient": nutrient,
                "k": inst.k_count,
                "active": bool(inst.active_mask[j]),
                "reason": reasons.get(nutrient, ""),
                "effective_lower": float(inst.nutrient_lower[j]),
                "effective_upper": float(inst.nutrient_upper[j]),
                "reachable_low": float(lo[j]),
                "reachable_high": float(hi[j]),
                "hard_feasible": bool(inst.hard_feasible),
                "conflict_set": "+".join(inst.conflict_set),
            })
        summary.setdefault("by_province", {})[province] = {
            "hard_feasible": bool(inst.hard_feasible),
            "conflict_set": list(inst.conflict_set),
            "n_active": int(np.sum(inst.active_mask)),
            "n_excluded": int(len(inst.non_actionable)),
        }
    return rows, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_scope_activation")
    args = ap.parse_args()

    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    all_rows: list[dict] = []
    summaries: list[dict] = []
    for scenario in SCENARIOS:
        for scope in SCOPES:
            rows, summary = _rows_for(scope, scenario)
            summary["scenario"] = scenario
            summaries.append(summary)
            all_rows.extend(rows)
            print(f"[{scenario:<10}] {scope:<12} K={summary['k']} "
                  f"硬可行 {sum(v['hard_feasible'] for v in summary['by_province'].values())}"
                  f"/{len(summary['by_province'])}")

    matrix = pd.DataFrame(all_rows)
    matrix.to_csv(run_dir / "activation_matrix.csv", index=False, encoding="utf-8-sig")

    # 只在 k4 被排除、在 k6 被纳入的约束 —— 这才是「K=4 静默丢掉的东西」
    key = ["scenario", "province", "nutrient"]
    a = matrix[matrix["scope"].eq("k4_official")].set_index(key)
    b = matrix[matrix["scope"].eq("k6_price")].set_index(key)
    # 显式改列名再 join：pandas 4 起 join 的 lsuffix/rsuffix 已弃用
    joined = a.add_suffix("_k4").join(b.add_suffix("_k6"), how="inner")
    masked = joined[(~joined["active_k4"]) & (joined["active_k6"])].reset_index()
    masked_out = masked[[
        "scenario", "province", "nutrient",
        "effective_lower_k4", "effective_upper_k4", "reachable_low_k4", "reachable_high_k4",
        "effective_lower_k6", "effective_upper_k6", "reachable_low_k6", "reachable_high_k6",
        "reason_k4", "reason_k6", "hard_feasible_k4", "hard_feasible_k6",
        "conflict_set_k4", "conflict_set_k6",
    ]]
    masked_out.to_csv(run_dir / "masked_by_scope.csv", index=False, encoding="utf-8-sig")

    scope_summary = pd.DataFrame([
        {
            "scenario": s["scenario"],
            "scope": s["scope"],
            "k": s["k"],
            "groups": " ".join(s["groups"]),
            "n_provinces": len(s["by_province"]),
            "n_hard_feasible": sum(v["hard_feasible"] for v in s["by_province"].values()),
            "n_excluded_constraints": sum(v["n_excluded"] for v in s["by_province"].values()),
            "conflicts": "; ".join(
                f"{p}:{'+'.join(v['conflict_set'])}"
                for p, v in s["by_province"].items() if not v["hard_feasible"]
            ),
        }
        for s in summaries
    ])
    scope_summary.to_csv(run_dir / "scope_summary.csv", index=False, encoding="utf-8-sig")

    print("\n=== 口径总览 ===")
    print(scope_summary.drop(columns=["groups"]).to_string(index=False))
    print(f"\n=== K=4 被排除、K=6 才生效的约束：{len(masked_out)} 条 ===")
    if len(masked_out):
        print(masked_out[["scenario", "province", "nutrient", "reason_k4"]].to_string(index=False))

    finalize_run(
        run_dir,
        {
            "command": "diagnose-scope-activation",
            "evidence_status": "structural",
            "evidence_note": (
                "只做契约装配与可达范围复算，不含求解。"
                "用于说明「K=4 的可行率」与「K=6 的可行率」不可直接比较："
                "K 变大后部分营养素从 non_actionable 变为 active，约束才开始被施加"
            ),
            "scopes": list(SCOPES),
            "scenarios": list(SCENARIOS),
            "n_masked_constraints": int(len(masked_out)),
            "masked_constraints": masked_out.to_dict("records"),
            "scope_summary": scope_summary.to_dict("records"),
            "per_scope_detail": summaries,
        },
        {"command": "diagnose-scope-activation", "scopes": list(SCOPES)},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
