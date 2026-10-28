"""R107：交互项启用条件的门控判定（对既有扫描产物的只读复算）。

## 背景

`outputs/B1_interaction_sweep_20261023_141000` 已被审计标记为 INCOMPLETE
（缺 `metrics.json` / `config.json` / `environment.json` / `DONE`，见
`docs/archive/AUDIT_2026-10-26.md` P2-2 / P2-3）。**该 run 本身不可作为有效 run 引用。**

但它留下的 `tuning.csv`（14 个配置 × 3 种掩码）与 `heldout.csv`
（3 个配置 × 3 种掩码）足以回答 R107 的唯一问题：
**加入 region×group 交互项，是否在调参与留出两侧同时改善？**

本脚本只读这两个 CSV，不重跑、不修改原目录，把判定结果写成独立文件。
这样结论可引用，而原始 run 的 INCOMPLETE 状态不被掩盖。

## 预注册的判定准则

「both improve」= 在 **调参集** 与 **留出集** 上，候选配置的
尺度化 MAE 相对 `default` 的比值都 < 1，且**三种掩码都不能出现显著退化**
（退化阈值 5%，即比值 > 1.05 视为退化）。

不采用「平均改善即可」的宽松口径——那会让「一种掩码大幅改善、
另一种明显变差」被平均掉，而这正是交互项最可能出问题的地方。

用法：
    python scripts/interaction_gate.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SWEEP = ROOT / "outputs" / "B1_interaction_sweep_20261023_141000"
OUT = ROOT / "outputs" / "R107_interaction_gate"

BASELINE = "default"
DEGRADE_TOL = 1.05  # 比值 > 1.05 记为「退化」
METRIC = "scaled_mae"


def _ratio_table(frame: pd.DataFrame, baseline: str) -> pd.DataFrame:
    base = frame[frame["config"].eq(baseline)].set_index("mask_type")[METRIC]
    rows = []
    for config, block in frame.groupby("config"):
        if config == baseline:
            continue
        row = {"config": config}
        for mask_type, value in block.set_index("mask_type")[METRIC].items():
            row[mask_type] = float(value / base[mask_type])
        row["mean_ratio"] = float(sum(v for k, v in row.items() if k != "config") / 3.0)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("mean_ratio").reset_index(drop=True)


def main() -> None:
    tuning = pd.read_csv(SWEEP / "tuning.csv")
    heldout = pd.read_csv(SWEEP / "heldout.csv")
    for name, frame in (("tuning", tuning), ("heldout", heldout)):
        if BASELINE not in set(frame["config"]):
            raise SystemExit(f"{name}.csv 缺基线配置 {BASELINE!r}，无法做相对比较")

    tune_ratio = _ratio_table(tuning, BASELINE)
    held_ratio = _ratio_table(heldout, BASELINE)

    # 只有同时出现在两侧的配置才能判定
    common = sorted(set(tune_ratio["config"]) & set(held_ratio["config"]))
    verdicts = []
    for config in common:
        t = tune_ratio.set_index("config").loc[config]
        h = held_ratio.set_index("config").loc[config]
        masks = [c for c in tuning["mask_type"].unique()]
        tune_all = all(t[m] < 1.0 for m in masks)
        held_all = all(h[m] < 1.0 for m in masks)
        tune_no_regress = all(t[m] <= DEGRADE_TOL for m in masks)
        held_no_regress = all(h[m] <= DEGRADE_TOL for m in masks)
        verdicts.append(
            {
                "config": config,
                "tuning_mean_ratio": float(t["mean_ratio"]),
                "heldout_mean_ratio": float(h["mean_ratio"]),
                "tuning_all_masks_improve": bool(tune_all),
                "heldout_all_masks_improve": bool(held_all),
                "no_mask_degrades": bool(tune_no_regress and held_no_regress),
                "both_improve_strict": bool(tune_all and held_all),
                "gate_pass": bool(tune_all and held_all and tune_no_regress and held_no_regress),
                "worst_mask_tuning": str(t.drop("mean_ratio").idxmax()),
                "worst_mask_heldout": str(h.drop("mean_ratio").idxmax()),
            }
        )
    verdict = pd.DataFrame(verdicts).sort_values("heldout_mean_ratio")

    OUT.mkdir(parents=True, exist_ok=True)
    tune_ratio.to_csv(OUT / "tuning_ratio_vs_default.csv", index=False, encoding="utf-8-sig")
    held_ratio.to_csv(OUT / "heldout_ratio_vs_default.csv", index=False, encoding="utf-8-sig")
    verdict.to_csv(OUT / "interaction_gate.csv", index=False, encoding="utf-8-sig")

    print("[R107] 只读复算，源 run 仍为 INCOMPLETE，不作为有效 run 引用")
    print(f"源目录: {SWEEP.relative_to(ROOT)}")
    print(f"\n判定准则：{METRIC} 相对 {BASELINE} 的比值，三种掩码全部 <1 才算 both improve；"
          f"任一抹码 >{DEGRADE_TOL} 记为退化\n")
    print(verdict.round(4).to_string(index=False))

    passed = verdict[verdict["gate_pass"]]
    conclusion = {
        "source_run": str(SWEEP.relative_to(ROOT)),
        "source_run_status": "INCOMPLETE (不得作为有效 run 引用)",
        "metric": METRIC,
        "baseline": BASELINE,
        "degrade_tolerance": DEGRADE_TOL,
        "configs_compared": common,
        "gate_pass": passed["config"].tolist(),
        "gate_conclusion": (
            "both improve 成立" if len(passed) else "both improve 不成立（无配置通过严格门控）"
        ),
        "detail": verdict.to_dict("records"),
    }
    (OUT / "interaction_gate.json").write_text(
        json.dumps(conclusion, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n结论: {conclusion['gate_conclusion']}")
    print(f"[written] {OUT.relative_to(ROOT)}/interaction_gate.json")


if __name__ == "__main__":
    main()
