"""HEAL_base 上界倍数的敏感性：到底要放宽到几倍，这个情景才可用？

## 问题

``HEAL_base`` 的设计是「0 到 **2 倍**省级基线」的可行域包络。K=6 决策口径下
实测 **6 省全部硬不可行**，冲突集一律为 ``{脂肪, 碳水化合物, 硫胺素}``。
而 K=4 时还有 1/7 可行、K=3 时 5/7——差异来自「被排除的约束条数」，不是模型好坏
（见 CHANGELOG §21.4）。

所以「HEAL_base 不可行」这句话本身没有信息量，要问的是：
**在 2 倍上界下不可行，是因为 2 倍这个数字，还是因为这个情景本身与营养需求冲突？**

## 做法

不改正式契约。把 ``data/processed`` 复制到 run 目录的 ``shadow_*/``，
只把 ``decision_bounds.csv`` 里 ``HEAL_base`` 单组行的上界乘以 ``m / 2``，
再用 ``Contract.load(processed=shadow, audit_file=<k6_price 的审计表>)`` 装配。

乘 ``m/2`` 而不是重算基线，是因为原表的上界恰为 ``2 × 基线``
（无基线的组退化为 ``2 × CDG 上限``），两种情形都随倍数线性缩放，
故一次乘法即可精确得到 ``m × 基线``，不必解析 note 列。

## 判据（两个，缺一不可）

**不能只看 `Instance.hard_feasible`。** 首次运行就出现了**非单调**结果：
m=2.5 时 4/6 可行，m=3.0 反而只有 3/6，m=4.0 又换了一批省。
原因还是「可操作营养素集合随边界变化」：放宽上界会让原本不可达的钙
（或碳水）变得可达，于是它**新进入**约束集，凭空多出一条冲突。
即 `hard_feasible` 的松紧不完全由可行域决定，还由「这一版边界下有哪几条约束存在」决定。

所以本诊断同时报两个判据：

1. ``model_feasible`` = ``Instance.hard_feasible``：模型**实际**看到的可行性（含遮蔽）；
2. ``full_feasible`` = 把**全部 11 个营养素**都强制纳入后是否可行
   （直接调 ``minimal_conflict_set``，绕开 active_mask）。

``full_feasible`` 只随 ``q_upper`` 单调变化（生效上下界与倍数无关），
所以它的「最小可行倍数」才是有意义的量。``model_feasible`` 只用来展示遮蔽效应。

## 证据等级

``structural``：不含求解，可逐行复核。

用法：
    python scripts/diagnose_heal_bound_scale.py
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.b2_problem import (  # noqa: E402
    SCOPE_AUDITS,
    Contract,
    minimal_conflict_set,
)
from src.io_utils import create_run_dir, finalize_run  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
MULTIPLIERS = (2.0, 2.5, 3.0, 4.0, 6.0, 8.0)
SCOPE = "k6_price"


def _shadow(multiplier: float, dest: Path) -> Path:
    """复制契约到影子目录，只改 HEAL_base 的上界倍数。"""
    dest.mkdir(parents=True, exist_ok=True)
    for src in PROCESSED.iterdir():
        if src.is_file() and src.suffix in {".csv", ".json"}:
            shutil.copy2(src, dest / src.name)

    db = pd.read_csv(PROCESSED / "decision_bounds.csv", encoding="utf-8-sig")
    mask = db["scenario"].eq("HEAL_base") & db["bound_type"].eq("single")
    # 原表上界 = 2 × 基线（或 2 × CDG 上限），故 × m/2 即得 m 倍
    db.loc[mask, "upper_g_day"] = db.loc[mask, "upper_g_day"] * (multiplier / 2.0)
    db.to_csv(dest / "decision_bounds.csv", index=False, encoding="utf-8-sig")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_heal_bound_scale")
    args = ap.parse_args()

    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    rows: list[dict] = []
    for multiplier in MULTIPLIERS:
        shadow = _shadow(multiplier, run_dir / f"shadow_m{multiplier:g}")
        contract = Contract.load(processed=shadow, audit_file=SCOPE_AUDITS[SCOPE])
        usable, _ = contract.complete_provinces()
        for province in usable:
            inst = contract.instance(province, "HEAL_base")
            # 全约束可行性：把 11 个营养素全部强制纳入，绕开 active_mask。
            # 生效上下界（effective）不随倍数变化，故该判据对 m 单调。
            n_mat = inst.nutrient_coeff[0]
            full_conflict_idx = minimal_conflict_set(
                n_mat,
                inst.q_lower,
                inst.q_upper,
                inst.nutrient_lower,
                inst.nutrient_upper,
                inst.extra_constraints,
            )
            full_feasible = full_conflict_idx is None

            # 摘掉钙后再判一次：用来区分「钙是唯一阻塞」与「钙只是并列阻塞之一」。
            # 若摘掉后 2× 基线就可行，说明「钙的处置」与「HEAL_base 的处置」
            # 其实是同一个决策，不该分开裁定。
            keep = [j for j, n in enumerate(inst.nutrients) if n != "钙"]
            ex_ca = minimal_conflict_set(
                n_mat[keep],
                inst.q_lower,
                inst.q_upper,
                inst.nutrient_lower[keep],
                inst.nutrient_upper[keep],
                inst.extra_constraints,
            )
            ex_ca_feasible = ex_ca is None
            rows.append({
                "multiplier": multiplier,
                "province": province,
                "k": inst.k_count,
                "model_feasible": bool(inst.hard_feasible),
                "model_conflict_set": "+".join(inst.conflict_set),
                "full_feasible": bool(full_feasible),
                "full_conflict_set": (
                    "" if full_feasible
                    else "+".join(inst.nutrients[j] for j in full_conflict_idx)
                ),
                "feasible_without_calcium": bool(ex_ca_feasible),
                "conflict_without_calcium": (
                    "" if ex_ca_feasible
                    else "+".join(inst.nutrients[keep[j]] for j in ex_ca)
                ),
                "n_excluded": len(inst.non_actionable),
                "excluded": "; ".join(n for n, _ in inst.non_actionable),
                "upper_sum_g_day": float(np.sum(inst.q_upper)),
            })
        sub = [r for r in rows if r["multiplier"] == multiplier]
        print(
            f"[m={multiplier:<4}] 全约束可行 {sum(r['full_feasible'] for r in sub)}/{len(sub)}"
            f"  摘掉钙后可行 {sum(r['feasible_without_calcium'] for r in sub)}/{len(sub)}"
            f"  模型可行(含遮蔽) {sum(r['model_feasible'] for r in sub)}/{len(sub)}"
        )

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "heal_bound_scale.csv", index=False, encoding="utf-8-sig")

    # 每省「最小全约束可行倍数」：不可行记 None
    first_ok = (
        df[df["full_feasible"]]
        .groupby("province")["multiplier"]
        .min()
        .reindex(sorted(df["province"].unique()))
    )
    min_mult = pd.DataFrame({
        "province": first_ok.index,
        "min_full_feasible_multiplier": first_ok.to_numpy(),
    })
    min_mult["still_infeasible_at_max"] = min_mult["min_full_feasible_multiplier"].isna()
    min_mult.to_csv(run_dir / "min_feasible_multiplier.csv", index=False, encoding="utf-8-sig")

    print("\n=== 每省最小全约束可行倍数（单调判据） ===")
    print(min_mult.to_string(index=False))

    print("\n=== 全约束冲突集随倍数的变化 ===")
    print(
        df.pivot_table(index="province", columns="multiplier",
                       values="full_conflict_set", aggfunc="first").fillna("").to_string()
    )
    print("\n=== 模型实际看到的冲突集（含遮蔽，非单调） ===")
    print(
        df.pivot_table(index="province", columns="multiplier",
                       values="model_conflict_set", aggfunc="first").fillna("").to_string()
    )

    finalize_run(
        run_dir,
        {
            "command": "diagnose-heal-bound-scale",
            "evidence_status": "structural",
            "evidence_note": (
                "只读 Instance 的约束装配结果与 minimal_conflict_set，不求解。"
                "两个判据：full_feasible = 11 个营养素全部强制纳入（对倍数单调，"
                "用于定最小倍数）；model_feasible = 模型实际所见（含 active_mask 遮蔽，"
                "非单调，仅用于展示遮蔽效应）。正式契约未改动（影子目录装配）。"
            ),
            "scope": SCOPE,
            "multipliers": list(MULTIPLIERS),
            "baseline_rule": "原表 HEAL_base 上界 = 2 × 省级基线；本诊断改为 m × 基线",
            "rows": df.to_dict("records"),
            "min_feasible_multiplier": min_mult.to_dict("records"),
            "n_provinces": int(df["province"].nunique()),
        },
        {"command": "diagnose-heal-bound-scale", "scope": SCOPE,
         "multipliers": list(MULTIPLIERS)},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
