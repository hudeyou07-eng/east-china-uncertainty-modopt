"""R307 诊断：目标函数在当前设计下到底起多大作用？

## 为什么要做这个

CHANGELOG §14 曾把「价格不确定性对决策零传导」归因为
**「脂肪下界钉死了红肉量，模型退化为一个等式」**。

这个解释有两个可检验的推论：

1. 若红肉量真被钉死，则**任何目标权重**都得到同一个解；
2. 若解是唯一顶点，则可行域里不应存在多个可选顶点。

本脚本逐条检验，结论是**原解释只对了一半**：

* 脂肪下界确实在 6/6 省都紧（推论的前半部分成立）；
* 但可行域有 **12–14 个顶点**，成本在它们之间做选择，
  所以「红肉量被钉死」**不成立**（纯环境权重下浙江红肉 39.8 → 30.4 g）；
* 真正稳健的事实是：**成本与营养两个目标选到同一个顶点**，
  只有环境目标会换顶点。价格之所以「看起来无传导」，
  是因为**顶点间的成本排序对 ±5% 的价格扰动稳健**，
  要 20%–100% 才翻转（见 DIAG_decision_sensitivity）。

## 四步检验

1. `binding`：最优点处哪些约束紧（三态：tight / violated / slack）；
2. `rank`：紧约束矩阵的秩 → 基线解是否孤立顶点；
3. `vertices`：穷举可行域全部顶点；
4. `weights`：极端权重（纯成本 / 纯营养 / 纯环境）与随机权重的解对比。

用法::

    python scripts/diagnose_objective_degeneracy.py --scenario CDG --epsilon 0.05
"""

from __future__ import annotations

import argparse
import itertools
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
OBJ_NAMES = ("成本", "营养", "环境")


def _state(slack: float, scale: float, tol: float = TOL) -> str:
    """三态：违反 / 紧 / 有余量。

    **不能用「slack <= tol 即紧」**——那样会把违反（slack<0）也算成紧，
    两者含义完全相反。
    """
    rel = slack / scale
    if rel < -tol:
        return "violated"
    if abs(rel) <= tol:
        return "tight"
    return "slack"


def _linear_rows(inst, include_inactive: bool) -> list[tuple[np.ndarray, float, str, str]]:
    """把全部线性约束写成 (系数, 右端, 方向, 名称)。

    ``include_inactive=False`` 时只保留进入机会约束的营养素（active_mask），
    用于顶点枚举——否则不可达营养素会让可行域为空。
    """
    nm = inst.nutrient_coeff[0]
    rows: list[tuple[np.ndarray, float, str, str]] = []
    for j, name in enumerate(inst.nutrients):
        if not include_inactive and not inst.active_mask[j]:
            continue
        if np.isfinite(inst.nutrient_lower[j]):
            rows.append((nm[j], float(inst.nutrient_lower[j]), "ge", f"{name}≥"))
        if np.isfinite(inst.nutrient_upper[j]):
            rows.append((nm[j], float(inst.nutrient_upper[j]), "le", f"{name}≤"))
    for idx, (vec, lo, hi) in enumerate(inst.extra_constraints):
        vec = np.asarray(vec, dtype=float)
        if np.isfinite(lo):
            rows.append((vec, float(lo), "ge", f"joint#{idx}≥"))
        if np.isfinite(hi):
            rows.append((vec, float(hi), "le", f"joint#{idx}≤"))
    for k in range(inst.k_count):
        unit = np.zeros(inst.k_count)
        unit[k] = 1.0
        rows.append((unit, float(inst.q_lower[k]), "ge", f"{inst.groups[k]}=下界"))
        rows.append((unit, float(inst.q_upper[k]), "le", f"{inst.groups[k]}=上界"))
    return rows


def _solve(inst, obj, nut, weights, epsilon):
    return solve_chance_modopt(
        obj,
        nut[:, inst.active_mask, :],
        inst.nutrient_lower[inst.active_mask],
        inst.nutrient_upper[inst.active_mask],
        inst.q_lower,
        inst.q_upper,
        np.asarray(weights, dtype=float),
        epsilon=epsilon,
        extra_constraints=inst.extra_constraints,
    )


