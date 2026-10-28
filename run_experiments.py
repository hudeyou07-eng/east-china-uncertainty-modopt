from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.data_audit import (
    audit_price_panel,
    load_clean_price_panel,
    load_consumption_panel,
    make_group_audit_template,
)
from src.imputation import predict
from src.io_utils import create_run_dir, fail_run, finalize_run, sha256_file, source_tree_hash, write_json
from src.masking import apply_mask, make_mask
from src.metrics import calibration_metrics
from src.robust_modopt import make_toy_problem, solve_chance_modopt


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def resolve_path(config_path: Path, raw: str) -> Path:
    return (config_path.parent / raw).resolve()


def load_panel(config: dict, config_path: Path, panel: str) -> tuple[pd.DataFrame, Path]:
    """按 ``panel`` 选择被插补对象，返回 (长表面板, 源文件路径)。

    ``price`` 是含真实缺口的省×品类×年面板；``consumption`` 是
    7 省 × 10 组 × 9 年的**全观测**面板，因此后者只做人造遮蔽的可恢复性测试。
    """
    if panel == "price":
        source = resolve_path(config_path, config["paths"]["clean_price_workbook"])
        raw_catalog = resolve_path(config_path, config["paths"]["price_workbook"])
        return (
            load_clean_price_panel(
                source, float(config["audit"]["oil_density_kg_per_litre"]), raw_catalog
            ),
            source,
        )
    if panel == "consumption":
        source = resolve_path(config_path, config["paths"]["clean_consumption_table"])
        return load_consumption_panel(source), source
    raise ValueError(f"Unknown panel: {panel!r} (expected 'price' or 'consumption')")


def run_audit(config: dict, config_path: Path, run_dir: Path) -> dict:
    source = resolve_path(config_path, config["paths"]["clean_price_workbook"])
    raw_catalog = resolve_path(config_path, config["paths"]["price_workbook"])
    panel = load_clean_price_panel(
        source, float(config["audit"]["oil_density_kg_per_litre"]), raw_catalog
    )
    summary, support = audit_price_panel(
        panel, config["audit"]["min_price_regions"], config["audit"]["min_price_observations"]
    )
    panel.to_csv(run_dir / "price_panel_long.csv", index=False, encoding="utf-8-sig")
    support.to_csv(run_dir / "price_group_support.csv", index=False, encoding="utf-8-sig")
    make_group_audit_template(support).to_csv(
        run_dir / "group_audit_template.csv", index=False, encoding="utf-8-sig"
    )
    summary["source"] = str(source)
    summary["source_sha256"] = sha256_file(source)
    summary["source_tree_sha256"] = source_tree_hash(ROOT)
    return summary


def _parse_subset(raw: str | None, total: int) -> list[int]:
    """Parse "0,2,4" or "0-4" or "0-4,7" into a validated index list."""
    if raw is None:
        return list(range(total))
    items: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, end = chunk.split("-", 1)
            items.extend(range(int(start), int(end) + 1))
        else:
            items.append(int(chunk))
    if not items:
        raise ValueError(f"Empty subset specification: {raw!r}")
    if any(i < 0 or i >= total for i in items):
        raise ValueError(f"Subset {raw!r} is outside [0, {total})")
    return sorted(set(items))


