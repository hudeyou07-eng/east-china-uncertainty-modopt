"""R307：边界门（boundary gate）开/关，结论标签会不会变？

## 问题

正式口径的边界门是「营养硬系数**全或无**」——11 个硬营养素里缺 1 项，该组就出局。
结果 K=4（蛋/禽/红肉/蔬菜）。但审计敏感性表显示：

| 口径 | 覆盖率门限 | K | 入组 |
|---|---|---|---|
| primary（正式） | 1.00，痕量算有效 | 4 | G02 G05 G06 G08 |
| 放宽 | 0.90，痕量**不**算有效 | **6** | G02 **G04** G05 G06 **G07** G08 |

多进来的 **G04（谷物及豆类）** 与 **G07（水产品）**，被挡的原因都只是
「11 项里差 1 项」。而 DIAG_objective 已证明 K=4 下可行域只有 12–14 个顶点、
价格传导需要 20%–100% 才翻转——**很可能就是决策维度太少造成的**。

所以本节点的核心问题不是「门限松紧哪个对」，而是：

> 「决策空间太窄」这个结论，是**数据的性质**，还是**边界门的产物**？

## 做法（不削弱正式门）

**正式门一个字节都不动。** 本脚本把 `data/processed/` 的契约文件复制到
run 目录下的 `shadow_processed/`，只替换其中 `group_audit.csv` 为放宽口径的审计表，
再让 `Contract.load` 指向这个影子目录。正式 `data/processed/` 不受影响。

## 指标

* ``k``、``vertices``（K>4 时跳过枚举，组合数爆炸）、``n_tight``、``rank``；
* ``price_d1_d0``：省内价 vs 合并价的 `max |Δq|`（价格传导的直接度量）；
* ``price_perturb_p50``：单组价格 ±50% 的 `max |Δq|`；
* 共同组（G02/G05/G06/G08）在 K=4 与 K=6 下的取值差 —— 结论标签的依赖程度。

## 证据等级

``plumbing_only``：场景为点估计。可采信的是**结构性对比**（顶点数、传导阈值、
共同组位移），不是绝对数值。

用法：
    python scripts/run_r307_gate_sensitivity.py
"""

from __future__ import annotations

import argparse
import itertools
import shutil
import sys
import time
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

COMMON = ("G02", "G05", "G06", "G08")
PERTURB = 0.50  # 单组价格 ±50%
MAX_ENUM_K = 4  # 顶点枚举的维度上限


def _solve(inst, obj, nut, epsilon):
    mask = inst.active_mask
    return solve_chance_modopt(
        obj,
        nut[:, mask, :],
        inst.nutrient_lower[mask],
        inst.nutrient_upper[mask],
        inst.q_lower,
        inst.q_upper,
        inst.objective_weights,
        epsilon=epsilon,
        extra_constraints=inst.extra_constraints,
    )


def _linear_rows(inst):
    nm = inst.nutrient_coeff[0]
    rows = []
    for j, name in enumerate(inst.nutrients):
        if not inst.active_mask[j]:
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


def _count_vertices(inst) -> int | None:
    if inst.k_count > MAX_ENUM_K:
        return None
    rows = _linear_rows(inst)
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
    return len(found)


