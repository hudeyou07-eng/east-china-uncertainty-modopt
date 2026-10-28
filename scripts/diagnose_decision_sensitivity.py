"""诊断：最优解对目标系数的敏感度（平台宽度）。

**这不是预注册实验**，是回答「为什么 D0 与 D1 的解逐元素相同」的诊断工具。
结论用于决定 M2 的设计是否需要改（K、约束松紧、噪声量级），本身不作为论文证据。

背景：`src/b2_problem.py` 的决策变量是 K 个食物组的摄入量。最优解一定是可行多面体的
一个顶点，顶点由 K 条紧约束唯一确定。目标函数只在**顶点之间**选择，因此
「价格 → 决策」的映射是**分片常数**的：价格在一个区间（平台）内变动时解完全不变，
跨过平台边界才会跳到另一个顶点。

若平台宽度远大于噪声量级（如 5% CV），则：

- D0（合并价）与 D1（省内价）必然给出同一个解，与「均值填充 vs 后验均值」无关；
- 机会约束 D3 也只能在跨平台时才与 D0/D1 分叉；
- 论文里「价格不确定性影响决策」的机制在设计上**不可能被检测到**。

本脚本量化这个平台宽度：把某一组的价格乘子从 0.5 扫到 2.0，
找出使解发生变化的**最小乘子偏离**。

同时做对称的检查：把每个**活跃**营养素的系数乘子改成 0.9 / 1.1，
看解是否移动。这一步是为了回答「不确定性该加在哪一维」——
如果价格扰动 50% 不动、营养系数扰动 10% 就动，那么场景生成器把
不确定性全押在价格上是设计错误，不是数据限制。

用法：
    python scripts/diagnose_decision_sensitivity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.b2_problem import Contract  # noqa: E402
from src.io_utils import create_run_dir, finalize_run, write_json  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402

MULTIPLIERS = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 1.05, 1.10, 1.20, 1.30, 1.50, 2.00)
# 判定「解变了」的阈值。1 g/day 与 b2_evaluate 的方向容差一致。
CHANGE_TOL = 1.0


def _finite(obj):
    """把 inf/nan 递归换成 None，使 metrics.json 可被严格 JSON 解析。

    「扫遍 0.5–2.0 都没翻转」是合法结论，但 inf 不能写进 JSON。
    写成 null 并配合 direction="none" 表达，不能悄悄填一个大数。
    """
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


def solve_single(inst, objective_coeff: np.ndarray | None = None):
    mask = inst.active_mask
    coeff = inst.objective_coeff[:1] if objective_coeff is None else objective_coeff
    return solve_chance_modopt(
        coeff,
        inst.nutrient_coeff[:1][:, mask, :],
        inst.nutrient_lower[mask],
        inst.nutrient_upper[mask],
        inst.q_lower,
        inst.q_upper,
        inst.objective_weights,
        epsilon=0.0,
        extra_constraints=inst.extra_constraints,
    )


def tight_set(inst, q: np.ndarray, tol: float = 1e-5) -> list[str]:
    tight: list[str] = []
    for g, lo, hi, v in zip(inst.groups, inst.q_lower, inst.q_upper, q):
        if abs(v - lo) < tol:
            tight.append(f"{g}↓")
        elif abs(v - hi) < tol:
            tight.append(f"{g}↑")
    for coeff, lo, hi in inst.extra_constraints:
        val = float(np.asarray(coeff, dtype=float) @ q)
        if abs(val - lo) < tol:
            tight.append("联合↓")
        elif abs(val - hi) < tol:
            tight.append("联合↑")
    mask = inst.active_mask
    names = [n for n, m in zip(inst.nutrients, mask) if m]
    nmat = inst.nutrient_coeff[0][mask]
    lo_a = inst.nutrient_lower[mask]
    hi_a = inst.nutrient_upper[mask]
    val_a = nmat @ q
    for i, name in enumerate(names):
        if abs(val_a[i] - lo_a[i]) < tol:
            tight.append(f"{name}↓")
        elif np.isfinite(hi_a[i]) and abs(val_a[i] - hi_a[i]) < tol:
            tight.append(f"{name}↑")
    return tight


def main() -> int:
    contract = Contract.load()
    provinces, _ = contract.complete_provinces()
    run_dir = create_run_dir(ROOT / "outputs", "DIAG_decision_sensitivity")

    rows: list[dict] = []
    for province in provinces:
        inst = contract.instance(province, "CDG")
        if not inst.hard_feasible:
            rows.append(
                {
                    "province": province,
                    "group": "—",
                    "status": "hard_infeasible:" + "+".join(inst.conflict_set),
                }
            )
            continue

        base = solve_single(inst)
        q0 = base.q
        base_tight = tight_set(inst, q0)

        # 参考：价格口径从省内换到合并均值
        pool = contract.instance(province, "CDG", price_mode="pooled")
        q_pool = solve_single(pool).q
        rows.append(
            {
                "province": province,
                "group": "PRICE_MODE",
                "multiplier": 1.0,
                "delta_q_max": float(np.abs(q_pool - q0).max()),
                "changed": bool(np.abs(q_pool - q0).max() >= CHANGE_TOL),
                "tight_set": "|".join(base_tight),
                "q": "|".join(f"{v:.2f}" for v in q0),
            }
        )

        for k, group in enumerate(inst.groups):
            nearest: float | None = None
            for mult in MULTIPLIERS:
                obj = inst.objective_coeff[:1].copy()
                obj[0, 0, k] *= mult
                res = solve_single(inst, obj)
                if not res.success:
                    rows.append(
                        {
                            "province": province,
                            "group": group,
                            "multiplier": mult,
                            "delta_q_max": float("nan"),
                            "changed": False,
                            "tight_set": "INFEASIBLE",
                            "q": "",
                        }
                    )
                    continue
                delta = float(np.abs(res.q - q0).max())
                changed = delta >= CHANGE_TOL
                if changed and nearest is None:
                    nearest = mult
                rows.append(
                    {
                        "province": province,
                        "group": group,
                        "multiplier": mult,
                        "delta_q_max": delta,
                        "changed": changed,
                        "tight_set": "|".join(tight_set(inst, res.q)),
                        "q": "|".join(f"{v:.2f}" for v in res.q),
                    }
                )
            rows.append(
                {
                    "province": province,
                    "group": group,
                    "multiplier": float("nan"),
                    "delta_q_max": float("nan"),
                    "changed": bool(nearest is not None),
                    "tight_set": f"最近翻转乘子={nearest if nearest else '未翻转'}",
                    "q": "",
                }
            )

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "sensitivity_scan.csv", index=False, encoding="utf-8-sig")

    # 汇总：每个 (省, 组) 的最小翻转幅度
    summary = []
    scan = df[df["multiplier"].notna() & df["group"].ne("PRICE_MODE")]
    for (province, group), block in scan.groupby(["province", "group"]):
        flipped = block[block["changed"]]
        if flipped.empty:
            summary.append(
                {
                    "province": province,
                    "group": group,
                    "min_abs_pct_change_to_flip": np.inf,
                    "direction": "none",
                }
            )
            continue
        idx = flipped["multiplier"].sub(1.0).abs().idxmin()
        mult = float(flipped.loc[idx, "multiplier"])
        summary.append(
            {
                "province": province,
                "group": group,
                "min_abs_pct_change_to_flip": abs(mult - 1.0) * 100,
                "direction": "down" if mult < 1.0 else "up",
            }
        )
    summary_df = pd.DataFrame(summary).sort_values(
        ["province", "min_abs_pct_change_to_flip"]
    )
    summary_df.to_csv(run_dir / "flip_thresholds.csv", index=False, encoding="utf-8-sig")

    # ---- 营养系数扫描：对称检查「不确定性该加在哪一维」 ----
    nutrient_rows: list[dict] = []
    for province in provinces:
        inst = contract.instance(province, "CDG")
        if not inst.hard_feasible:
            continue
        q0 = solve_single(inst).q
        for j, nutrient in enumerate(inst.nutrients):
            if not inst.active_mask[j]:
                continue
            for mult in (0.9, 1.1):
                nmat = inst.nutrient_coeff[:1].copy()
                nmat[0, j, :] *= mult
                mask = inst.active_mask
                res = solve_chance_modopt(
                    inst.objective_coeff[:1],
                    nmat[:, mask, :],
                    inst.nutrient_lower[mask],
                    inst.nutrient_upper[mask],
                    inst.q_lower,
                    inst.q_upper,
                    inst.objective_weights,
                    epsilon=0.0,
                    extra_constraints=inst.extra_constraints,
                )
                delta = float(np.abs(res.q - q0).max()) if res.success else float("nan")
                nutrient_rows.append(
                    {
                        "province": province,
                        "nutrient": nutrient,
                        "multiplier": mult,
                        "delta_q_max": delta,
                        "changed": bool(np.isfinite(delta) and delta >= CHANGE_TOL),
                    }
                )
    nutrient_df = pd.DataFrame(nutrient_rows)
    nutrient_df.to_csv(run_dir / "nutrient_sensitivity.csv", index=False, encoding="utf-8-sig")

    price_mode = df[df["group"].eq("PRICE_MODE")][["province", "delta_q_max", "changed"]]
    metrics = {
        "command": "diagnose-decision-sensitivity",
        "purpose": "解释 D0 与 D1 解完全相同：价格→决策的映射是分片常数",
        "evidence_status": "diagnostic_only",
        "multipliers": list(MULTIPLIERS),
        "change_tolerance_g": CHANGE_TOL,
        "price_mode_effect": price_mode.to_dict("records"),
        "flip_thresholds": summary_df.to_dict("records"),
        "nutrient_sensitivity": (
            nutrient_df.groupby("nutrient")["changed"].mean().round(3).to_dict()
            if not nutrient_df.empty
            else {}
        ),
    }
    finalize_run(
        run_dir,
        _finite(metrics),
        {
            "command": "diagnose-decision-sensitivity",
            "multipliers": list(MULTIPLIERS),
            "change_tolerance_g": CHANGE_TOL,
        },
    )

    print(f"[diag] {len(df)} 行 | 省 {len(provinces)}")
    print()
    print("价格口径（省内 vs 合并均值）对解的影响：")
    print(price_mode.round(3).to_string(index=False))
    print()
    print("各 (省, 组) 使解发生变化的最小价格乘子偏离（%）：")
    piv = summary_df.pivot_table(
        index="province", columns="group", values="min_abs_pct_change_to_flip"
    )
    print(piv.round(0).to_string())
    if not nutrient_df.empty:
        print()
        print("营养系数 ±10% 扰动下解发生变化的比例（按营养素）：")
        share = (
            nutrient_df.groupby("nutrient")["changed"]
            .mean()
            .sort_values(ascending=False)
            .round(2)
        )
        print(share.to_string())
    print()
    print(f"[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
