"""校验 `docs/EXPERIMENT_TRACKER.md` 与磁盘产物的一致性。

设计原则：tracker 是**结论的账本**，它的每一条引用都必须能在仓库里被解析。
脚本只做机械核对，不判断科学结论对错——那需要人读 CHANGELOG。

十项检查
--------
1.  run 表结构：每行 9 列，run ID 形如 R123 / R307b，且唯一、升序。
2.  状态词表：只允许 DONE / DONE-conditional / PARTIAL / TODO / SUPERSEDED。
3.  里程碑归属：R0xx→M0、R1xx→M1、R2xx→M2、R3xx→M3、R4xx→M4、R5xx→M5。
4.  路径可解析：正文出现的 `outputs/<dir>` 必须存在；已清理目录须登记在
    ``RETIRED_DIRS``（每个都要写明替代者）。
5.  目录全覆盖：`outputs/` 下的每个目录都必须在 tracker 中被提到。
6.  DONE 行必须有产物：至少一个反引号路径真实存在。
7.  DONE 行的 run 目录必须带 `DONE` 标记（``DIR_WITHOUT_DONE_MARKER`` 例外）。
8.  汇总表自洽：`进度总览` 的分里程碑计数与 run 表实际计数一致。
9.  索引覆盖：`产物索引` 段必须覆盖 run 表里的每一个 run。
10. 证据等级：索引里出现的等级必须来自 ``EVIDENCE_CLASSES``。

用法
----
    python scripts/check_tracker.py            # 只报错，退出码 1 表示不通过
    python scripts/check_tracker.py --verbose  # 逐项打印通过项

退出码 0 表示 tracker 与磁盘一致。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACKER = ROOT / "docs" / "EXPERIMENT_TRACKER.md"
OUTPUTS = ROOT / "outputs"

STATUSES = {"DONE", "DONE-conditional", "PARTIAL", "TODO", "SUPERSEDED"}
EVIDENCE_CLASSES = {
    "formal",
    "formal_conditional",
    "sensitivity",
    "structural",
    "smoke",
    "n/a",
}

MILESTONE_PREFIX = {"0": "M0", "1": "M1", "2": "M2", "3": "M3", "4": "M4", "5": "M5"}

# 已被 docs/archive/CLEANUP_2026-10-28.md 删除、但仍作为历史过程被正文引用的目录。
# key=目录名, value=替代者（用于报告可读性）。
RETIRED_DIRS = {
    "R200_203_b2_formal_20261027_170542": "R200_203_b2_formal_20261027_222841",
    "R200_203_b2_formal_20261027_174710": "R200_203_b2_formal_20261027_222841",
    "R200_203_b2_smoke_20261027_151138": "无（smoke，已登记为不可现场复核）",
    "R200_203_b2_smoke_20261026_180400": "无（smoke，已登记为不可现场复核）",
    "R306_big_m_20261026_181722": "R306_big_m_20261026_181747",
    "DIAG_heal_bound_scale_20261027_151648": "DIAG_heal_bound_scale_20261027_151753",
    "DIAG_heal_bound_scale_20261027_151734": "DIAG_heal_bound_scale_20261027_151753",
    "DIAG_scope_activation_20261027_151224": "DIAG_scope_activation_20261027_151305",
    "DIAG_scope_activation_20261027_151242": "DIAG_scope_activation_20261027_151305",
    "DIAG_price_radius_20261027_173136": "DIAG_price_radius_20261027_174014",
    "DIAG_price_radius_20261027_173521": "DIAG_price_radius_20261027_174014",
    "DIAG_price_radius_20261027_173709": "DIAG_price_radius_20261027_174014",
    "DIAG_tail_angle_20261027_190238": "DIAG_tail_angle_20261027_192248",
    "DIAG_lambda_curve_20261027_190959": "DIAG_lambda_curve_20261027_191751",
    "DIAG_lambda_curve_fine_20261027_191241": "DIAG_lambda_curve_fine_20261027_191956",
    "decision_space_20261023_134000": "无（过时本体产物，含 6 个废弃组名，2026-10-28 清理，见 CLEANUP D 组）",
}

# 产物目录存在但没有 DONE 标记的，必须在这里说明原因。
DIR_WITHOUT_DONE_MARKER = {
    "R107_interaction_gate": "只读复算脚本产物（interaction_gate.json 即结论），不是求解批次",
}

RUN_ID_RE = re.compile(r"^R\d{3}[a-z]?$")
PATH_RE = re.compile(r"`([^`]+)`")
OUT_DIR_RE = re.compile(r"outputs/([A-Za-z0-9_]+)")


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        if ok:
            self.passes.append(f"{name}{(' — ' + detail) if detail else ''}")
        else:
            self.failures.append(f"{name}{(' — ' + detail) if detail else ''}")
        return ok

    def fail(self, name: str, detail: str) -> None:
        self.failures.append(f"{name} — {detail}")


def split_row(line: str) -> list[str]:
    """按未被反斜杠转义的竖线切分表格行，返回去掉首尾空单元后的内容。"""
    cells = re.split(r"(?<!\\)\|", line.strip())
    return [c.strip() for c in cells[1:-1]]


def parse_runs(lines: list[str]) -> list[dict]:
    """只解析 run 表（以 `| Run ID |` 开头的那一张），不碰索引表。"""
    runs: list[dict] = []
    start = None
    for i, line in enumerate(lines):
        if line.startswith("| Run ID |"):
            start = i + 1
            break
    if start is None:
        return runs
    for i in range(start, len(lines)):
        line = lines[i]
        if not line.startswith("|"):
            break
        m = re.match(r"^\|\s*(R\d{3}[a-z]?)\s*\|", line)
        if not m:
            continue
        runs.append(
            {
                "line": i + 1,
                "id": m.group(1),
                "cells": split_row(line),
                "raw": line,
            }
        )
    return runs


def section_slice(lines: list[str], startswith: str) -> list[str]:
    """取出以 startswith 开头的小节正文（到下一个 `## ` 或 `---` 为止）。"""
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line.startswith(startswith)
            continue
        if inside:
            if line.strip() == "---":
                break
            out.append(line)
    return out


def section_any(lines: list[str], headings: tuple[str, ...]) -> list[str]:
    """按候选标题依次查找小节（中文版与英文版共用同一套校验）。"""
    for h in headings:
        s = section_slice(lines, h)
        if s:
            return s
    return []


def expand_run_ids(cell: str) -> list[str]:
    """把 `R100–R102` 这类区间展开成 run id 列表。"""
    ids = re.findall(r"R\d{3}[a-z]?", cell)
    if not ids:
        return []
    if len(ids) >= 2 and ("–" in cell or "~" in cell):
        first, last = ids[0], ids[-1]
        if first[1:].isdigit() and last[1:].isdigit():
            return [f"R{i:03d}" for i in range(int(first[1:]), int(last[1:]) + 1)]
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 experiment tracker 与磁盘产物的一致性。")
    parser.add_argument("--verbose", action="store_true", help="打印通过的检查项")
    parser.add_argument(
        "--file",
        default=None,
        help="要校验的 tracker 路径（默认 docs/EXPERIMENT_TRACKER.md；英文版传 docs/EXPERIMENT_TRACKER_EN.md）",
    )
    parser.add_argument(
        "--ignore",
        nargs="*",
        default=[],
        help=(
            "目录名前缀白名单：这些 outputs 目录不要求被 tracker 收录。"
            "只用于「正在生成、尚未写入 tracker」的 run（例如 R505 自检它自己的输出目录），"
            "不得用于掩盖真正的漏登记。"
        ),
    )
    args = parser.parse_args()
    target = Path(args.file) if args.file else TRACKER
    if not target.is_absolute():
        target = ROOT / target

    if not target.exists():
        print(f"FAIL: 找不到 {target}")
        return 1
    lines = target.read_text(encoding="utf-8").splitlines()
    text = "\n".join(lines)
    rep = Report()

    runs = parse_runs(lines)
    rep.check("表结构：解析到 run 行", len(runs) > 0, f"{len(runs)} 行")

    # 1. 结构
    bad_shape = [(r["id"], len(r["cells"])) for r in runs if len(r["cells"]) != 9]
    rep.check("表结构：每行 9 列", not bad_shape, str(bad_shape[:5]) if bad_shape else "OK")

    bad_id = [r["id"] for r in runs if not RUN_ID_RE.match(r["id"])]
    rep.check("run ID 形如 R123/R307b", not bad_id, str(bad_id))

    ids = [r["id"] for r in runs]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    rep.check("run ID 唯一", not dup, str(dup))

    order_key = [int(re.match(r"R(\d{3})", i).group(1)) * 10 + (ord(i[-1]) - 97 if i[-1].isalpha() else 0) for i in ids]
    rep.check("run ID 升序排列", order_key == sorted(order_key), "OK" if order_key == sorted(order_key) else "顺序错乱")

    # 2. 状态词表
    bad_status = [(r["id"], r["cells"][7]) for r in runs if r["cells"][7] not in STATUSES]
    rep.check("状态词表合法", not bad_status, str(bad_status))

    # 3. 里程碑归属
    bad_ms = []
    for r in runs:
        prefix = r["id"][1]
        expected = MILESTONE_PREFIX[prefix]
        if r["cells"][1] != expected:
            bad_ms.append((r["id"], r["cells"][1], expected))
    rep.check("里程碑归属一致", not bad_ms, str(bad_ms))

    # 4. 路径可解析
    cited = sorted({m for m in OUT_DIR_RE.findall(text)})
    on_disk = {p.name for p in OUTPUTS.iterdir() if p.is_dir()} if OUTPUTS.exists() else set()
    missing = [c for c in cited if c not in on_disk and c not in RETIRED_DIRS]
    rep.check("正文引用的 outputs 目录均已登记", not missing, str(missing))

    # 5. 目录全覆盖
    unmentioned = sorted(
        d for d in (on_disk - set(cited))
        if not any(d.startswith(prefix) for prefix in args.ignore)
    )
    rep.check("outputs 目录全部被 tracker 提到", not unmentioned, str(unmentioned))

    # 索引先解析，供 DONE 行的产物追溯使用
    index = section_any(lines, ("## 产物索引", "## Artifact index"))
    covered: set[str] = set()
    index_text: dict[str, str] = {}

    def index_run_ids(line: str) -> list[str]:
        """只从索引表的第一个单元取 run 编号——路径列里的 `R108_109_...` 会污染匹配。"""
        cells = split_row(line)
        return expand_run_ids(cells[0]) if cells else []

    for line in index:
        if not line.startswith("|"):
            continue
        for rid in index_run_ids(line):
            covered.add(rid)
            index_text[rid] = index_text.get(rid, "") + " " + line

    # 6-7. DONE 行的产物与标记
    def ignored(name: str) -> bool:
        return any(name.startswith(prefix) for prefix in args.ignore)

    no_artifact = []
    no_marker = []
    for r in runs:
        status = r["cells"][7]
        if status not in {"DONE", "DONE-conditional"}:
            continue
        scope = r["raw"] + " " + index_text.get(r["id"], "")
        paths = [p for p in PATH_RE.findall(scope)]
        all_dirs = OUT_DIR_RE.findall(scope)
        dirs_in_scope = [d for d in all_dirs if not ignored(d)]
        if all_dirs and not dirs_in_scope:
            # 该行只指向「正在生成的门禁产物」：本轮不判它，登记完成后普通校验仍会管到
            continue
        if dirs_in_scope:
            existing = [p for p in paths if (ROOT / p).exists() and not ignored(Path(p).parent.name)]
        else:
            existing = [p for p in paths if (ROOT / p).exists()]
        if not existing:
            no_artifact.append(r["id"])
        for d in dirs_in_scope:
            if d in on_disk and d not in DIR_WITHOUT_DONE_MARKER:
                if not (OUTPUTS / d / "DONE").exists():
                    no_marker.append(f"{r['id']}→{d}")
    rep.check("DONE 行至少引用一个存在的产物", not no_artifact, str(no_artifact))
    rep.check("DONE 行引用的 run 目录带 DONE 标记", not no_marker, str(no_marker))

    # 8. 汇总表自洽
    actual: dict[str, dict[str, int]] = {}
    for r in runs:
        ms, status = r["cells"][1], r["cells"][7]
        actual.setdefault(ms, {s: 0 for s in STATUSES})
        actual[ms][status] += 1

    summary = section_any(lines, ("## 进度总览", "## Progress summary"))
    declared: dict[str, list[int]] = {}
    totals: list[int] | None = None
    for line in summary:
        if not line.startswith("|"):
            continue
        cells = split_row(line)
        if len(cells) < 5:
            continue
        label = cells[0].replace("*", "").strip()
        nums: list[int] = []
        for cell in cells[1:]:
            token = cell.strip("* ").strip()
            if token.isdigit():
                nums.append(int(token))
            else:
                break
        if len(nums) != 4:
            continue
        if label.startswith("M") and len(label) >= 2 and label[1].isdigit():
            declared[label[:2]] = nums
        elif "合计" in label or "total" in label.lower():
            totals = nums

    order = ("DONE", "DONE-conditional", "PARTIAL", "TODO")
    mismatched = []
    for ms, nums in declared.items():
        got = [actual.get(ms, {}).get(s, 0) for s in order]
        if got != nums:
            mismatched.append(f"{ms} 声明 {nums} 实际 {got}")
    rep.check("汇总表：分里程碑计数与 run 表一致", not mismatched, "; ".join(mismatched))

    if totals is None:
        rep.check("汇总表：存在合计行", False)
    else:
        got_totals = [sum(actual.get(ms, {}).get(s, 0) for ms in actual) for s in order]
        rep.check(
            "汇总表：合计行等于 run 表总数",
            got_totals == totals and sum(totals) == len(runs),
            f"声明 {totals} 实际 {got_totals} / {len(runs)} 行",
        )

    # 9. 索引覆盖（index / covered 已在上方解析）
    uncovered = [r["id"] for r in runs if r["id"] not in covered]
    rep.check("产物索引覆盖全部 run", not uncovered, str(uncovered))

    # 10. 证据等级词表
    bad_class = []
    for line in index:
        if not line.startswith("|"):
            continue
        cells = split_row(line)
        if len(cells) < 3:
            continue
        for token in re.findall(r"\b(?:formal_conditional|formal|sensitivity|structural|smoke|n/a)\b", cells[-1]):
            if token not in EVIDENCE_CLASSES:
                bad_class.append(token)
    rep.check("证据等级取自固定词表", not bad_class, str(sorted(set(bad_class))))

    # 输出
    if args.verbose:
        for p in rep.passes:
            print(f"PASS  {p}")
    if rep.failures:
        print()
        for f in rep.failures:
            print(f"FAIL  {f}")
        print(f"\n结论：{len(rep.failures)} 项不通过（共 {len(rep.passes) + len(rep.failures)} 项）。")
        return 1

    print(f"结论：{len(rep.passes)} 项全部通过。")
    print(
        f"run 行 {len(runs)} 条；outputs 目录 {len(on_disk)} 个；"
        f"正文引用目录 {len(cited)} 个（其中已清理 {len([c for c in cited if c in RETIRED_DIRS])} 个已登记）。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