def run_calibration(
    config: dict,
    config_path: Path,
    run_dir: Path,
    profile: str,
    fold_subset: list[int] | None = None,
    repeat_subset: list[int] | None = None,
    panel_kind: str = "price",
) -> dict:
    panel, source = load_panel(config, config_path, panel_kind)
    section = config["calibration"]
    allowed_natures = set(section["training_data_natures"])
    excluded = panel["observed"] & ~panel["data_nature"].isin(allowed_natures)
    panel.loc[excluded, "value"] = np.nan
    panel.loc[excluded, "observed"] = False
    panel["truth_eligible"] = panel["observed"]
    folds = int(section[f"{profile}_folds"])
    repeats = int(section[f"{profile}_repeats"])
    fold_list = _parse_subset(None, folds) if fold_subset is None else fold_subset
    repeat_list = _parse_subset(None, repeats) if repeat_subset is None else repeat_subset
    seed = int(config["project"]["seed"])
    rows = []
    prediction_rows = []
    mask_rows = []
    start_time = time.time()
    for fold in fold_list:
        for repeat in repeat_list:
            for mask_type in section["mask_types"]:
                mask_seed = seed + fold * 10000 + repeat * 100 + section["mask_types"].index(mask_type)
                rng = np.random.default_rng(mask_seed)
                mask = make_mask(
                    panel,
                    mask_type,
                    rng,
                    float(section["point_mask_fraction"]),
                    int(section["block_years"]),
                    fold=fold,
                    n_folds=folds,
                    fold_seed=seed + section["mask_types"].index(mask_type) * 1000,
                    min_series_observations=int(section["min_series_observations"]),
                )
                masked = apply_mask(panel, mask)
                target = masked.loc[mask, ["province", "group_raw", "year", "target_truth"]].copy()
                for _, target_row in target.iterrows():
                    mask_rows.append(
                        {
                            "fold": fold,
                            "repeat": repeat,
                            "mask_type": mask_type,
                            "seed": mask_seed,
                            "province": target_row["province"],
                            "group_raw": target_row["group_raw"],
                            "year": int(target_row["year"]),
                            "truth": float(target_row["target_truth"]),
                        }
                    )
                for method in section["methods"]:
                    method_start = time.time()
                    prediction = predict(
                        method,
                        masked,
                        target[["province", "group_raw", "year"]],
                        mask_seed,
                        int(section["posterior_draws"] if profile == "formal" else min(20, section["posterior_draws"])),
                    )
                    metric = calibration_metrics(target["target_truth"].to_numpy(float), prediction)
                    metric.update(
                        {
                            "fold": fold,
                            "repeat": repeat,
                            "mask_type": mask_type,
                            "method": method,
                            "seed": mask_seed,
                            "runtime_seconds": time.time() - method_start,
                        }
                    )
                    rows.append(metric)
                    for pos, (_, target_row) in enumerate(target.iterrows()):
                        prediction_rows.append(
                            {
                                "fold": fold,
                                "repeat": repeat,
                                "mask_type": mask_type,
                                "method": method,
                                "seed": mask_seed,
                                "province": target_row["province"],
                                "group_raw": target_row["group_raw"],
                                "year": int(target_row["year"]),
                                "truth": float(target_row["target_truth"]),
                                "prediction": float(prediction.mean[pos]),
                                "lower80": float(prediction.lower80[pos]),
                                "upper80": float(prediction.upper80[pos]),
                                "lower95": float(prediction.lower95[pos]),
                                "upper95": float(prediction.upper95[pos]),
                            }
                        )
    results = pd.DataFrame(rows)
    results.to_csv(run_dir / "calibration_results.csv", index=False)
    pd.DataFrame(mask_rows).to_csv(run_dir / "masks.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(prediction_rows).to_csv(
        run_dir / "cell_predictions.csv", index=False, encoding="utf-8-sig"
    )
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
    )
    # 注意：这里**故意不汇总** calibration_error。
    # 它是 |经验覆盖率 − 名义水平| 的均值，而每个 fold-repeat 块的样本很小
    # （consecutive_years 每块仅 8 格），小样本噪声会把 |cov − nominal| 系统性抬高，
    # 再跨块平均会得到一个虚高的数（实测 0.242，而池化后只有 0.066）。
    # 权威口径请用 scripts/coverage_curve.py 在池化样本上重算。
    summary.to_csv(run_dir / "calibration_summary.csv", index=False)

    # R106：coverage–width 曲线（长表，一行 = 一个 方法×遮蔽类型×名义水平）
    curve_rows = []
    for (mask_type, method), block in summary.groupby(["mask_type", "method"]):
        for level in (50, 80, 90, 95):
            curve_rows.append(
                {
                    "panel": panel_kind,
                    "mask_type": mask_type,
                    "method": method,
                    "nominal": level / 100.0,
                    "empirical_coverage": float(block[f"coverage{level}"].iloc[0]),
                    "mean_width": float(block[f"width{level}"].iloc[0]),
                    "gap": float(block[f"coverage{level}"].iloc[0]) - level / 100.0,
                }
            )
    curve = pd.DataFrame(curve_rows)
    curve.to_csv(run_dir / "coverage_curve.csv", index=False, encoding="utf-8-sig")
    return {
        "profile": profile,
        "folds": folds,
        "repeats": repeats,
        "evaluated_folds": fold_list,
        "evaluated_repeats": repeat_list,
        "result_rows": int(len(results)),
        "wall_seconds": time.time() - start_time,
        "source": str(source),
        "source_sha256": sha256_file(source),
        "source_tree_sha256": source_tree_hash(ROOT),
        "panel": panel_kind,
        "training_data_natures": sorted(allowed_natures),
        "training_observations": int(panel["observed"].sum()),
        "summary": summary.to_dict("records"),
    }


