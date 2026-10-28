"""R505：可复现性校验（交接门禁）。

## 这个脚本能自动验什么、不能验什么

能自动验（本脚本）：

1. **合同哈希零漂移**——`model_manifest.json` 里登记的每个产物，重算 sha256 与登记值比对；
2. **产物完整性**——被 tracker 引用的 run 目录存在且带 `DONE` 标记；
3. **测试门禁**——`unittest discover -s tests` 全绿；
4. **降级风险**——`requirements.txt` 与当前环境包版本的差异（只报，不改）。

不能自动验（必须人工，脚本会写进 `not_verified`）：

- **干净环境的重跑**：需要 `git clone` + 新建 venv + `pip install -r requirements.txt`，
  在离线/沙箱环境里做不了，也不该由脚本偷偷联网完成。
  替代做法：本脚本给出 `RUNBOOK.md` 的逐条命令，人工在干净机上跑。

## 用法

    python scripts/verify_reproducibility.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.io_utils import create_run_dir, finalize_run  # noqa: E402

OUTPUT_ROOT = ROOT / "outputs"
MUST_OUTPUT_DIRS = [
    "B1_formal_withmice_20261023_124906",
    "R103_105_consumption_formal_20261026_174725",
    "R108_109_price_formal_20261026_175443",
    "R200_203_b2_formal_20261027_222841",
    "R200_203_b2_formal_20261027_224315",
    "R002_group_freeze_20261027_232440",
    "M3_all_smoke_20261026_181618",
    "R400_406_provinces_20261028_183104",
    "R407_looro_20261028_183054",
    "R408_delta_20261028_183131",
    "R409_bounds_20261028_183421",
    "R401_shanghai_availability_20261028_180508",
    "R500_504_paper_artifacts*",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def verify_manifest() -> dict:
    manifest = json.loads((ROOT / "data/processed/model_manifest.json").read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", {})
    drift, missing, ok = [], [], 0
    for name, meta in artifacts.items():
        rel = meta.get("path") if isinstance(meta, dict) else None
        want = meta.get("sha256") if isinstance(meta, dict) else None
        if not rel or not want:
            continue
        p = ROOT / rel
        if not p.exists():
            missing.append(rel)
            continue
        got = sha256(p)
        if got != want:
            drift.append({"path": rel, "expected": want[:16], "actual": got[:16]})
        else:
            ok += 1
    return {"n_checked": len(artifacts), "n_ok": ok, "drift": drift, "missing": missing}


def resolve_dir(name: str) -> Path:
    """支持两种写法：完整目录名，或 `前缀*`（取时间戳最新的一个）。

    后者用于会被重建的批次（例如图表产物换语言后会生成新目录），
    避免把某个时间戳写死进门禁，导致重建后门禁误报「目录缺失」。
    """
    if name.endswith("*"):
        hits = sorted(p for p in OUTPUT_ROOT.glob(name) if p.is_dir())
        return hits[-1] if hits else OUTPUT_ROOT / name
    return OUTPUT_ROOT / name


def verify_dirs() -> dict:
    missing_done, absent = [], []
    for name in MUST_OUTPUT_DIRS:
        p = resolve_dir(name)
        if not p.is_dir():
            absent.append(name)
        elif not (p / "DONE").exists():
            missing_done.append(p.name)
    return {"n_checked": len(MUST_OUTPUT_DIRS), "absent": absent, "missing_done": missing_done}


def run_tests() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return {"returncode": proc.returncode, "tail": tail}


def run_tracker_check() -> dict:
    proc = subprocess.run(
        [sys.executable, "scripts/check_tracker.py", "--verbose", "--ignore", "R505_reproducibility"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.startswith(("PASS", "FAIL", "结论"))]
    return {"returncode": proc.returncode, "summary": lines[-1] if lines else "", "n_pass": sum(1 for ln in lines if ln.startswith("PASS")), "n_fail": sum(1 for ln in lines if ln.startswith("FAIL"))}


def requirements_snapshot() -> dict:
    import importlib.metadata as md

    want = {}
    txt = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split(">=")[0].split("==")[0].strip()
        try:
            want[name] = md.version(name)
        except Exception:  # noqa: BLE001
            want[name] = "NOT INSTALLED"
    return want


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="R505_reproducibility")
    ap.add_argument(
        "--exact",
        action="store_true",
        help=(
            "目录名不加时间戳（默认 outputs/R505_reproducibility）。门禁产物需要**稳定路径**，"
            "否则 tracker 引用与每次重跑的时间戳会互相追尾。"
        ),
    )
    ap.add_argument("--force", action="store_true", help="配合 --exact：目录已存在时先删除再建")
    args = ap.parse_args()

    if args.exact:
        import shutil

        run_dir = OUTPUT_ROOT / args.run_id
        if run_dir.exists():
            if not args.force:
                raise SystemExit(f"{run_dir} 已存在；重跑请加 --force（仅限门禁产物）")
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
    else:
        run_dir = create_run_dir(OUTPUT_ROOT, args.run_id)

    man = verify_manifest()
    dirs = verify_dirs()
    tests = run_tests()
    tracker = run_tracker_check()
    reqs = requirements_snapshot()

    verified = []
    if man["drift"] == [] and man["missing"] == []:
        verified.append(f"合同哈希零漂移（{man['n_ok']}/{man['n_checked']}）")
    if not dirs["absent"] and not dirs["missing_done"]:
        verified.append(f"关键 run 目录完整（{dirs['n_checked']} 个，均带 DONE）")
    if tests["returncode"] == 0:
        verified.append("unittest 全绿")
    if tracker["returncode"] == 0:
        verified.append(f"tracker 校验全绿（{tracker['n_pass']} 项）")

    not_verified = [
        "干净环境重跑（git clone + 新建 venv + pip install -r requirements.txt）—— "
        "本环境无网络/不新建环境，未执行；命令见 RUNBOOK.md",
        "论文图表的人工视觉核对（R502/R503 的 SVG 需人眼确认可读性）",
    ]

    report = {
        "command": "verify-reproducibility",
        "run_id": "R505",
        "evidence_status": "formal",
        "manifest": man,
        "must_dirs": dirs,
        "tests": tests,
        "tracker_check": tracker,
        "packages": reqs,
        "verified": verified,
        "not_verified": not_verified,
        "verdict": "PASS（自动化部分）" if len(verified) == 4 else "FAIL",
        "note": (
            "本报告只覆盖可自动化验证的部分。R505 的预注册要求是「干净环境复跑」，"
            "那一步必须在仓库外执行，见 RUNBOOK.md；本报告不声称已完成它。"
        ),
    }
    (run_dir / "reproducibility_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    runbook = [
        "# RUNBOOK — 干净环境复跑（R505 的人工部分）",
        "",
        "以下命令在**仓库外的新目录**执行，用于验证「clone 即可复现」。",
        "",
        "```powershell",
        "git clone <repo-url> east-china-repro",
        "cd east-china-repro",
        "python -m venv .venv",
        ".\\.venv\\Scripts\\Activate.ps1",
        "python -m pip install -r requirements.txt",
        "",
        "# 1) 测试与文档门禁",
        "python -m unittest discover -s tests -v      # 期望 69 tests OK",
        "python scripts/check_tracker.py              # 期望 15 项全绿",
        "",
        "# 2) 合同 gate",
        "python scripts/check_contract_gates.py       # 期望 7/7 PASS",
        "",
        "# 3) 选定的 MUST run（按耗时排序，可从长到短取舍）",
        "python run_experiments.py audit --run-id R001_repro_audit",
        "python scripts/run_b2.py --profile formal --bounds-basis ear --run-id REPRO_b2_ear",
        "python scripts/run_m4.py --block provinces --run-id REPRO_m4_provinces",
        "",
        "# 4) 比对",
        "#    新批次不与旧批次逐元素比较（时间戳与求解器版本会引入微差），",
        "#    而是比较 metrics.json 里的关键量：",
        "#    - B2: per_method[*].dq_ref_change_rate / feasible_active_rate",
        "#    - M4: direction_agreement_mean / label_counts",
        "```",
        "",
        "## 判据",
        "",
        "| 项 | 容差 |",
        "|---|---|",
        "| `dq_ref_change_rate` | 与报告值同号且 \\|差\\| ≤ 1e-6 |",
        "| `feasible_active_rate` | 逐位相同（0/1 比例，无随机性） |",
        "| `direction_agreement_mean` | 同号且 \\|差\\| ≤ 1e-6 |",
        "| 图/表数值 | 与 `artifact_manifest.json` 的 CSV 逐单元格一致 |",
        "",
        "## 本报告已自动验证的部分",
        "",
    ] + [f"- ✅ {v}" for v in verified] + [
        "",
        "## 未验证",
        "",
    ] + [f"- ⬜ {v}" for v in not_verified]
    (run_dir / "RUNBOOK.md").write_text("\n".join(runbook), encoding="utf-8")

    finalize_run(run_dir, report, {"command": "verify-reproducibility", "must_dirs": MUST_OUTPUT_DIRS})
    print(f"[R505] {run_dir}")
    print(f"  verdict: {report['verdict']}")
    for v in verified:
        print(f"  OK   {v}")
    for v in not_verified:
        print(f"  TODO {v[:60]}")
    return 0 if report["verdict"].startswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
