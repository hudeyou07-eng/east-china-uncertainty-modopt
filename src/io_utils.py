from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


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


def json_safe(obj: Any) -> Any:
    """把 NaN / ±Inf 递归换成 ``None``。

    **只在写 JSON 元数据时用，不要用于校验。** 输入侧的 NaN 应当显式报错
    （如 ``solve_chance_modopt`` 对非有限系数的 ``ValueError``）；
    而输出侧遇到 NaN 通常只意味着「这个指标没算出来」，为此让整个 run 崩掉
    得不偿失——结果 CSV 仍保留原始 NaN，元数据里记为 null。
    """
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, np.floating):
        value = float(obj)
        return value if math.isfinite(value) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


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
