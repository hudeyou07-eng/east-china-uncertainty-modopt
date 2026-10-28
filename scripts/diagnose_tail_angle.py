"""执行 §24.8 的预注册判定：逐省比较 `θ_tail` 与 `θ*`。

## 规则（预注册，见 CHANGELOG §24.8）

对每个省：

1. `θ_tail` = 尾部 10% 场景的成本方向与均值方向的夹角；
2. `θ*` = 该省可行域的顶点稳定半径（`DIAG_vertex_radius`，与后验无关）；
3. `θ_tail < θ*` → 该省 CVaR **可证明**无效，附录一句「已验证不敏感」；
4. `θ_tail ≥ θ*` → 该省**必须**报告 λ 敏感性曲线。

## 与 `diagnose_cvar_angle.py` 的区别

那个脚本用**占位**对数正态 / 组特异性冲击。本节按预注册要求换成
**B1 经验残差后验**（`src.b2_scenarios.posterior_scenarios`），
因为后验的组间离散度结构（G07 水产品 sd 0.377 vs G04 谷物豆类 0.124）
才是决定尾部方向的东西，占位噪声没有这个结构。

## 为什么要多 seed

200 个场景取 10% 尾部 = 20 个场景，`θ_tail` 的抽样误差不小。
单次取值可能把「差一点」的省判错。因此对每个 (情景, 省) 跑 `--seeds` 个独立种子，
报**中位数与 5–95 分位**，判定用中位数，并额外报告「判定翻转率」
（多少比例的种子会给出相反的结论）——若翻转率高，说明该省处于边界，需谨慎。

## 用法

    python scripts/diagnose_tail_angle.py
    python scripts/diagnose_tail_angle.py --vertex-run outputs/DIAG_vertex_radius_20261027_164952
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
from src.b2_scenarios import (  # noqa: E402
    B1_MASK_DEFAULT,
    B1_METHOD_DEFAULT,
    B1_RUN_DEFAULT,
    load_residual_pool,
    posterior_scenarios,
)
from src.io_utils import create_run_dir, finalize_run  # noqa: E402
from src.robust_modopt import solve_chance_modopt  # noqa: E402

SCOPE = "k6_price"
BASIS = "ear"
SCENARIOS = ("CDG", "EAT")
N_SCEN = 200
ALPHA = 0.90  # 尾部取最差 10%
SEEDS = tuple(range(20261027, 20261027 + 20))
VERTEX_RUN_DEFAULT = "outputs/DIAG_vertex_radius_20261027_164952"


def _solve(inst, obj, nut, lam):
    mask = inst.active_mask
    return solve_chance_modopt(
        obj, nut[:, mask, :],
        inst.nutrient_lower[mask], inst.nutrient_upper[mask],
        inst.q_lower, inst.q_upper, inst.objective_weights,
        epsilon=0.05, extra_constraints=inst.extra_constraints,
        risk_weight=lam, cvar_alpha=ALPHA,
    )


def _angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom <= 0:
        return float("nan")
    return float(np.degrees(np.arccos(np.clip(float(a @ b) / denom, -1.0, 1.0))))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_tail_angle")
    ap.add_argument("--vertex-run", default=VERTEX_RUN_DEFAULT)
    ap.add_argument("--seeds", type=int, default=len(SEEDS))
    ap.add_argument("--n-scen", type=int, default=N_SCEN)
    args = ap.parse_args()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    # ---- θ*：读已有的顶点稳定半径，不重算（它与后验无关）----
    vertex_csv = ROOT / args.vertex_run / "vertex_radius.csv"
    if not vertex_csv.exists():
        raise FileNotFoundError(f"找不到 {vertex_csv}，先跑 diagnose_vertex_radius.py")
    vr = pd.read_csv(vertex_csv, encoding="utf-8-sig")
    theta_star = {
        (r["scenario"], r["province"]): float(r["radius_min"])
        for _, r in vr.iterrows()
        if bool(r["solver_success"])
    }

    contract = Contract.load_scope(SCOPE)
    usable, _ = contract.complete_provinces()
    pool = load_residual_pool(
        ROOT / "outputs" / B1_RUN_DEFAULT, method=B1_METHOD_DEFAULT,
        mask_type=B1_MASK_DEFAULT, groups=contract.groups,
    )

    rows: list[dict] = []
    seeds = SEEDS[: args.seeds]
    for scenario in SCENARIOS:
        for province in usable:
            inst = contract.instance(province, scenario, bounds_basis=BASIS)
            star = theta_star.get((scenario, province), float("nan"))
            for seed in seeds:
                obj, nut = posterior_scenarios(
                    inst, args.n_scen, seed, pool=pool
                )
                r0 = _solve(inst, obj, nut, 0.0)
                r1 = _solve(inst, obj, nut, 1.0)
                if not (r0.success and r1.success):
                    rows.append({
                        "scenario": scenario, "province": province, "seed": seed,
                        "status": "solver_failed", "theta_tail_deg": float("nan"),
                        "theta_star_deg": star, "max_abs_dq": float("nan"),
                    })
                    continue
                q1 = np.asarray(r1.q, float)
                cmat = np.asarray(obj, float)[:, 0, :]  # [S, K]
                costs = cmat @ q1
                n_tail = max(1, int(round((1.0 - ALPHA) * len(costs))))
                tail = np.argsort(costs)[-n_tail:]
                theta = _angle_deg(cmat.mean(axis=0), cmat[tail].mean(axis=0))
                rows.append({
                    "scenario": scenario, "province": province, "seed": seed,
                    "status": "ok",
                    "theta_tail_deg": theta,
                    "theta_star_deg": star,
                    "max_abs_dq": float(np.abs(q1 - np.asarray(r0.q, float)).max()),
                    "tail_cost_ratio": float(costs[tail].mean() / costs.mean()),
                })

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "tail_angle.csv", index=False, encoding="utf-8-sig")
    n_failed = int((~df["status"].eq("ok")).sum()) if len(df) else 0
    failed_cells = sorted(
        f"{r['scenario']}/{r['province']}"
        for _, r in df[~df["status"].eq("ok")][["scenario", "province"]]
        .drop_duplicates().iterrows()
    )

    # ---- 逐 (情景, 省) 汇总 + 判定 ----
    agg_rows: list[dict] = []
    for (scenario, province), sub in df[df["status"].eq("ok")].groupby(
        ["scenario", "province"], sort=True
    ):
        th = sub["theta_tail_deg"].to_numpy(dtype=float)
        star = float(sub["theta_star_deg"].iloc[0])
        med = float(np.median(th))
        verdict = "CVaR 可证明无效（θ_tail < θ*）" if med < star else "必须报告 λ 曲线（θ_tail ≥ θ*）"
        flip = float(np.mean(th >= star))
        agg_rows.append({
            "scenario": scenario,
            "province": province,
            "theta_star_deg": star,
            "theta_tail_median_deg": med,
            "theta_tail_p05_deg": float(np.percentile(th, 5)),
            "theta_tail_p95_deg": float(np.percentile(th, 95)),
            "ratio_median_over_star": med / star if star else float("nan"),
            "verdict": verdict,
            "verdict_flip_rate": flip,
            "max_abs_dq_median": float(sub["max_abs_dq"].median()),
            "n_seeds": int(len(sub)),
        })
    agg = pd.DataFrame(agg_rows).sort_values(["scenario", "ratio_median_over_star"])
    agg.to_csv(run_dir / "tail_angle_summary.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 240)
    print("=== θ_tail 与 θ* 逐省比较（B1 经验残差后验）===")
    print(
        agg[["scenario", "province", "theta_star_deg", "theta_tail_median_deg",
             "theta_tail_p05_deg", "theta_tail_p95_deg", "ratio_median_over_star",
             "max_abs_dq_median", "verdict_flip_rate"]]
        .round(3).to_string(index=False)
    )
    print("\n=== 判定 ===")
    for _, r in agg.iterrows():
        flag = "" if r["verdict_flip_rate"] in (0.0, 1.0) else "  ← 边界，判定不稳定"
        print(f"  {r['scenario']}/{r['province']}: {r['verdict']}{flag}")

    n_ok = int((agg["verdict_flip_rate"].eq(0.0)).sum())
    n_bad = int((agg["verdict_flip_rate"].eq(1.0)).sum())
    summary = {
        "theta_star_source": args.vertex_run,
        "n_scen": args.n_scen,
        "alpha": ALPHA,
        "n_seeds": len(seeds),
        "n_cells": int(len(agg)),
        "n_rows": int(len(df)),
        "n_solver_failed": n_failed,
        "cells_all_failed": failed_cells,
        "cells_cvar_ineffective": n_ok,
        "cells_must_report_lambda": n_bad,
        "cells_boundary_unstable": int(len(agg) - n_ok - n_bad),
        "theta_tail_max_deg": float(agg["theta_tail_median_deg"].max()),
        "ratio_max": float(agg["ratio_median_over_star"].max()),
    }
    print("\n=== 汇总 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    finalize_run(
        run_dir,
        {
            "command": "diagnose-tail-angle",
            "evidence_status": "structural",
            "scope": SCOPE,
            "bounds_basis": BASIS,
            "scenarios": list(SCENARIOS),
            "n_scen": args.n_scen,
            "alpha": ALPHA,
            "seeds": list(seeds),
            "b1_run": B1_RUN_DEFAULT,
            "b1_method": B1_METHOD_DEFAULT,
            "b1_mask_type": B1_MASK_DEFAULT,
            "theta_star_source": args.vertex_run,
            "evidence_note": (
                "执行 CHANGELOG §24.8 的预注册判定。θ_tail 用 B1 经验残差后验计算，"
                "θ* 取自 diagnose_vertex_radius（与后验无关）。"
                "verdict_flip_rate 是 20 个种子里给出相反判定的比例，0/1 表示稳定。"
                "evidence_status=structural：这是诊断，不是预注册的重复实验协议；"
                "EAT 下山东/江苏/浙江结构性不可行，20 个种子全部求解失败，不计入 n_cells。"
            ),
            "summary": summary,
        },
        {"command": "diagnose-tail-angle", "scope": SCOPE},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
