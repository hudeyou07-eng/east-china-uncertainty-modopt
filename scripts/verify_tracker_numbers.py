"""数值准确性校验：把 tracker 里写下的关键数字逐条对回产物。

`check_tracker.py` 只验结构与引用可解析；本脚本验**数字本身**：
每一行断言都从 run 的 `metrics.json` / CSV 重新算一遍，再与 tracker 文本里
出现的字符串比对。任何一项对不上就 FAIL。

用法：
    python scripts/verify_tracker_numbers.py                        # 校验英文版
    python scripts/verify_tracker_numbers.py --file docs/EXPERIMENT_TRACKER.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "outputs"
B2_EAR = OUT / "R200_203_b2_formal_20261027_222841"
B2_RNI = OUT / "R200_203_b2_formal_20261027_224315"
M4 = OUT / "R400_406_provinces_20261028_183104"


def load_metrics(p: Path) -> dict:
    return json.loads((p / "metrics.json").read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", default="docs/EXPERIMENT_TRACKER_EN.md")
    args = ap.parse_args()
    text = (ROOT / args.file).read_text(encoding="utf-8")

    rows: list[tuple[str, object, bool, str]] = []

    def claim(name: str, computed, predicate, expected_text: str) -> None:
        ok = bool(predicate(computed)) and expected_text in text
        rows.append((name, computed, ok, expected_text))

    # ---- B2：主指标 ----
    ear, rni = load_metrics(B2_EAR), load_metrics(B2_RNI)
    claim("EAR D0 dq_change_rate = 0", ear["per_method"]["D0"]["dq_ref_change_rate"],
          lambda v: abs(v) < 1e-12, "0.000")
    claim("EAR D3 dq_change_rate = 0", ear["per_method"]["D3"]["dq_ref_change_rate"],
          lambda v: abs(v) < 1e-12, "0.000")
    claim("RNI D0 dq_change_rate = 0.460", round(rni["per_method"]["D0"]["dq_ref_change_rate"], 3),
          lambda v: abs(v - 0.460) < 5e-4, "0.460")
    claim("RNI D3 dq_change_rate = 0.333", round(rni["per_method"]["D3"]["dq_ref_change_rate"], 3),
          lambda v: abs(v - 0.333) < 5e-4, "0.333")
    claim("D2 dq_ref_mean ≈ 128.65", round(ear["per_method"]["D2"]["dq_ref_mean"], 2),
          lambda v: abs(v - 128.65) < 0.05, "128.65")
    claim("D2 flip_rate = 0.194", round(ear["per_method"]["D2"]["flip_rate"], 3),
          lambda v: abs(v - 0.194) < 5e-4, "0.194")

    # ---- M4：方向标签 ----
    cell = pd.read_csv(M4 / "m4_province_scenario.csv", encoding="utf-8-sig")
    lab = pd.read_csv(M4 / "m4_direction_labels.csv", encoding="utf-8-sig")
    ok_cells = cell[cell["status"] == "ok"]
    claim("M4 可解格 = 15", int(len(ok_cells)), lambda v: v == 15, "15/18")
    claim("M4 硬不可行格 = 3", int((cell["status"] == "hard_infeasible").sum()),
          lambda v: v == 3, "3 EAT cells hard-infeasible")
    claim("M4 平均一致率 = 0.956", round(float(ok_cells["direction_agreement"].mean()), 3),
          lambda v: abs(v - 0.956) < 5e-4, "0.956")
    counts = lab["label"].value_counts().to_dict()
    claim("标签 up=36", int(counts.get("stable-up", 0)), lambda v: v == 36, "up 36")
    claim("标签 down=49", int(counts.get("stable-down", 0)), lambda v: v == 49, "down 49")
    claim("标签 neutral=1", int(counts.get("stable-neutral", 0)), lambda v: v == 1, "neutral 1")
    claim("标签 data-sensitive=4", int(counts.get("data-sensitive", 0)), lambda v: v == 4, "data-sensitive 4")
    sens_scen = set(lab.loc[lab["label"] == "data-sensitive", "scenario"])
    claim("data-sensitive 全在 EAT", sorted(sens_scen), lambda v: v == ["EAT"], "all 4 data-sensitive cells are in EAT")

    # ---- R407 ----
    looro = pd.read_csv(OUT / "R407_looro_20261028_183054" / "m4_looro.csv", encoding="utf-8-sig")
    changed = looro[looro["n_direction_changed"] > 0]
    claim("R407 变化格 = 6", int(len(changed)), lambda v: v == 6, "6 cells flip")
    claim("R407 全在 EAT", sorted(changed["scenario"].unique()), lambda v: v == ["EAT"], "all in EAT")
    claim("R407 最大位移 ≈ 341.7", round(float(changed["dq_max"].max()), 1),
          lambda v: abs(v - 341.7) < 0.2, "339.3–341.7")

    # ---- R408 ----
    delta = pd.read_csv(OUT / "R408_delta_20261028_183131" / "m4_delta.csv", encoding="utf-8-sig")
    off = delta[(delta["solver_success"]) & (delta["delta"] != 0.0)]
    claim("R408 最大位移 ≤ 1e-8", float(off["dq_max_vs_delta0"].max()),
          lambda v: v <= 1e-8, "2.3e-9")

    # ---- R409 ----
    b = pd.read_csv(OUT / "R409_bounds_20261028_183421" / "m4_bounds.csv", encoding="utf-8-sig")
    claim("R409 solved = 12", int(b["solver_success"].sum()), lambda v: v == 12, "12 solved")
    claim("R409 low 不可行 = 6", int((~b[b["variant"] == "low"]["solver_success"]).sum()),
          lambda v: v == 6, "`low` 6 cells solver-infeasible")
    claim("R409 worst 空盒 = 6", int((b[b["variant"] == "worst"]["detail"] == "empty_box").sum()),
          lambda v: v == 6, "`worst` 6 cells empty box")
    claim("R409 high 最大位移 ≈ 92.05", round(float(b[b["variant"] == "high"]["dq_max_vs_mid"].max()), 2),
          lambda v: abs(v - 92.05) < 0.05, "92.05")

    # ---- R401 ----
    v401 = load_metrics(OUT / "R401_shanghai_availability_20261028_180508")
    claim("R401 k6 不可用", v401["can_enter_k6_price"], lambda v: v is False, "cannot enter `k6_price`")
    claim("R401 k4 可用", v401["can_enter_k4_official"], lambda v: v is True, "`k4_official` is assemblable")
    g07 = v401["groups_without_any_price"]
    claim("R401 G07 零价格年", "G07" in g07, lambda v: v is True, "**0/9**")

    # ---- 合同 gate ----
    gate = json.loads((ROOT / "data/processed/contract_gate_report.json").read_text(encoding="utf-8"))
    claim("合同 gate 7/7", f"{gate['passed']}/{gate['total']}",
          lambda v: v == "7/7", "Contract gates **7/7 PASS**")

    # ---- R505 ----
    r505 = load_metrics(OUT / "R505_reproducibility")
    claim("R505 verdict 含 PASS", r505["verdict"], lambda v: str(v).startswith("PASS"), "Automated part PASS")

    # ---- 输出 ----
    width = max(len(r[0]) for r in rows)
    bad = 0
    for name, value, ok, expect in rows:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            bad += 1
        print(f"{mark}  {name:<{width}}  实测={value!r:<28} 文档期望出现={expect!r}")
    print()
    if bad:
        print(f"结论：{bad}/{len(rows)} 项与 tracker 文本不一致。")
        return 1
    print(f"结论：{len(rows)} 项数值断言全部与 tracker 文本一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
