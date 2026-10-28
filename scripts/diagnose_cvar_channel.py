"""风险厌恶能不能让价格不确定性进入决策？—— CVaR 通道的实测。

## 问题

CHANGELOG §21.5b 证明：目标对 ``q`` 线性、价格只进目标不进约束时，
``min_q E_s[c_s·q] = min_q (E_s c_s)·q``，**期望的最优解等于最优解的期望**，
所以 D3 ≡ D1，价格不确定性对决策结构性零传导。

这个结论有个直接推论：**只要目标保持线性，无论把场景数加多少、
把后验做得多精细，不确定性都不会影响决策。** 想让不确定性有用，
必须换一个非线性的目标——CVaR 是最常用、也最容易线性化的一种：

```
min_q  (1−λ)·E[cost(q)] + λ·CVaR_α[cost(q)]
```

本脚本回答：**换了之后，推荐的膳食真的会变吗？变了多少？代价是什么？**

## 设计

* 决策口径 `k6_price`，营养下界 `ear`（作者已定）。
* 场景只扰动**价格**（``cv_nutrient=0``）。营养系数不变时，机会约束退化为
  硬约束（每个场景的违反指示相同，``Σz_s ≤ floor(εS)`` 要么全 0 要么全 1），
  因此这里比较的**纯粹是目标函数形式的影响**，与 ε 无关。
* ``λ ∈ {0, 0.25, 0.5, 0.75, 1.0}``，``α = 0.90``（关注最差 10% 场景）。
* 指标：
  - ``max_abs_dq``：相对 λ=0 的最大组级位移（g/day）——「决策变了吗」
  - ``E_cost`` / ``CVaR_cost``：元/人/天——「买了什么」
  - ``d_E_cost`` / ``d_CVaR_cost``：相对 λ=0 的变化

## 判读

* 若 ``max_abs_dq ≈ 0`` 而 ``CVaR_cost`` 明显下降 → 存在「免费的风险改善」
  （同一膳食在尾部更好），说明价格不确定性对**排序**无影响，只是被忽略；
* 若 ``max_abs_dq`` 显著 → 风险偏好真的会改变推荐膳食，此时论文必须交代选了哪个 λ；
* 若 ``d_E_cost`` 与 ``d_CVaR_cost`` 同向且量级相近 → 没有真正的权衡，
  只是把整体成本压低，CVaR 没提供额外信息。

## 证据等级

``plumbing_only``：场景仍是占位对数正态噪声，不是 B1 后验。
可采信的是「通道是否存在、量级多大」，不是绝对数值。

用法：
    python scripts/diagnose_cvar_channel.py
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

from src.b2_problem import Contract  # noqa: E402
from src.b2_scenarios import placeholder_scenarios  # noqa: E402
from src.io_utils import create_run_dir, finalize_run  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402

SCOPE = "k6_price"
BASIS = "ear"
SCENARIO = "CDG"
ALPHA = 0.90
LAMBDAS = (0.0, 0.25, 0.5, 0.75, 1.0)
N_SCEN = 200
SEED = 20261027
CV_PRICE = 0.05


def _empirical_cvar(costs: np.ndarray, alpha: float) -> float:
    """经验 CVaR：最差 ``(1−α)`` 比例的均值（等权场景）。"""
    n_tail = max(1, int(round((1.0 - alpha) * len(costs))))
    return float(np.sort(costs)[-n_tail:].mean())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_cvar_channel")
    args = ap.parse_args()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    contract = Contract.load_scope(SCOPE)
    usable, _ = contract.complete_provinces()

    rows: list[dict] = []
    qrows: list[dict] = []

    for province in usable:
        inst = contract.instance(province, SCENARIO, bounds_basis=BASIS)
        obj_s, nut_s = placeholder_scenarios(
            inst, N_SCEN, SEED, cv_price=CV_PRICE, cv_nutrient=0.0
        )
        mask = inst.active_mask
        cost_coeff = np.asarray(obj_s, dtype=float)[:, 0, :]  # [S, K] 元/g

        base_q = None
        for lam in LAMBDAS:
            res = solve_chance_modopt(
                obj_s,
                nut_s[:, mask, :],
                inst.nutrient_lower[mask],
                inst.nutrient_upper[mask],
                inst.q_lower,
                inst.q_upper,
                inst.objective_weights,
                epsilon=0.05,
                extra_constraints=inst.extra_constraints,
                risk_weight=lam,
                cvar_alpha=ALPHA,
            )
            if not res.success:
                rows.append({
                    "province": province, "lambda": lam, "success": False,
                    "message": str(res.message)[:80],
                })
                continue
            q = np.asarray(res.q, dtype=float)
            if base_q is None:
                base_q = q.copy()
            costs = cost_coeff @ q
            rows.append({
                "province": province,
                "lambda": lam,
                "success": True,
                "objective": float(res.objective),
                "E_cost": float(costs.mean()),
                "CVaR_cost": _empirical_cvar(costs, ALPHA),
                "max_cost": float(costs.max()),
                "max_abs_dq": float(np.abs(q - base_q).max()),
                "sum_abs_dq": float(np.abs(q - base_q).sum()),
            })
            qrows.append({
                "province": province, "lambda": lam,
                **{f"q_{g}": float(v) for g, v in zip(inst.groups, q)},
            })

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "cvar_channel.csv", index=False, encoding="utf-8-sig")
    qdf = pd.DataFrame(qrows)
    if not qdf.empty:
        qdf.to_csv(run_dir / "cvar_q.csv", index=False, encoding="utf-8-sig")

    ok = df[df["success"]]
    pd.set_option("display.width", 220)

    print(f"=== {SCENARIO} / {SCOPE} / {BASIS} / α={ALPHA} / S={N_SCEN} ===")
    print("\n决策位移（相对 λ=0，g/day）")
    print(
        ok.pivot_table(index="province", columns="lambda", values="max_abs_dq")
        .round(3).to_string()
    )
    print("\n期望成本（元/人/天）")
    print(
        ok.pivot_table(index="province", columns="lambda", values="E_cost")
        .round(3).to_string()
    )
    print(f"\nCVaR_{ALPHA} 成本（元/人/天）")
    print(
        ok.pivot_table(index="province", columns="lambda", values="CVaR_cost")
        .round(3).to_string()
    )

    # 相对 λ=0 的变化
    base = ok[ok["lambda"].eq(0.0)].set_index("province")
    delta_rows = []
    for _, r in ok[~ok["lambda"].eq(0.0)].iterrows():
        b = base.loc[r["province"]]
        delta_rows.append({
            "province": r["province"], "lambda": r["lambda"],
            "max_abs_dq": r["max_abs_dq"],
            "d_E_cost": r["E_cost"] - b["E_cost"],
            "d_CVaR_cost": r["CVaR_cost"] - b["CVaR_cost"],
            "d_E_pct": (r["E_cost"] / b["E_cost"] - 1) * 100,
            "d_CVaR_pct": (r["CVaR_cost"] / b["CVaR_cost"] - 1) * 100,
        })
    ddf = pd.DataFrame(delta_rows)
    if not ddf.empty:
        ddf.to_csv(run_dir / "cvar_delta.csv", index=False, encoding="utf-8-sig")
        print("\n相对 λ=0 的变化")
        print(
            ddf.pivot_table(index="province", columns="lambda", values="d_CVaR_pct")
            .round(2).to_string()
        )

    if not qdf.empty:
        print("\n组级摄入（λ=0 vs λ=1，g/day）")
        wide = qdf[qdf["lambda"].isin([0.0, 1.0])].set_index(["province", "lambda"])
        cols = [c for c in qdf.columns if c.startswith("q_")]
        print(wide[cols].round(1).to_string())

    summary = {}
    if not ddf.empty:
        summary = {
            "max_abs_dq_over_all": float(ddf["max_abs_dq"].max()),
            "median_abs_dq_at_lambda1": float(
                ddf[ddf["lambda"].eq(1.0)]["max_abs_dq"].median()
            ),
            "mean_d_CVaR_pct_at_lambda1": float(
                ddf[ddf["lambda"].eq(1.0)]["d_CVaR_pct"].mean()
            ),
            "mean_d_E_pct_at_lambda1": float(
                ddf[ddf["lambda"].eq(1.0)]["d_E_pct"].mean()
            ),
        }
        print("\n=== 汇总 ===")
        for k, v in summary.items():
            print(f"  {k}: {v:.4f}")

    finalize_run(
        run_dir,
        {
            "command": "diagnose-cvar-channel",
            "evidence_status": "plumbing_only",
            "scope": SCOPE,
            "bounds_basis": BASIS,
            "scenario": SCENARIO,
            "alpha": ALPHA,
            "lambdas": list(LAMBDAS),
            "n_scenarios": N_SCEN,
            "cv_price": CV_PRICE,
            "cv_nutrient": 0.0,
            "evidence_note": (
                "场景仍是占位对数正态噪声，非 B1 后验。"
                "可采信『通道是否存在、量级多大』，不可采信绝对数值。"
                "cv_nutrient=0 时机会约束退化为硬约束，故本诊断只反映目标形式的影响"
            ),
            "summary": summary,
            "rows": df.to_dict("records"),
        },
        {"command": "diagnose-cvar-channel", "scope": SCOPE, "alpha": ALPHA},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