def _build_shadow(audit_csv: Path, dest: Path) -> None:
    """复制契约文件到影子目录，只替换 group_audit.csv。"""
    dest.mkdir(parents=True, exist_ok=True)
    for src in (ROOT / "data" / "processed").iterdir():
        if src.is_file() and src.suffix in {".csv", ".json"}:
            shutil.copy2(src, dest / src.name)
    shutil.copy2(audit_csv, dest / "group_audit.csv")
    audit = pd.read_csv(dest / "group_audit.csv", encoding="utf-8-sig")
    if "include" not in audit.columns:
        raise ValueError("影子审计表缺 include 列")
    print(f"影子目录已建：{dest}")
    print(f"  include=1 的组：{sorted(audit.loc[audit['include'].astype(bool), 'group_id'])}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="CDG")
    ap.add_argument("--epsilon", type=float, default=0.05)
    ap.add_argument(
        "--relaxed-audit",
        default="data/processed/group_audit_sensitivity_c0.90.csv",
        help="放宽口径的审计表（默认 c0.90，K=6）",
    )
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    start = time.time()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id or "R307_gate")
    shadow = run_dir / "shadow_processed"
    _build_shadow(ROOT / args.relaxed_audit, shadow)

    official = Contract.load()
    relaxed = Contract.load(processed=shadow)
    print(f"正式口径 K={len(official.groups)}：{official.groups}")
    print(f"放宽口径 K={len(relaxed.groups)}：{relaxed.groups}")

    rows: list[dict] = []
    q_rows: list[dict] = []

    for scope, contract in (("official_K4", official), ("relaxed_K6", relaxed)):
        usable, skipped = contract.complete_provinces()
        print(f"\n[{scope}] 可用 {len(usable)} 省，跳过 {skipped}")
        for province in usable:
            try:
                inst = contract.instance(province, args.scenario)
            except ValueError as exc:
                rows.append(
                    {"scope": scope, "province": province, "error": str(exc)[:120]}
                )
                continue
            if not inst.hard_feasible:
                rows.append(
                    {
                        "scope": scope,
                        "province": province,
                        "k": inst.k_count,
                        "hard_feasible": False,
                        "conflict_set": ";".join(inst.conflict_set),
                    }
                )
                continue

            obj, nut = deterministic(inst)
            res = _solve(inst, obj, nut, args.epsilon)
            if not res.success:
                rows.append(
                    {
                        "scope": scope,
                        "province": province,
                        "k": inst.k_count,
                        "solve_success": False,
                        "message": res.message[:80],
                    }
                )
                continue
            q = np.asarray(res.q, dtype=float)

            # 价格传导：省内价 vs 合并价
            inst_pooled = contract.instance(province, args.scenario, price_mode="pooled")
            obj_p, nut_p = deterministic(inst_pooled)
            res_p = _solve(inst_pooled, obj_p, nut_p, args.epsilon)
            d_d1_d0 = (
                float(np.abs(np.asarray(res_p.q, dtype=float) - q).max())
                if res_p.success
                else float("nan")
            )

            # 单组价格 ±50%
            perturbs: list[float] = []
            for k_idx in range(inst.k_count):
                for sign in (1.0, -1.0):
                    obj2 = obj.copy()
                    obj2[0, 0, k_idx] *= 1.0 + sign * PERTURB  # 目标 0 = 成本
                    r2 = _solve(inst, obj2, nut, args.epsilon)
                    if r2.success:
                        perturbs.append(
                            float(np.abs(np.asarray(r2.q, dtype=float) - q).max())
                        )

            rows.append(
                {
                    "scope": scope,
                    "province": province,
                    "k": inst.k_count,
                    "hard_feasible": True,
                    "solve_success": True,
                    "objective": float(res.objective),
                    "vertices": _count_vertices(inst),
                    "n_tight": None,
                    "price_d1_d0": d_d1_d0,
                    "price_perturb_p50": float(np.median(perturbs)) if perturbs else float("nan"),
                    "price_perturb_max": float(np.max(perturbs)) if perturbs else float("nan"),
                    **{f"q_{g}": float(v) for g, v in zip(inst.groups, q)},
                }
            )
            q_rows.append(
                {
                    "scope": scope,
                    "province": province,
                    **{f"q_{g}": float(v) for g, v in zip(inst.groups, q)},
                }
            )
            print(
                f"  {province}: K={inst.k_count} 顶点={rows[-1]['vertices']} "
                f"D1vsD0={d_d1_d0:.2f}g  ±50%中位={rows[-1]['price_perturb_p50']:.2f}g"
            )

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "gate_sensitivity.csv", index=False, encoding="utf-8-sig")

    # 共同组的跨口径对比
    qdf = pd.DataFrame(q_rows)
    cmp_rows: list[dict] = []
    if not qdf.empty:
        wide = qdf.set_index(["scope", "province"])
        provinces = sorted(set(wide.index.get_level_values(1)))
        for province in provinces:
            if ("official_K4", province) not in wide.index:
                continue
            if ("relaxed_K6", province) not in wide.index:
                continue
            a = wide.loc[("official_K4", province)]
            b = wide.loc[("relaxed_K6", province)]
            row = {"province": province}
            deltas = []
            for g in COMMON:
                va, vb = float(a.get(f"q_{g}", np.nan)), float(b.get(f"q_{g}", np.nan))
                row[f"{g}_K4"] = va
                row[f"{g}_K6"] = vb
                row[f"{g}_delta"] = vb - va
                if np.isfinite(vb - va):
                    deltas.append(abs(vb - va))
            row["max_abs_delta_common"] = max(deltas) if deltas else float("nan")
            cmp_rows.append(row)
    cmp = pd.DataFrame(cmp_rows)
    if not cmp.empty:
        cmp.to_csv(run_dir / "common_group_compare.csv", index=False, encoding="utf-8-sig")
        print("\n=== 共同组在两种口径下的位移（g/day） ===")
        print(
            cmp[["province", "G02_delta", "G05_delta", "G06_delta", "G08_delta",
                 "max_abs_delta_common"]]
            .round(2)
            .to_string(index=False)
        )

    print("\n=== 价格传导对比 ===")
    ok = df[df.get("solve_success") == True]  # noqa: E712
    if not ok.empty:
        print(
            ok.groupby("scope")[["price_d1_d0", "price_perturb_p50", "price_perturb_max"]]
            .agg(["mean", "max"])
            .round(2)
            .to_string()
        )

    finalize_run(
        run_dir,
        {
            "command": "r307-gate-sensitivity",
            "scenario": args.scenario,
            "epsilon": args.epsilon,
            "official_k": len(official.groups),
            "relaxed_k": len(relaxed.groups),
            "official_groups": list(official.groups),
            "relaxed_groups": list(relaxed.groups),
            "relaxed_audit": args.relaxed_audit,
            "perturb": PERTURB,
            "wall_seconds": time.time() - start,
            "evidence_status": "plumbing_only",
            "evidence_note": (
                "正式门未改动：放宽口径通过影子 processed 目录装配，"
                "data/processed 保持原样。可采信的是结构性对比（顶点数、价格传导阈值、"
                "共同组位移），绝对数值不作结论。"
            ),
            "rows": df.to_dict("records"),
            "common_group_compare": cmp.to_dict("records") if not cmp.empty else [],
        },
        {
            "command": "r307-gate-sensitivity",
            "scenario": args.scenario,
            "epsilon": args.epsilon,
            "relaxed_audit": args.relaxed_audit,
        },
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
