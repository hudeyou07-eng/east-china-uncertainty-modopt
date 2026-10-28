"""M5 图表与交付：把原始 run 产物转成论文表/图（R500–R504）。

## 设计原则

1. **只读既有产物**，不重跑任何求解；因此这一层永远不会改变结论。
2. **不引入新依赖**：仓库 `requirements.txt` 没有 matplotlib，图形直接写 SVG
   （纯文本、可 diff、可被脚本校验），数据另存 CSV 供重绘。
3. **每个产物可追溯**：`artifact_manifest.json` 记录每个文件的 sha256 与其源 run 目录。

## 产物与 run 的对应

| run | 产物 | 源 |
|---|---|---|
| R500 | `table1_price.csv` / `table1_consumption.csv` / `table1.md` | B1 两个面板的 `calibration_summary.csv` |
| R501 | `table2_decision.csv` / `table2.md` | B2 的 EAR / RNI 两个 `metrics.json` |
| R502 | `figure1_stable_flip.csv` / `figure1.svg` | M4 的 `m4_direction_labels.csv` |
| R503 | `figure2_regional_heatmap.csv` / `figure2.svg` | 同上（CDG 情景） |
| R504 | `appendix_index.md` / `artifact_manifest.json` | 本目录全部产物 |

## 用法

    python scripts/build_paper_artifacts.py
    python scripts/build_paper_artifacts.py --run-id R500_504_paper_artifacts
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.io_utils import create_run_dir, finalize_run  # noqa: E402

OUTPUT_ROOT = ROOT / "outputs"
B1_PRICE = OUTPUT_ROOT / "B1_formal_withmice_20261023_124906"
B1_CONS = OUTPUT_ROOT / "R103_105_consumption_formal_20261026_174725"
B2_EAR = OUTPUT_ROOT / "R200_203_b2_formal_20261027_222841"
B2_RNI = OUTPUT_ROOT / "R200_203_b2_formal_20261027_224315"
M4 = OUTPUT_ROOT / "R400_406_provinces_20261028_183104"

LABELS = ("stable-up", "stable-down", "stable-neutral", "data-sensitive")
COLORS = {
    "stable-up": "#2b8a3e",
    "stable-down": "#c92a2a",
    "stable-neutral": "#adb5bd",
    "data-sensitive": "#f08c00",
}
LABEL_EN = {
    "stable-up": "Stable up",
    "stable-down": "Stable down",
    "stable-neutral": "Neutral",
    "data-sensitive": "Data-sensitive",
}
SHORT_EN = {
    "stable-up": "UP",
    "stable-down": "DOWN",
    "stable-neutral": "FLAT",
    "data-sensitive": "SENS",
}
PROVINCE_EN = {
    "安徽": "Anhui",
    "山东": "Shandong",
    "江苏": "Jiangsu",
    "江西": "Jiangxi",
    "浙江": "Zhejiang",
    "福建": "Fujian",
    "上海": "Shanghai",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def assert_viewbox(svg: list[str], w: int, h: int) -> None:
    """任何元素越出画布就失败。

    这条检查是被一次真实的排版错误逼出来的（2026-10-28）：图 1 的图例 y=416，
    而画布高 420，图例整体被裁在可视区外。机器能验「没越界」，人才能验「好不好看」。
    """
    for ln in svg:
        s = ln.lstrip()
        if s.startswith("<svg") or s.startswith("</") or not (s.startswith("<rect") or s.startswith("<text")):
            continue
        x = re.search(r'\bx="(-?[\d.]+)"', ln)
        y = re.search(r'\by="(-?[\d.]+)"', ln)
        if s.startswith("<rect"):
            ww = re.search(r'\bwidth="([\d.]+)"', ln)
            hh = re.search(r'\bheight="([\d.]+)"', ln)
            x0 = float(x.group(1)) if x else 0.0
            y0 = float(y.group(1)) if y else 0.0
            w1 = float(ww.group(1)) if ww else 0.0
            h1 = float(hh.group(1)) if hh else 0.0
            if x0 + w1 > w + 0.5 or y0 + h1 > h + 0.5:
                raise AssertionError(f"rect 越界：x+w={x0 + w1:.1f}, y+h={y0 + h1:.1f}，画布 {w}x{h}")
        else:
            x0 = float(x.group(1)) if x else 0.0
            y0 = float(y.group(1)) if y else 0.0
            if y0 > h - 2 or x0 > w:
                raise AssertionError(f"text 越界：x={x0:.1f}, y={y0:.1f}，画布 {w}x{h}")


# ---------------------------------------------------------------- R500
def build_table1(run_dir: Path) -> list[str]:
    frames = []
    for panel, src in (("price", B1_PRICE), ("consumption", B1_CONS)):
        d = pd.read_csv(src / "calibration_summary.csv", encoding="utf-8-sig")
        d.insert(0, "panel", panel)
        frames.append(d)
        d.to_csv(run_dir / f"table1_{panel}.csv", index=False, encoding="utf-8-sig")
    allp = pd.concat(frames, ignore_index=True)

    lines = [
        "# Table 1 — 插补方法的点精度与区间校准（R100–R105）",
        "",
        "两份面板各 5 折 × 20 重复 × 3 种遮蔽几何。`coverage95` 名义值 0.95，",
        "`scaled_mae` 越小越好。**点精度与标定不是同一件事**：MICE 点误差最低但在",
        "`province_group` 上崩溃（价格 sMAE 1.18 / 覆盖 0.733；消费 sMAE 1.000 / 覆盖 0.079）。",
        "",
    ]
    for panel in ("price", "consumption"):
        d = allp[allp["panel"] == panel]
        lines += [f"## {panel}", "", "| mask | method | n_eval | sMAE | logRMSE | cov80 | cov95 | width95 |",
                  "|---|---|---|---|---|---|---|---|"]
        for _, r in d.iterrows():
            lines.append(
                f"| {r['mask_type']} | {r['method']} | {r['n_eval']} | {r['scaled_mae']:.4f} | "
                f"{r['log_rmse']:.4f} | {r['coverage80']:.3f} | {r['coverage95']:.3f} | {r['width95']:.2f} |"
            )
        lines.append("")
    (run_dir / "table1.md").write_text("\n".join(lines), encoding="utf-8")
    return ["table1_price.csv", "table1_consumption.csv", "table1.md"]


# ---------------------------------------------------------------- R501
def build_table2(run_dir: Path) -> list[str]:
    rows = []
    for basis, src in (("ear", B2_EAR), ("rni", B2_RNI)):
        import json

        m = json.loads((src / "metrics.json").read_text(encoding="utf-8"))
        for method, v in m["per_method"].items():
            rows.append({
                "bounds_basis": basis,
                "method": method,
                "n_repeats": v["n_repeats"],
                "feasible_active_rate": v["feasible_active_rate"],
                "feasible_all_rate": v["feasible_all_rate"],
                "gap_mean": v["gap_mean"],
                "flip_rate": v["flip_rate"],
                "dq_change_rate": v["dq_ref_change_rate"],
                "dq_ref_p95": v["dq_ref_p95"],
                "solver_failures": v["solver_failures"],
            })
    d = pd.DataFrame(rows)
    d.to_csv(run_dir / "table2_decision.csv", index=False, encoding="utf-8-sig")

    lines = [
        "# Table 2 — 决策可靠性（R200–R203）",
        "",
        "**主指标是 `dq_change_rate`（|Δq| 变化率，预注册偏离，见 CHANGELOG §27），`flip_rate` 降为辅助。**",
        "`feasible_all` 恒为 0 是已知的结构事实（钙在全部 18 个格子里不可达，见 §23），",
        "因此**可行性只报 `feasible_active`**。",
        "",
        "| basis | method | n | feasible(active) | gap_mean | flip_rate | dq_change_rate | dq p95 (g/day) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in d.iterrows():
        lines.append(
            f"| {r['bounds_basis']} | {r['method']} | {r['n_repeats']} | {r['feasible_active_rate']:.3f} | "
            f"{r['gap_mean']:.4f} | {r['flip_rate']:.3f} | {r['dq_change_rate']:.3f} | {r['dq_ref_p95']:.2f} |"
        )
    lines += [
        "",
        "> `gap` 用逐目标 payoff 区间归一化，**不可跨价格面板版本比较**（CHANGELOG §31.5）。",
    ]
    (run_dir / "table2.md").write_text("\n".join(lines), encoding="utf-8")
    return ["table2_decision.csv", "table2.md"]


# ---------------------------------------------------------------- R502
def build_figure1(run_dir: Path) -> list[str]:
    lab = pd.read_csv(M4 / "m4_direction_labels.csv", encoding="utf-8-sig")
    counts = lab.groupby(["scenario", "label"]).size().unstack(fill_value=0)
    for lb in LABELS:
        if lb not in counts:
            counts[lb] = 0
    counts = counts[list(LABELS)]
    counts.to_csv(run_dir / "figure1_stable_flip.csv", encoding="utf-8-sig", index_label="scenario")

    scenarios = list(counts.index)
    totals = counts.sum(axis=1).to_numpy()
    # 高度必须容纳「柱 + 情景名 + n= + 图例」四行；旧版 420 把图例裁在画布外
    w, h, pad, bar_w, plot_h = 760, 490, 60, 110, 300
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="sans-serif" font-size="12">',
        f'<rect width="{w}" height="{h}" fill="white"/>',
        f'<text x="{w/2}" y="26" text-anchor="middle" font-size="15">Figure 1. Direction-label distribution across 6 provinces x 6 food groups (90 group-cells)</text>',
    ]
    top = totals.max() if len(totals) else 1
    for i, scen in enumerate(scenarios):
        x = pad + 40 + i * (bar_w + 90)
        y = pad + plot_h
        for lb in LABELS:
            n = int(counts.loc[scen, lb])
            if not n:
                continue
            hh = plot_h * n / top
            y -= hh
            svg.append(
                f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{hh:.1f}" fill="{COLORS[lb]}" '
                f'stroke="white" stroke-width="0.5"/>'
            )
            if hh > 16:
                svg.append(
                    f'<text x="{x + bar_w/2}" y="{y + hh/2 + 4:.1f}" text-anchor="middle" '
                    f'fill="white">{n}</text>'
                )
        svg.append(f'<text x="{x + bar_w/2}" y="{pad + plot_h + 20}" text-anchor="middle">{scen}</text>')
        svg.append(f'<text x="{x + bar_w/2}" y="{pad + plot_h + 36}" text-anchor="middle" fill="#666">n={int(totals[i])}</text>')
    # 图例
    lx = pad + 40
    ly = pad + plot_h + 70
    for lb in LABELS:
        svg.append(f'<rect x="{lx}" y="{ly}" width="12" height="12" fill="{COLORS[lb]}"/>')
        svg.append(f'<text x="{lx + 18}" y="{ly + 10}">{LABEL_EN[lb]}</text>')
        lx += 150
    svg.append("</svg>")
    assert_viewbox(svg, w, h)
    (run_dir / "figure1.svg").write_text("\n".join(svg), encoding="utf-8")
    return ["figure1_stable_flip.csv", "figure1.svg"]


# ---------------------------------------------------------------- R503
def build_figure2(run_dir: Path) -> list[str]:
    lab = pd.read_csv(M4 / "m4_direction_labels.csv", encoding="utf-8-sig")
    d = lab[lab["scenario"] == "CDG"].copy()
    provs = sorted(d["province"].unique())
    groups = sorted(d["group_id"].unique())
    pivot = d.pivot(index="province", columns="group_id", values="label").reindex(index=provs, columns=groups)
    pivot.to_csv(run_dir / "figure2_regional_heatmap.csv", encoding="utf-8-sig", index_label="province")

    cw, ch, left, top = 92, 46, 110, 76
    w = left + cw * len(groups) + 40
    h = top + ch * len(provs) + 60
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="sans-serif" font-size="12">',
        f'<rect width="{w}" height="{h}" fill="white"/>',
        f'<text x="{w/2}" y="26" text-anchor="middle" font-size="15">Figure 2. Direction labels by region, CDG scenario (6 provinces x 6 food groups)</text>',
    ]
    for j, g in enumerate(groups):
        svg.append(
            f'<text x="{left + j*cw + cw/2}" y="{top - 12}" text-anchor="middle">{g}</text>'
        )
    for i, p in enumerate(provs):
        svg.append(f'<text x="{left - 10}" y="{top + i*ch + ch/2 + 4}" text-anchor="end">{PROVINCE_EN.get(p, p)}</text>')
        for j, g in enumerate(groups):
            v = pivot.loc[p, g]
            fill = COLORS.get(v, "#ffffff")
            svg.append(
                f'<rect x="{left + j*cw}" y="{top + i*ch}" width="{cw-2}" height="{ch-2}" '
                f'fill="{fill}" stroke="#dee2e6"/>'
            )
            svg.append(
                f'<text x="{left + j*cw + cw/2 - 1}" y="{top + i*ch + ch/2 + 4}" text-anchor="middle" '
                f'fill="white">{SHORT_EN.get(v, v)}</text>'
            )
    lx, ly = left, top + ch * len(provs) + 28
    for lb in LABELS:
        svg.append(f'<rect x="{lx}" y="{ly}" width="12" height="12" fill="{COLORS[lb]}"/>')
        svg.append(f'<text x="{lx + 18}" y="{ly + 10}">{LABEL_EN[lb]}</text>')
        lx += 130
    svg.append("</svg>")
    assert_viewbox(svg, w, h)
    (run_dir / "figure2.svg").write_text("\n".join(svg), encoding="utf-8")
    return ["figure2_regional_heatmap.csv", "figure2.svg"]


# ---------------------------------------------------------------- R504
def build_appendix(run_dir: Path, produced: list[str]) -> list[str]:
    rows = []
    for name in produced:
        p = run_dir / name
        rows.append({"file": name, "bytes": p.stat().st_size, "sha256": sha256(p)})
    import json

    (run_dir / "artifact_manifest.json").write_text(
        json.dumps({"artifacts": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 附录产物清单（R504）",
        "",
        "| 文件 | bytes | sha256（前 16） |",
        "|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| `{r['file']}` | {r['bytes']} | `{r['sha256'][:16]}` |")
    lines += [
        "",
        "## 源 run",
        "",
        f"- B1 价格面板：`{B1_PRICE.relative_to(ROOT)}`",
        f"- B1 消费面板：`{B1_CONS.relative_to(ROOT)}`",
        f"- B2 EAR：`{B2_EAR.relative_to(ROOT)}`；RNI：`{B2_RNI.relative_to(ROOT)}`",
        f"- M4 方向标签：`{M4.relative_to(ROOT)}`",
        "",
        "## 复现",
        "",
        "```powershell",
        "python scripts/build_paper_artifacts.py",
        "```",
    ]
    (run_dir / "appendix_index.md").write_text("\n".join(lines), encoding="utf-8")
    return produced + ["artifact_manifest.json", "appendix_index.md"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="R500_504_paper_artifacts")
    ap.add_argument(
        "--exact",
        action="store_true",
        help="目录名不加时间戳（默认 outputs/R500_504_paper_artifacts）。派生交付物需要稳定路径，"
        "否则每次重绘都会让 tracker 引用漂移。",
    )
    ap.add_argument("--force", action="store_true", help="配合 --exact：目录已存在时先删除再建")
    args = ap.parse_args()

    for p in (B1_PRICE, B1_CONS, B2_EAR, B2_RNI, M4):
        if not (p / "DONE").exists():
            raise SystemExit(f"源 run 缺少 DONE 标记：{p}")

    if args.exact:
        import shutil

        run_dir = OUTPUT_ROOT / args.run_id
        if run_dir.exists():
            if not args.force:
                raise SystemExit(f"{run_dir} 已存在；重绘请加 --force（仅限派生交付物）")
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
    else:
        run_dir = create_run_dir(OUTPUT_ROOT, args.run_id)
    produced: list[str] = []
    produced += build_table1(run_dir)
    produced += build_table2(run_dir)
    produced += build_figure1(run_dir)
    produced += build_figure2(run_dir)
    produced = build_appendix(run_dir, produced)

    # 校验：产物非空、表 2 的 8 行（2 口径 × 4 方法）、图 1/2 的行数与预期一致
    t2 = pd.read_csv(run_dir / "table2_decision.csv", encoding="utf-8-sig")
    f1 = pd.read_csv(run_dir / "figure1_stable_flip.csv", encoding="utf-8-sig")
    f2 = pd.read_csv(run_dir / "figure2_regional_heatmap.csv", encoding="utf-8-sig")
    assert len(t2) == 8, f"table2 期望 8 行，实际 {len(t2)}"
    assert len(f1) == 3, f"figure1 期望 3 个情景，实际 {len(f1)}"
    assert f2.shape == (6, 7), f"figure2 期望 6 省 × (1+6 组)，实际 {f2.shape}"

    finalize_run(
        run_dir,
        {
            "command": "build-paper-artifacts",
            "run_id": "R500-504",
            "evidence_status": "formal",
            "covers": ["R500", "R501", "R502", "R503", "R504"],
            "n_artifacts": len(produced),
            "artifacts": produced,
            "checks": {
                "table2_rows": int(len(t2)),
                "figure1_scenarios": int(len(f1)),
                "figure2_shape": list(map(int, f2.shape)),
            },
            "note": (
                "本 run 只读既有产物、不重跑求解，因此不会改变任何结论；"
                "图形为纯 SVG（无 matplotlib 依赖），数据另存 CSV 供重绘。"
            ),
        },
        {"command": "build-paper-artifacts", "sources": [str(p.relative_to(ROOT)) for p in (B1_PRICE, B1_CONS, B2_EAR, B2_RNI, M4)]},
    )
    print(f"[M5] {run_dir}")
    print(f"  产物 {len(produced)} 个: {', '.join(produced)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