def _enumerate_vertices(inst) -> list[np.ndarray]:
    """穷举 K 个约束的交点，保留可行者。K=4 时组合数在万级，可接受。"""
    rows = _linear_rows(inst, include_inactive=False)
    k = inst.k_count
    found: set[tuple[float, ...]] = set()
    for combo in itertools.combinations(range(len(rows)), k):
        matrix = np.vstack([rows[i][0] for i in combo])
        if abs(np.linalg.det(matrix)) < 1e-9:
            continue
        rhs = np.array([rows[i][1] for i in combo])
        q = np.linalg.solve(matrix, rhs)
        if np.any(q < inst.q_lower - 1e-7) or np.any(q > inst.q_upper + 1e-7):
            continue
        feasible = True
        for vec, bound, direction, _ in rows:
            value = float(vec @ q)
            if direction == "ge" and value < bound - 1e-7:
                feasible = False
                break
            if direction == "le" and value > bound + 1e-7:
                feasible = False
                break
        if feasible:
            found.add(tuple(np.round(q, 6)))
    return [np.array(v, dtype=float) for v in sorted(found)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="CDG")
    ap.add_argument("--epsilon", type=float, default=0.05)
    ap.add_argument("--n-random", type=int, default=500)
    ap.add_argument("--seed", type=int, default=20261026)
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    contract = Contract.load()
    usable, skipped = contract.complete_provinces()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id or "DIAG_objective")
    rng = np.random.default_rng(args.seed)

    binding_rows: list[dict] = []
    vertex_rows: list[dict] = []
    weight_rows: list[dict] = []

    for province in usable:
        inst = contract.instance(province, args.scenario)
        if not inst.hard_feasible:
            continue
        obj, nut = deterministic(inst)
        base = _solve(inst, obj, nut, inst.objective_weights, args.epsilon)
        if not base.success:
            print(f"{province}: 基线求解失败 —— {base.message}")
            continue
        q_base = np.asarray(base.q, dtype=float)

        # ---- 1. 紧约束三态 + 2. 秩 ----
        nm = inst.nutrient_coeff[0]
        tight_vecs: list[np.ndarray] = []
        tight_names: list[str] = []
        for row in _linear_rows(inst, include_inactive=False):
            vec, bound, direction, name = row
            value = float(vec @ q_base)
            slack = value - bound if direction == "ge" else bound - value
            scale = max(abs(bound), abs(value), 1.0)
            state = _state(slack, scale)
            binding_rows.append(
                {
                    "province": province,
                    "constraint": name,
                    "bound": bound,
                    "achieved": value,
                    "slack": slack,
                    "rel_slack": slack / scale,
                    "state": state,
                }
            )
            if state == "tight":
                tight_vecs.append(vec)
                tight_names.append(name)
        rank = int(np.linalg.matrix_rank(np.vstack(tight_vecs), tol=1e-9)) if tight_vecs else 0

        # ---- 3. 顶点枚举 ----
        vertices = _enumerate_vertices(inst)
        for idx, q in enumerate(vertices):
            vertex_rows.append(
                {
                    "province": province,
                    "vertex": idx,
                    **{f"q_{g}": float(v) for g, v in zip(inst.groups, q)},
                    "is_base": bool(np.abs(q - q_base).max() < 1e-6),
                }
            )

        # ---- 4. 极端权重 + 随机权重 ----
        cases = {
            "原始": tuple(inst.objective_weights),
            "纯成本": (0.9998, 0.0001, 0.0001),
            "纯营养": (0.0001, 0.9998, 0.0001),
            "纯环境": (0.0001, 0.0001, 0.9998),
        }
        for name, weights in cases.items():
            res = _solve(inst, obj, nut, weights, args.epsilon)
            if not res.success:
                continue
            q = np.asarray(res.q, dtype=float)
            weight_rows.append(
                {
                    "province": province,
                    "case": name,
                    **{f"q_{g}": float(v) for g, v in zip(inst.groups, q)},
                    "objective": float(res.objective),
                    "max_abs_delta_vs_base": float(np.abs(q - q_base).max()),
                    "n_vertices": len(vertices),
                    "rank_tight": rank,
                    "k": inst.k_count,
                }
            )

        random_qs: list[np.ndarray] = []
        for _ in range(args.n_random):
            w = rng.dirichlet(np.ones(len(inst.objective_weights)))
            res = _solve(inst, obj, nut, w, args.epsilon)
            if res.success:
                random_qs.append(np.asarray(res.q, dtype=float))
        if random_qs:
            arr = np.vstack(random_qs)
            weight_rows.append(
                {
                    "province": province,
                    "case": f"随机权重×{args.n_random}",
                    **{f"q_{g}": float("nan") for g in inst.groups},
                    "objective": float("nan"),
                    "max_abs_delta_vs_base": float(np.abs(arr - q_base[None, :]).max()),
                    "n_vertices": len(vertices),
                    "rank_tight": rank,
                    "k": inst.k_count,
                    "n_distinct_solutions": len({tuple(np.round(a, 2)) for a in arr}),
                }
            )

        print(
            f"{province}: 顶点 {len(vertices)}，紧约束 {len(tight_names)} 条、秩 {rank}/{inst.k_count}"
            f"（零空间 {inst.k_count - rank} 维）"
        )
        print(f"    紧：{', '.join(tight_names)}")

    binding_df = pd.DataFrame(binding_rows)
    vertex_df = pd.DataFrame(vertex_rows)
    weight_df = pd.DataFrame(weight_rows)
    binding_df.to_csv(run_dir / "binding_constraints.csv", index=False, encoding="utf-8-sig")
    vertex_df.to_csv(run_dir / "vertices.csv", index=False, encoding="utf-8-sig")
    weight_df.to_csv(run_dir / "objective_cases.csv", index=False, encoding="utf-8-sig")

    print()
    print("=== 各营养下界的紧约束次数（谁在真正驱动解） ===")
    low = binding_df[binding_df.constraint.str.endswith("≥")]
    print(
        low.assign(nutrient=low.constraint.str.rstrip("≥"))
        .groupby("nutrient")
        .agg(
            n_tight=("state", lambda s: int((s == "tight").sum())),
            n_violated=("state", lambda s: int((s == "violated").sum())),
            n_total=("state", "size"),
        )
        .sort_values("n_tight", ascending=False)
        .to_string()
    )

    print()
    print("=== 极端权重下解是否移动（max |Δq| vs 原始） ===")
    pivot = weight_df.pivot_table(
        index="province", columns="case", values="max_abs_delta_vs_base"
    )
    print(pivot.round(2).to_string())

    fat_tight = int(
        (
            (binding_df.constraint == "脂肪≥") & (binding_df.state == "tight")
        ).sum()
    )
    fat_total = int((binding_df.constraint == "脂肪≥").sum())
    finalize_run(
        run_dir,
        {
            "command": "diagnose-objective-degeneracy",
            "scenario": args.scenario,
            "epsilon": args.epsilon,
            "n_random": args.n_random,
            "seed": args.seed,
            "provinces_used": usable,
            "provinces_skipped": skipped,
            "fat_lower_tight": f"{fat_tight}/{fat_total}",
            "vertices_per_province": vertex_df.groupby("province").size().to_dict(),
            "evidence_status": "plumbing_only",
            "evidence_note": (
                "确定性实例（省内价）的结构诊断，不是决策可靠性结果。"
                "结论只涉及「目标函数在本设计下能起多大作用」，不涉及最优解是否营养合理。"
            ),
        },
        {
            "command": "diagnose-objective-degeneracy",
            "scenario": args.scenario,
            "epsilon": args.epsilon,
            "n_random": args.n_random,
            "seed": args.seed,
            "tol": TOL,
        },
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
