"""R307b：边界门的 2×2 因子分解 —— 到底哪个旋钮在起作用？

## 为什么要重做 R307

R307 比较了「正式 K=4」与「放宽 K=6」，但**同时改了两个东西**：

1. `trace_as_valid`（痕量格算不算有效观测）True → False；
2. `min_cell_coverage`（覆盖率门限）1.0 → 0.90。

两处同时动，结论归因不清。更麻烦的是，`scripts/build_group_audit.py` 的
营养门是**双分支**，两条分支用的判据根本不同：

```python
if min_cell_coverage >= 1.0:
    gate = 每个营养素的组内食物覆盖都 == 1.0        # 全或无
else:
    gate = 组内整体格子比例 >= min_cell_coverage     # 平均比例
```

也就是说 **c=1.0 与 c=0.999 不是同一条规则的松紧，而是两条不同规则**。
所以「门限敏感性」表（0.80/0.85/0.90/0.95/1.00）把一次**判据切换**
混在了一列阈值里——这不是阈值敏感性，是模型定义变了。

## 本脚本做的事

对 2×2 四个口径各装配一次决策模型（影子目录，正式门不动），比较：

| 口径 | trace | c | 预期 K |
|---|---|---|---|
| A 正式 | True | 1.00 | 4（G02 G05 G06 G08）|
| B | True | 0.95 | 6（+G04 +G07）|
| C 预注册 K=3 | False | 1.00 | 3（G02 G05 G08）|
| D | False | 0.95 | 5（+G04）|

指标：K、可用省份、山东是否硬可行、价格 D1vsD0 位移、共同组相对 A 的位移。

**这样能回答**：价格传导的恢复是靠 G04、靠 G07，还是靠「K 变大」本身？
如果 D（K=5，只有 G04）就已经恢复，那 G07 不必进；如果只有 B（K=6）恢复，
说明水产品的替代作用不可替代。

## 证据等级

``plumbing_only``：场景为点估计。可采信的是结构性对比，不是绝对数值。

用法：
    python scripts/run_r307b_gate_factorial.py
"""

from __future__ import annotations

import argparse
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
VARIANTS = (
    ("A_official", "trace=True,c=1.00", "group_audit.csv"),
    ("B_trace_c095", "trace=True,c=0.95", "group_audit_trace_c0.95.csv"),
    ("C_k3_strict", "trace=False,c=1.00", "group_audit_k3_strict.csv"),
    ("D_notrace_c095", "trace=False,c=0.95", "group_audit_notrace_c0.95.csv"),
)


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


