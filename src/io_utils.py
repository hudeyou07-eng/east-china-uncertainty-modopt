from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def create_run_dir(output_root: Path, run_id: str) -> Path:
    path = output_root / f"{run_id}_{utc_stamp()}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def source_tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def environment_info() -> dict[str, Any]:
    packages: dict[str, str] = {}
    for name in ("numpy", "pandas", "scipy", "sklearn", "yaml", "openpyxl"):
        try:
            module = __import__(name)
            packages[name] = getattr(module, "__version__", "unknown")
        except Exception as exc:  # explicit in artifact; never silently ignored
            packages[name] = f"UNAVAILABLE: {exc}"
    try:
        git_hash = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        git_hash = "not-a-git-checkout"
    return {
        "timestamp": datetime.now().astimezone().isoformat(),
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "git_hash": git_hash,
        "packages": packages,
    }


def finalize_run(run_dir: Path, metrics: dict[str, Any], config: dict[str, Any]) -> None:
    write_json(run_dir / "metrics.json", metrics)
    write_json(run_dir / "config.json", config)
    write_json(run_dir / "environment.json", environment_info())
    (run_dir / "DONE").write_text("completed\n", encoding="utf-8")


def fail_run(run_dir: Path, exc: BaseException, config: dict[str, Any] | None = None) -> None:
    if config is not None:
        write_json(run_dir / "config.json", config)
    write_json(run_dir / "environment.json", environment_info())
    write_json(
        run_dir / "FAILED.json",
        {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now().isoformat(),
        },
    )