def run_optimization_smoke(config: dict, run_dir: Path) -> dict:
    seed = int(config["project"]["seed"])
    scenarios = int(config["optimization"]["train_scenarios_smoke"])
    problem = make_toy_problem(seed, scenarios)
    result = solve_chance_modopt(
        **problem,
        time_limit=float(config["optimization"]["mip_time_limit_seconds"]),
        mip_rel_gap=float(config["optimization"]["mip_relative_gap"]),
    )
    if not result.success:
        raise RuntimeError(f"Toy chance-MODOpt failed: {result.message}")
    allowed = int(np.floor(float(problem["epsilon"]) * scenarios + 1e-12))
    if int(result.z.sum()) > allowed:
        raise AssertionError("Chance-constraint violation budget exceeded")
    payload = {
        "synthetic_fixture_only": True,
        "scenarios": scenarios,
        "q": result.q.tolist(),
        "z_sum": int(result.z.sum()),
        "z_allowed": allowed,
        "objective": result.objective,
        "mip_gap": result.mip_gap,
        "message": result.message,
    }
    write_json(run_dir / "toy_solution.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproducible experiments for uncertainty-propagating MODOpt")
    parser.add_argument("command", choices=["audit", "calibration", "optimization-smoke", "all-smoke"])
    parser.add_argument("--config", default=str(ROOT / "configs" / "default.yaml"))
    parser.add_argument("--profile", choices=["smoke", "formal"], default="smoke")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--panel",
        choices=["price", "consumption"],
        default="price",
        help="被插补对象：price=零售价面板（含真实缺口）；consumption=消费面板（全观测，只测可恢复性）",
    )
    parser.add_argument(
        "--folds",
        default=None,
        help='Optional fold subset for sharded runs, e.g. "0,2" or "0-1". Default: all folds.',
    )
    parser.add_argument(
        "--repeats",
        default=None,
        help='Optional repeat subset for sharded runs, e.g. "0-9". Default: all repeats.',
    )
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    output_root = resolve_path(config_path, config["paths"]["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    default_id = args.command.replace("-", "_")
    if args.panel != "price":
        default_id = f"{default_id}_{args.panel}"
    run_id = args.run_id or default_id
    run_dir = create_run_dir(output_root, run_id)
    section = config["calibration"]
    fold_subset = (
        _parse_subset(args.folds, int(section[f"{args.profile}_folds"]))
        if args.folds
        else None
    )
    repeat_subset = (
        _parse_subset(args.repeats, int(section[f"{args.profile}_repeats"]))
        if args.repeats
        else None
    )
    try:
        metrics: dict[str, object] = {"command": args.command}
        if args.command in {"audit", "all-smoke"}:
            metrics["audit"] = run_audit(config, config_path, run_dir)
        if args.command in {"calibration", "all-smoke"}:
            metrics["calibration"] = run_calibration(
                config,
                config_path,
                run_dir,
                args.profile,
                fold_subset,
                repeat_subset,
                panel_kind=args.panel,
            )
        if args.command in {"optimization-smoke", "all-smoke"}:
            metrics["optimization_smoke"] = run_optimization_smoke(config, run_dir)
        finalize_run(run_dir, metrics, {"args": vars(args), "config": config})
        print(json.dumps({"status": "DONE", "run_dir": str(run_dir), "metrics": metrics}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        fail_run(run_dir, exc, {"args": vars(args), "config": config})
        print(json.dumps({"status": "FAILED", "run_dir": str(run_dir), "error": str(exc)}, ensure_ascii=False, indent=2))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