def _shadow(audit_csv: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for src in (ROOT / "data" / "processed").iterdir():
        if src.is_file() and src.suffix in {".csv", ".json"}:
            shutil.copy2(src, dest / src.name)
    shutil.copy2(audit_csv, dest / "group_audit.csv")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="CDG")
    ap.add_argument("--epsilon", type=float, default=0.05)
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    start = time.time()
    run_dir = create_run_dir(ROOT / "outputs", args.run_id or "R307b_gate_factorial")

    rows: list[dict] = []
    q_rows: list[dict] = []

    for key, label, audit_name in VARIANTS:
        audit = ROOT / "data" / "processed" / audit_name
        if not audit.exists():
            print(f"[{key}] 缺审计表 {audit_name}，跳过")
            continue
        shadow = run_dir / f"shadow_{key}"
        _shadow(audit, shadow)
        contract = Contract.load(processed=shadow)
        usable, skipped = contract.complete_provinces()
        print(f"\n[{key}] {label}  K={len(contract.groups)} groups={contract.groups}")
        print(f"        可用 {len(usable)} 省；跳过 {skipped}")

        for province in usable:
            try:
                inst = contract.instance(province, args.scenario)
            except ValueError as exc:
                rows.append({"variant": key, "label": label, "province": province,
                             "error": str(exc)[:100]})
                continue
            if not inst.hard_feasible:
                rows.append({
                    "variant": key, "label": label, "province": province,
                    "k": inst.k_count, "hard_feasible": False,
                    "conflict_set": ";".join(inst.conflict_set),
                })
                continue

            obj, nut = deterministic(inst)
            res = _solve(inst, obj, nut, args.epsilon)
            if not res.success:
                rows.append({"variant": key, "label": label, "province": province,
                             "k": inst.k_count, "solve_success": False,
                             "message": res.message[:60]})
                continue
            q = np.asarray(res.q, dtype=float)

            inst0 = contract.instance(province, args.scenario, price_mode="pooled")
            obj0, nut0 = deterministic(inst0)
            r0 = _solve(inst0, obj0, nut0, args.epsilon)
            d_d1d0 = (
                float(np.abs(np.asarray(r0.q, dtype=float) - q).max()) if r0.success else float("nan")
            )
            rel = np.abs(inst.objective_coeff[0, 0] / inst0.objective_coeff[0, 0] - 1.0)

            rows.append({
                "variant": key, "label": label, "province": province,
                "k": inst.k_count, "hard_feasible": True, "solve_success": True,
                "objective": float(res.objective),
                "price_d1_d0": d_d1d0,
                "price_max_rel_change_pct": float(rel.max() * 100),
                **{f"q_{g}": float(v) for g, v in zip(inst.groups, q)},
            })
            q_rows.append({"variant": key, "province": province,
                           **{f"q_{g}": float(v) for g, v in zip(inst.groups, q)}})

    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "gate_factorial.csv", index=False, encoding="utf-8-sig")

    qdf = pd.DataFrame(q_rows)
    cmp_rows: list[dict] = []
    if not qdf.empty and "A_official" in set(qdf.variant):
        wide = qdf.set_index(["variant", "province"])
        for variant in [v for v, _, _ in VARIANTS if v != "A_official"]:
            for province in sorted(set(wide.index.get_level_values(1))):
                if (variant, province) not in wide.index:
                    continue
                if ("A_official", province) not in wide.index:
                    continue
                a = wide.loc[("A_official", province)]
                b = wide.loc[(variant, province)]
                deltas = [
                    abs(float(b.get(f"q_{g}", np.nan)) - float(a.get(f"q_{g}", np.nan)))
                    for g in COMMON
                    if np.isfinite(b.get(f"q_{g}", np.nan)) and np.isfinite(a.get(f"q_{g}", np.nan))
                ]
                cmp_rows.append({
                    "variant": variant, "province": province,
                    "max_abs_delta_common": max(deltas) if deltas else float("nan"),
                    **{f"{g}_delta": float(b.get(f"q_{g}", np.nan)) - float(a.get(f"q_{g}", np.nan))
                       for g in COMMON},
                })
    cmp = pd.DataFrame(cmp_rows)
    if not cmp.empty:
        cmp.to_csv(run_dir / "common_group_compare.csv", index=False, encoding="utf-8-sig")

    print("\n=== 四口径总览 ===")
    ok = df[df.get("solve_success") == True]  # noqa: E712
    overview = (
        df.groupby(["variant", "label"])
        .agg(
            k=("k", "first"),
            n_provinces=("province", "size"),
            n_solved=("solve_success", "sum"),
            n_hard_infeasible=("hard_feasible", lambda s: int((s == False).sum())),  # noqa: E712
        )
        .reset_index()
    )
    print(overview.to_string(index=False))

    print("\n=== 价格传导：D1 vs D0 的 max|Δq|（g/day） ===")
    if not ok.empty:
        print(
            ok.pivot_table(index="province", columns="variant", values="price_d1_d0")
            .round(2)
            .to_string()
        )

    print("\n=== 山东在四口径下的状态 ===")
    sd = df[df.province == "山东"][["variant", "label", "k", "hard_feasible", "conflict_set"]]
    print(sd.to_string(index=False))

    if not cmp.empty:
        print("\n=== 共同组相对正式口径的位移（g/day） ===")
        print(
            cmp.pivot_table(index="province", columns="variant", values="max_abs_delta_common")
            .round(2)
            .to_string()
        )

    finalize_run(
        run_dir,
        {
            "command": "r307b-gate-factorial",
            "scenario": args.scenario,
            "epsilon": args.epsilon,
            "variants": [{"key": k, "label": lab, "audit": a} for k, lab, a in VARIANTS],
            "wall_seconds": time.time() - start,
            "evidence_status": "plumbing_only",
            "evidence_note": (
                "2×2 因子设计，隔离 trace_as_valid 与 min_cell_coverage 两个旋钮。"
                "正式门未改动（影子目录装配）。"
                "注意 min_cell_coverage 在 1.0 处存在判据切换（全或无 vs 平均比例），"
                "因此这不是纯粹的阈值敏感性。"
            ),
            "overview": overview.to_dict("records"),
            "rows": df.to_dict("records"),
        },
        {
            "command": "r307b-gate-factorial",
            "scenario": args.scenario,
            "epsilon": args.epsilon,
        },
    )
    print(f"\n[run] {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
