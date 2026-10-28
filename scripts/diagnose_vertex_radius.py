"""顶点稳定半径：目标方向要转多少度，推荐膳食才会变？

## 为什么需要这个数

前面的诊断把「不确定性进不了决策」拆成两层：

1. **结构层**（已证明）：目标对 ``q`` 线性、价格只进目标不进约束时，
   ``min E_s[c_s·q] = min (E_s c_s)·q``，期望最优 = 最优的期望，**精确为零**。
2. **CVaR 层**（已实测）：CVaR 对线性规划的唯一作用是**旋转成本方向**。
   旋转量很小——i.i.d. 对数正态扰动下 ``cv=0.05`` 只有 0.44–1.12°，
   即使把波动放大 10 倍到 ``cv=0.50`` 也只有 4.7–9.9°；
   换成组特异性冲击（单品类暴涨 1.5–3 倍）才升到 8.3–16.3°。

于是问题归结为：**这个旋转量够不够移动最优顶点？**
本脚本直接给出答案——不依赖场景分布，是可行域的**几何常数**：

> 稳定半径 ``θ*``：把成本方向从 ``c̄`` 转过 ``θ*`` 度时，最优解首次改变。

``θ*`` 大 → 该省的推荐膳食对目标方向不敏感，任何风险度量都改不了它；
``θ*`` 小 → 换个目标就换一套膳食，风险偏好必须交代。

## 方法

方向族取 ``c(θ) = a·cos θ + r⊥·sin θ``，其中 ``a = c̄/||c̄||``、
``r⊥`` 是随机方向在与 ``a`` 正交的子空间上的投影并归一化。
这样 ``c(θ)`` 与 ``c̄`` 的夹角**精确等于** ``θ``（不依赖小角近似）。
每省取 40 个随机 ``r⊥``，在网格 ``θ ∈ {0.5 … 30}`` 上逐点求解，
取首次出现 ``max|Δq| > 1e-4`` 的 ``θ`` 作为该方向的半径，报最小值与中位数。

跳过使 ``c(θ)`` 出现非正分量的方向（负价格无经济含义）。

## 判读

* ``θ*_min > 16.3`` → 连组特异性冲击（最强扰动）都改不了，结论对后验形态**稳健**；
* ``θ*_min`` 落在 4–10° → 真实后验的尾部方向一旦偏离均值超过这个角度，
  风险偏好就会改变推荐膳食，此时必须在论文里交代 ``λ``；
* ``θ*`` 跨省差异大 → 说明「要不要做鲁棒决策」不是全局问题，而是分省的。

用法：
    python scripts/diagnose_vertex_radius.py
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

SCOPE = "k6_price"
BASIS = "ear"
SCENARIOS = ("CDG", "EAT", "HEAL_base")
THETAS = (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0)
N_DIR = 40
SEED = 20261027
DQ_TOL = 1e-4


def _solve_det(inst, obj):
    mask = inst.active_mask
    return solve_chance_modopt(
        obj, inst.nutrient_coeff[:, mask, :],
        inst.nutrient_lower[mask], inst.nutrient_upper[mask],
        inst.q_lower, inst.q_upper, inst.objective_weights,
        epsilon=0.05, extra_constraints=inst.extra_constraints,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="DIAG_vertex_radius")
    args = ap.parse_args()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id)

    contract = Contract.load_scope(SCOPE)
    usable, _ = contract.complete_provinces()
    rng = np.random.default_rng(SEED)

    rows: list[dict] = []
    curve: list[dict] = []

    for scenario in SCENARIOS:
        for province in usable:
            inst = contract.instance(province, scenario, bounds_basis=BASIS)
            obj, _ = deterministic(inst)
            obj = np.asarray(obj, float)
            base = _solve_det(inst, obj)
            if not base.success:
                rows.append({"scenario": scenario, "province": province,
                             "solver_success": False})
                continue
            q_base = np.asarray(base.q, float)
            k = len(inst.groups)
            a = obj[0, 0, :].astype(float)
            a = a / np.linalg.norm(a)

            radii: list[float] = []
            for _ in range(N_DIR):
                r = rng.normal(size=k)
                r = r - (r @ a) * a
                norm = np.linalg.norm(r)
                if norm < 1e-9:
                    continue
                r = r / norm
                first = np.nan
                for deg in THETAS:
                    th = np.radians(deg)
                    c = a * np.cos(th) + r * np.sin(th)
                    if np.any(c <= 0):
                        continue
                    o = obj.copy()
                    o[:, 0, :] = c[None, :]
                    res = _solve_det(inst, o)
                    if not res.success:
                        continue
                    dq = float(np.abs(np.asarray(res.q, float) - q_base).max())
                    curve.append({
                        "scenario": scenario, "province": province,
                        "theta_deg": deg, "max_abs_dq": dq,
                    })
                    if dq > DQ_TOL and not np.isfinite(first):
                        first = deg
                        break
                radii.append(first)

            arr = np.asarray(radii, dtype=float)
            finite = arr[np.isfinite(arr)]
            rows.append({
                "scenario": scenario, "province": province,
                "solver_success": True,
                "n_dirs": int(len(arr)),
                "n_dirs_switched": int(np.isfinite(arr).sum()),
                "radius_min": float(finite.min()) if finite.size else np.inf,
                "radius_median": float(np.median(finite)) if finite.size else np.inf,
                "radius_max": float(finite.max()) if finite.size else np.inf,
                "never_switched_within_30": bool(finite.size == 0),
            })

    rdf = pd.DataFrame(rows)
    cdf = pd.DataFrame(curve)
    rdf.to_csv(run_dir / "vertex_radius.csv", index=False, encoding="utf-8-sig")
    cdf.to_csv(run_dir / "radius_curve.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 220)
    print("=== 顶点稳定半径（度）：目标方向转过这么多，推荐膳食首次改变 ===")
    print(rdf[["scenario", "province", "n_dirs_switched", "radius_min",
               "radius_median", "radius_max"]].to_string(index=False))

    print("\n=== 切换比例随角度的变化（该角度下已发生切换的方向占比）===")
    if not cdf.empty:
        cdf["switched"] = cdf["max_abs_dq"] > DQ_TOL
        frac = cdf.groupby(["theta_deg"])["switched"].mean()
        print(frac.round(3).to_string())

    ok = rdf[rdf["solver_success"].eq(True)]
    summary = {
        "min_radius_overall": float(ok["radius_min"].min()),
        "min_radius_cdg": float(ok[ok["scenario"].eq("CDG")]["radius_min"].min()),
        "median_radius_overall": float(ok["radius_median"].median()),
        "provinces_never_switch": int(ok["never_switched_within_30"].sum()),
        "provinces_total": int(len(ok)),
        "threshold_16_3_deg": 16.3,
    }
    print("\n=== 汇总 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    finalize_run(
        run_dir,
        {
            "command": "diagnose-vertex-radius",
            "evidence_status": "structural",
            "scope": SCOPE,
            "bounds_basis": BASIS,
            "scenarios": list(SCENARIOS),
            "thetas_deg": list(THETAS),
            "n_dir": N_DIR,
            "dq_tol": DQ_TOL,
            "evidence_note": (
                "可行域的几何常数，不依赖场景分布。"
                "θ 为成本方向与点估计方向 c̄ 的精确夹角"
            ),
            "summary": summary,
        },
        {"command": "diagnose-vertex-radius", "scope": SCOPE},
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
