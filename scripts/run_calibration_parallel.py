"""Run the B1 calibration in parallel shards and merge the results.

`IterativeImputer.transform` re-runs the whole iterative loop on every call, so
one MICE evaluation at 100 posterior draws costs about 75 s and the full formal
block (5 folds x 20 repeats x 3 masks) costs roughly six hours sequentially.

Sharding is safe because every mask seed is a pure function of
(fold, repeat, mask_type) and every method draws from that same mask. Running
disjoint (fold, repeat) subsets therefore reproduces the sequential result
exactly — verified by comparing a shard against the corresponding rows of a
full sequential run.

Usage:
    python scripts/run_calibration_parallel.py --workers 20 --blocks-per-fold 4
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.io_utils import environment_info, sha256_file, utc_stamp  # noqa: E402

OUTPUT_FILES = [
    "calibration_results.csv",
    "masks.csv",
    "cell_predictions.csv",
]


def build_shards(folds: int, repeats: int, blocks_per_fold: int) -> list[dict]:
    if repeats % blocks_per_fold:
        raise ValueError("repeats must be divisible by blocks_per_fold")
    span = repeats // blocks_per_fold
    shards = []
    for fold in range(folds):
        for block in range(blocks_per_fold):
            lo = block * span
            hi = lo + span - 1
            shards.append({"fold": fold, "repeats": f"{lo}-{hi}"})
    return shards


def run_shard(shard: dict, config_path: Path, profile: str, run_id: str, panel: str = "price") -> Path:
    shard_id = f"{run_id}_f{shard['fold']}_r{shard['repeats'].replace('-', 'to')}"
    cmd = [
        sys.executable,
        str(ROOT / "run_experiments.py"),
        "calibration",
        "--config", str(config_path),
        "--profile", profile,
        "--run-id", shard_id,
        "--folds", str(shard["fold"]),
        "--repeats", shard["repeats"],
        "--panel", panel,
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Shard {shard_id} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    output_root = (config_path.parent / yaml.safe_load(config_path.read_text(encoding="utf-8"))["paths"]["output_root"]).resolve()
    matches = sorted(output_root.glob(f"{shard_id}_*"))
    if not matches:
        raise RuntimeError(f"Shard {shard_id} produced no run directory")
    return matches[-1]


def merge(shard_dirs: list[Path], run_dir: Path, config: dict, profile: str) -> dict:
    frames = {name: pd.concat([pd.read_csv(d / name) for d in shard_dirs], ignore_index=True) for name in OUTPUT_FILES}
    results = frames["calibration_results.csv"].sort_values(["mask_type", "method", "fold", "repeat"]).reset_index(drop=True)
    results.to_csv(run_dir / "calibration_results.csv", index=False)
    frames["masks.csv"].to_csv(run_dir / "masks.csv", index=False, encoding="utf-8-sig")
    frames["cell_predictions.csv"].to_csv(run_dir / "cell_predictions.csv", index=False, encoding="utf-8-sig")

    summary = (
        results.groupby(["mask_type", "method"], as_index=False)
        .agg(
            n_eval=("n", "sum"),
            scaled_mae=("scaled_mae", "mean"),
            log_rmse=("log_rmse", "mean"),
            coverage50=("coverage50", "mean"),
            coverage80=("coverage80", "mean"),
            coverage90=("coverage90", "mean"),
            coverage95=("coverage95", "mean"),
            width50=("width50", "mean"),
            width80=("width80", "mean"),
            width90=("width90", "mean"),
            width95=("width95", "mean"),
            asymmetry95=("asymmetry95", "mean"),
            runtime_seconds=("runtime_seconds", "sum"),
        )
        .sort_values(["mask_type", "method"])
    )
    summary.to_csv(run_dir / "calibration_summary.csv", index=False)

    duplicate = results.duplicated(["fold", "repeat", "mask_type", "method"]).sum()
    if duplicate:
        raise AssertionError(f"Merged results contain {duplicate} duplicate rows")

    return {
        "profile": profile,
        "shards": len(shard_dirs),
        "result_rows": int(len(results)),
        "duplicate_rows": int(duplicate),
        "methods": sorted(results["method"].unique().tolist()),
        "mask_types": sorted(results["mask_type"].unique().tolist()),
        "folds_covered": sorted(results["fold"].unique().tolist()),
        "repeats_covered": sorted(results["repeat"].unique().tolist()),
        "source_tree_sha256": None,
        "summary": summary.to_dict("records"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel sharded B1 calibration")
    parser.add_argument("--config", default=str(ROOT / "configs" / "default.yaml"))
    parser.add_argument("--profile", choices=["smoke", "formal"], default="formal")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--blocks-per-fold", type=int, default=4)
    parser.add_argument("--run-id", default="B1_formal_parallel")
    parser.add_argument("--panel", choices=["price", "consumption"], default="price")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    section = config["calibration"]
    folds = int(section[f"{args.profile}_folds"])
    repeats = int(section[f"{args.profile}_repeats"])
    shards = build_shards(folds, repeats, args.blocks_per_fold)

    output_root = (config_path.parent / config["paths"]["output_root"]).resolve()
    run_dir = output_root / f"{args.run_id}_{utc_stamp()}"
    run_dir.mkdir(parents=True, exist_ok=False)

    start = time.time()
    print(json.dumps({"shards": len(shards), "workers": args.workers, "run_dir": str(run_dir)}, ensure_ascii=False))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        shard_dirs = list(
            pool.map(
                lambda s: run_shard(s, config_path, args.profile, args.run_id, args.panel), shards
            )
        )

    metrics = {"command": "calibration-parallel", "calibration": merge(shard_dirs, run_dir, config, args.profile)}
    metrics["calibration"]["panel"] = args.panel
    metrics["calibration"]["wall_seconds"] = time.time() - start
    metrics["calibration"]["shard_dirs"] = [str(d) for d in shard_dirs]
    metrics["calibration"]["config_sha256"] = sha256_file(config_path)

    (run_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (run_dir / "config.json").write_text(json.dumps({"args": vars(args), "config": config}, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "environment.json").write_text(json.dumps(environment_info(), ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "DONE").write_text("completed\n", encoding="utf-8")
    print(json.dumps({"status": "DONE", "run_dir": str(run_dir), "wall_seconds": metrics["calibration"]["wall_seconds"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
