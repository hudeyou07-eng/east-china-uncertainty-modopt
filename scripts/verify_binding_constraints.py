"""R307 前置诊断：验证「最优解处哪些约束是紧的」。

**为什么需要这一步**：CHANGELOG §14 的核心因果主张是
「六省最优解里脂肪下界无一例外都是紧约束，模型因此退化为
『需要多少红肉才能满足脂肪下界』，价格相对变化自然不起作用」。

这个主张此前只有**间接**证据（脂肪系数 ±10% 会移动解、价格 ±50% 不动）。
间接证据不足以支撑因果链——营养系数扰动敏感也可能只是因为它
恰好是**紧约束**，而价格不敏感也可能另有原因（如可行域退化）。
本脚本直接把最优点代回全部约束，报出每条约束的余量，正面检验该主张。

判定口径用**三态**，不能用「``slack <= tol`` 即紧」——那样会把**违反**
（``slack < 0``）也算成「紧」，而两者含义完全相反：

* ``violated``：``slack / scale < -tol`` —— 约束被违反（本模型里只有
  ``active_mask=False`` 的不可达营养素会这样，属已知设计）；
* ``tight``：``|slack / scale| <= tol`` —— 真正卡住解的那条；
* ``slack``：其余。

其中 ``slack = achieved - lower``（下界）或 ``upper - achieved``（上界），
``scale = max(|bound|, |achieved|, 1)`` 避免 0 附近除零。
默认 ``tol = 1e-6``（HiGHS 对 LP 的原始可行性容差量级）。

用法::

    python scripts/verify_binding_constraints.py --profile smoke
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
from src.b2_scenarios import deterministic  # noqa: E402
from src.io_utils import create_run_dir, finalize_run  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402

TOL = 1e-6


def _state(slack: float, scale: float, tol: float = TOL) -> str:
    """把余量分成 violated / tight / slack 三态。"""
    rel = slack / scale
    if rel < -tol:
        return "violated"
    if abs(rel) <= tol:
        return "tight"
    return "slack"


def _slack_rows(inst, q: np.ndarray, scenario: int = 0) -> list[dict]:
    """把最优点 q 代回全部约束，逐条报余量。"""
    rows: list[dict] = []
    coeff = inst.nutrient_coeff[scenario]  # [J, K]
    achieved = coeff @ q

    for j, name in enumerate(inst.nutrients):
        lo = inst.nutrient_lower[j]
        hi = inst.nutrient_upper[j]
        val = float(achieved[j])
        if np.isfinite(lo):
            slack = val - lo
            scale = max(abs(lo), abs(val), 1.0)
            rows.append(
                {
                    "kind": "nutrient_lower",
                    "name": name,
                    "bound": float(lo),
                    "achieved": val,
                    "slack": float(slack),
                    "rel_slack": float(slack / scale),
                    "active_in_chance": bool(inst.active_mask[j]),
                    "state": _state(slack, scale),
                }
            )
        if np.isfinite(hi):
            slack = hi - val
            scale = max(abs(hi), abs(val), 1.0)
            rows.append(
                {
                    "kind": "nutrient_upper",
                    "name": name,
                    "bound": float(hi),
                    "achieved": val,
                    "slack": float(slack),
                    "rel_slack": float(slack / scale),
                    "active_in_chance": bool(inst.active_mask[j]),
                    "state": _state(slack, scale),
                }
            )

    for idx, (vec, lo, hi) in enumerate(inst.extra_constraints):
        vec = np.asarray(vec, dtype=float)
        val = float(vec @ q)
        if np.isfinite(lo):
            slack = val - lo
            scale = max(abs(lo), abs(val), 1.0)
            rows.append(
                {
                    "kind": "joint_lower",
                    "name": f"joint#{idx}",
                    "bound": float(lo),
                    "achieved": val,
                    "slack": float(slack),
                    "rel_slack": float(slack / scale),
                    "active_in_chance": True,
                    "state": _state(slack, scale),
                }
            )
        if np.isfinite(hi):
            slack = hi - val
            scale = max(abs(hi), abs(val), 1.0)
            rows.append(
                {
                    "kind": "joint_upper",
                    "name": f"joint#{idx}",
                    "bound": float(hi),
                    "achieved": val,
                    "slack": float(slack),
                    "rel_slack": float(slack / scale),
                    "active_in_chance": True,
                    "state": _state(slack, scale),
                }
            )

    # 决策箱边界（q 是否贴上下限）——红肉若贴下界，说明「被钉住」在决策箱一侧
    for k, gid in enumerate(inst.groups):
        if q[k] - inst.q_lower[k] <= TOL * max(abs(inst.q_lower[k]), 1.0):
            rows.append(
                {
                    "kind": "q_lower",
                    "name": gid,
                    "bound": float(inst.q_lower[k]),
                    "achieved": float(q[k]),
                    "slack": float(q[k] - inst.q_lower[k]),
                    "rel_slack": 0.0,
                    "active_in_chance": False,
                    "state": "tight",
                }
            )
        if inst.q_upper[k] - q[k] <= TOL * max(abs(inst.q_upper[k]), 1.0):
            rows.append(
                {
                    "kind": "q_upper",
                    "name": gid,
                    "bound": float(inst.q_upper[k]),
                    "achieved": float(q[k]),
                    "slack": float(inst.q_upper[k] - q[k]),
                    "rel_slack": 0.0,
                    "active_in_chance": False,
                    "state": "tight",
                }
            )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="CDG", help="膳食情景，默认 CDG")
    ap.add_argument("--epsilon", type=float, default=0.05)
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    contract = Contract.load()
    usable, skipped = contract.complete_provinces()
    print(f"可用省份 {len(usable)}：{', '.join(usable)}")
    if skipped:
        print(f"跳过（硬不可行）：{', '.join(skipped)}")

    run_dir = create_run_dir(ROOT / "outputs", args.run_id or "DIAG_binding")

    rows: list[dict] = []
    solutions: list[dict] = []
    for province in usable:
        inst = contract.instance(province, args.scenario)
        if not inst.hard_feasible:
            continue
        # D1 = 确定性单一场景（省内价）。这里只关心「最优解处哪些约束紧」，
        # 用确定性实例即可，不需要 200 个随机场景。
        obj, nut = deterministic(inst)
        res = solve_chance_modopt(
            obj,
            nut[:, inst.active_mask, :],
            inst.nutrient_lower[inst.active_mask],
            inst.nutrient_upper[inst.active_mask],
            inst.q_lower,
            inst.q_upper,
            inst.objective_weights,
            epsilon=args.epsilon,
            extra_constraints=inst.extra_constraints,
        )
        if not res.success:
            print(f"  {province}: 求解失败 —— {res.message}")
            continue

        solutions.append(
            {
                "province": province,
                "objective": float(res.objective),
                **{f"q_{g}": float(v) for g, v in zip(inst.groups, res.q)},
            }
        )
        for row in _slack_rows(inst, np.asarray(res.q, dtype=float)):
            rows.append({"province": province, **row})

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "constraint_slack.csv", index=False, encoding="utf-8-sig")
    sol = pd.DataFrame(solutions)
    sol.to_csv(run_dir / "solutions.csv", index=False, encoding="utf-8-sig")

    print()
    print("=== 每个省的约束状态（tight / violated） ===")
    for province, sub in df.groupby("province"):
        tight = [f"{r.kind}:{r['name']}" for _, r in sub[sub.state == "tight"].iterrows()]
        viol = [f"{r.kind}:{r['name']}" for _, r in sub[sub.state == "violated"].iterrows()]
        print(f"  {province}")
        print(f"    tight    : {', '.join(tight) if tight else '（无）'}")
        print(f"    violated : {', '.join(viol) if viol else '（无）'}")

    print()
    print("=== 脂肪下界是否在全部省份都紧？ ===")
    fat = df[(df.kind == "nutrient_lower") & (df.name == "脂肪")]
    if fat.empty:
        print("  未找到脂肪下界记录")
    else:
        n_tight = int((fat.state == "tight").sum())
        print(f"  tight {n_tight}/{len(fat)} 省")
        print(fat[["province", "bound", "achieved", "rel_slack", "state"]]
              .round(4).to_string(index=False))

    print()
    print("=== 全部「营养下界」的状态统计（看谁在真正驱动解） ===")
    low = df[df.kind == "nutrient_lower"]
    summary = (
        low.groupby("name")
        .agg(
            n_tight=("state", lambda s: int((s == "tight").sum())),
            n_violated=("state", lambda s: int((s == "violated").sum())),
            n_total=("state", "size"),
            median_rel_slack=("rel_slack", "median"),
        )
        .sort_values(["n_tight", "median_rel_slack"], ascending=[False, True])
    )
    print(summary.round(4).to_string())

    fat_tight = int(
        ((df.kind == "nutrient_lower") & (df.name == "脂肪") & (df.state == "tight")).sum()
    )
    finalize_run(
        run_dir,
        {
            "command": "verify-binding-constraints",
            "scenario": args.scenario,
            "epsilon": args.epsilon,
            "provinces_used": usable,
            "provinces_skipped": skipped,
            "n_constraints": int(len(df)),
            "n_tight": int((df.state == "tight").sum()),
            "n_violated": int((df.state == "violated").sum()),
            "fat_lower_tight_count": fat_tight,
            "fat_lower_total": int(((df.kind == "nutrient_lower") & (df.name == "脂肪")).sum()),
            "evidence_status": "plumbing_only",
            "evidence_note": (
                "D1 确定性实例（省内价）的最优解约束余量诊断。"
                "目的只是正面检验「脂肪下界紧」这一因果主张，不是决策可靠性结果。"
                "violated 记录应只出现在 active_mask=False 的不可达营养素上（已知设计）。"
            ),
        },
        {
            "command": "verify-binding-constraints",
            "scenario": args.scenario,
            "epsilon": args.epsilon,
            "tol": TOL,
        },
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
