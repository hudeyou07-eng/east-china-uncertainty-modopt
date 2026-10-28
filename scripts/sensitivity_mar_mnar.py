"""R108（MAR 敏感性诊断）+ R109（MNAR δ 网格）。

## 为什么需要这一对

B1 的插补与区间都建立在「缺失与数值无关」的前提上（MCAR/MAR）。
真实数据很少满足。若缺失是系统性的（高值更容易缺），插补会**系统性偏低**，
而 95% 区间照样会覆盖——因为区间宽度也是从同一批数据估的。
换句话说：**标定好不代表无偏**。本脚本把这两件事分开测。

## R108：MAR 诊断（误差是否随真值水平变化）

按真值五分位分组，报告每组的 signed bias 与 scaled MAE。

- 若 MAR 成立，各组 bias 应接近 0，无单调趋势；
- 若高值组的 bias 显著为负（低估），说明高值更难恢复，
  真实数据若「高值更易缺」，插补就会偏低——这是 R109 要量化的方向。

同时报告 `bias_slope`：bias 对真值的回归斜率（标准化）。
|slope| 越大，误差越依赖水平，MAR 假设越可疑。

## R109：MNAR δ 网格

δ-调整是 MNAR 敏感性的标准做法：假设被遮蔽格的**真实值**系统性偏离
MAR 预测 δ 个残差标准差。

    truth_shifted = truth + δ · σ_g

δ ∈ {-0.5, 0, +0.5}（预注册网格，见 EXPERIMENT_PLAN.md B4「delta=-0.5,0,+0.5 残差 SD」）。

σ_g 取组内残差 SD：``value - group_mean(value)`` 在**未被遮蔽**的观测上估计。
这是「同组不同省/年」的自然离散度，比全局 SD 更贴近插补的实际误差尺度。

注意：δ≠0 时覆盖率下降是**预期**的，不是方法失败。真正要看的是
**不同方法在 δ 下的相对排序是否稳定**——若 D3 主方法在 δ=±0.5 下仍保持
最低标定误差，说明结论不依赖 MAR 假设。

用法：
    python scripts/sensitivity_mar_mnar.py --panel price --profile smoke
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from run_experiments import load_config, load_panel, resolve_path  # noqa: E402
from src.imputation import predict  # noqa: E402
from src.io_utils import create_run_dir, finalize_run  # noqa: E402
from src.masking import apply_mask, make_mask  # noqa: E402
from src.metrics import calibration_metrics  # noqa: E402

DELTA_GRID = (-0.5, 0.0, 0.5)


def _finite(obj):
    """把 NaN/Inf 递归换成 None，使 metrics.json 可被严格 JSON 解析。

    ``write_json`` 用 ``allow_nan=False``，而样本不足时 bias_slope 会是 NaN。
    直接写会抛错；静默改成 0 又会伪造结果。写成 null 是唯一诚实的选项。
    """
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj
QUINTILES = 5


def group_residual_sd(panel: pd.DataFrame) -> pd.Series:
    """组内残差 SD：``value - group_mean(value)``，只用未遮蔽的观测估计。"""
    observed = panel.dropna(subset=["value"])
    means = observed.groupby("group_raw")["value"].transform("mean")
    resid = observed["value"] - means
    return resid.groupby(observed["group_raw"]).std(ddof=1).fillna(0.0)


def mar_diagnostic(truth: np.ndarray, mean: np.ndarray, weights: np.ndarray) -> dict:
    """按真值五分位看 signed bias，并给出 bias 对真值的标准化斜率。"""
    if len(truth) < QUINTILES * 2:
        return {"n": int(len(truth)), "note": "样本过少，跳过五分位"}
    order = np.argsort(truth)
    chunks = np.array_split(order, QUINTILES)
    bias = mean - truth
    rows = []
    for i, idx in enumerate(chunks):
        if len(idx) == 0:
            continue
        rows.append(
            {
                "quintile": i + 1,
                "n": int(len(idx)),
                "truth_mean": float(truth[idx].mean()),
                "bias": float(bias[idx].mean()),
                "scaled_bias": float(bias[idx].mean() / max(float(np.mean(np.abs(truth[idx]))), 1e-8)),
                "scaled_mae": float(np.mean(np.abs(bias[idx])) / max(float(np.mean(np.abs(truth[idx]))), 1e-8)),
            }
        )
    truth_sd = float(truth.std(ddof=1))
    bias_sd = float(bias.std(ddof=1))
    if truth_sd > 1e-12 and bias_sd > 1e-12:
        slope = float(np.polyfit(truth, bias, 1)[0] * truth_sd / bias_sd)
    else:
        slope = 0.0
    return {
        "n": int(len(truth)),
        "bias_overall": float(bias.mean()),
        "bias_slope": slope,
        "monotone_bias": bool(
            len(rows) >= 3 and all(rows[i]["bias"] <= rows[i + 1]["bias"] for i in range(len(rows) - 1))
        ),
        "by_quintile": rows,
        "weights_note": "weights 仅用于核对样本来源一致性",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="R108 MAR diagnostic + R109 MNAR delta grid")
    parser.add_argument("--config", default=str(ROOT / "configs" / "default.yaml"))
    parser.add_argument("--panel", choices=["price", "consumption"], default="price")
    parser.add_argument("--profile", choices=["smoke", "formal"], default="smoke")
    parser.add_argument("--methods", nargs="*", default=None)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    section = config["calibration"]
    methods = args.methods or section["methods"]
    folds = int(section[f"{args.profile}_folds"])
    repeats = int(section[f"{args.profile}_repeats"])
    draws = int(section["posterior_draws"]) if args.profile == "formal" else 20
    seed = int(config["project"]["seed"])

    panel, source = load_panel(config, config_path, args.panel)
    allowed = set(section["training_data_natures"])
    panel = panel[panel["data_nature"].isin(allowed) | ~panel["observed"]].copy()
    panel["truth_eligible"] = panel["observed"]
    sigma = group_residual_sd(panel)
    if not (sigma > 0).any():
        raise SystemExit("组内残差 SD 全为 0，无法做 δ 调整")

    output_root = resolve_path(config_path, config["paths"]["output_root"])
    run_id = args.run_id or f"R108_109_{args.panel}_{args.profile}"
    run_dir = create_run_dir(output_root, run_id)

    delta_rows = []
    # MAR 诊断必须池化：province_group 单次重复只遮蔽 1 条序列（9 格），
    # 逐重复算五分位会因样本过少而退化。按「遮蔽类型 × 方法」累积全部折与重复后统一计算。
    pooled: dict[tuple[str, str], list[tuple[np.ndarray, np.ndarray]]] = {}
    start = time.time()

    for fold in range(folds):
        for repeat in range(repeats):
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
                if target.empty:
                    continue
                sigma_target = target["group_raw"].map(sigma).fillna(float(sigma.mean())).to_numpy(float)

                for method in methods:
                    pred = predict(method, masked, target[["province", "group_raw", "year"]], mask_seed, draws)
                    truth = target["target_truth"].to_numpy(float)

                    for delta in DELTA_GRID:
                        shifted = truth + delta * sigma_target
                        if np.any(shifted <= 0):
                            # 价格/消费量必须为正；δ<0 时截断到极小正值并记录
                            shifted = np.maximum(shifted, 1e-6)
                        metric = calibration_metrics(shifted, pred)
                        delta_rows.append(
                            {
                                "panel": args.panel,
                                "fold": fold,
                                "repeat": repeat,
                                "mask_type": mask_type,
                                "method": method,
                                "delta": delta,
                                "n": metric["n"],
                                "scaled_mae": metric["scaled_mae"],
                                "coverage95": metric["coverage95"],
                                "coverage50": metric["coverage50"],
                                "calibration_error": metric["calibration_error"],
                                "signed_bias": float(np.mean(pred.mean - shifted)),
                            }
                        )

                    pooled.setdefault((mask_type, method), []).append((truth.copy(), pred.mean.copy()))

    delta_df = pd.DataFrame(delta_rows)
    delta_df.to_csv(run_dir / "mnar_delta_grid.csv", index=False, encoding="utf-8-sig")

    mar_rows, mar_quintiles = [], []
    for (mask_type, method), blocks in pooled.items():
        truth = np.concatenate([b[0] for b in blocks])
        mean = np.concatenate([b[1] for b in blocks])
        diag = mar_diagnostic(truth, mean, np.ones(len(truth)))
        mar_rows.append(
            {
                "panel": args.panel,
                "mask_type": mask_type,
                "method": method,
                "n": diag.get("n", len(truth)),
                "bias_overall": diag.get("bias_overall"),
                "bias_slope": diag.get("bias_slope"),
                "monotone_bias": diag.get("monotone_bias"),
            }
        )
        for row in diag.get("by_quintile", []):
            mar_quintiles.append({"mask_type": mask_type, "method": method, **row})
    mar_df = pd.DataFrame(mar_rows)
    mar_df.to_csv(run_dir / "mar_diagnostic.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(mar_quintiles).to_csv(run_dir / "mar_quintile_profile.csv", index=False, encoding="utf-8-sig")

    delta_summary = (
        delta_df.groupby(["mask_type", "method", "delta"], as_index=False)
        .agg(
            n_eval=("n", "sum"),
            scaled_mae=("scaled_mae", "mean"),
            coverage95=("coverage95", "mean"),
            calibration_error=("calibration_error", "mean"),
            signed_bias=("signed_bias", "mean"),
        )
        .sort_values(["mask_type", "method", "delta"])
    )
    delta_summary.to_csv(run_dir / "mnar_delta_summary.csv", index=False, encoding="utf-8-sig")

    mar_summary = mar_df.sort_values(["mask_type", "method"]).reset_index(drop=True)
    mar_summary.to_csv(run_dir / "mar_summary.csv", index=False, encoding="utf-8-sig")

    # 排序稳定性：每个 δ 下按 calibration_error 排名，看主方法的名次是否漂移
    rank_rows = []
    for (mask_type, delta), block in delta_summary.groupby(["mask_type", "delta"]):
        ranked = block.sort_values("calibration_error")
        for pos, (_, row) in enumerate(ranked.iterrows(), start=1):
            rank_rows.append(
                {
                    "mask_type": mask_type,
                    "delta": delta,
                    "method": row["method"],
                    "rank": pos,
                    "calibration_error": row["calibration_error"],
                }
            )
    rank_df = pd.DataFrame(rank_rows)
    rank_df.to_csv(run_dir / "mnar_rank_stability.csv", index=False, encoding="utf-8-sig")

    print(f"[R108/109] {args.panel} | {args.profile} | {len(delta_df)} 行 | {time.time() - start:.1f}s")
    print("\nR109 MNAR δ 网格（calibration_error，越低越好）:")
    print(
        delta_summary.pivot_table(
            index=["mask_type", "method"], columns="delta", values="calibration_error"
        ).round(3).to_string()
    )
    print("\nR109 覆盖率@95%（δ 越大应越低，属预期）:")
    print(
        delta_summary.pivot_table(
            index=["mask_type", "method"], columns="delta", values="coverage95"
        ).round(3).to_string()
    )
    print("\nR108 MAR 诊断（bias_slope 接近 0 才支持 MAR）:")
    print(mar_summary.round(3).to_string(index=False))
    print("\n排序稳定性（每个 δ 下 calibration_error 的名次）:")
    print(rank_df.pivot_table(index="method", columns=["mask_type", "delta"], values="rank").to_string())

    finalize_run(
        run_dir,
        _finite(
            {
                "command": "sensitivity-mar-mnar",
                "panel": args.panel,
                "profile": args.profile,
                "source": str(source),
                "folds": folds,
                "repeats": repeats,
                "methods": methods,
                "delta_grid": list(DELTA_GRID),
                "n_delta_rows": int(len(delta_df)),
                "wall_seconds": time.time() - start,
                "evidence_status": "masking_protocol",
                "evidence_note": (
                    "遮蔽协议下的插补敏感性。真值是遮蔽前的实测值，"
                    "因此 R108/R109 的结论不依赖 B2 的场景生成器；"
                    "但缺失机制是**人造**的（MCAR 遮蔽），不是真实缺失机制。"
                ),
                "delta_summary": delta_summary.to_dict("records"),
                "mar_summary": mar_summary.to_dict("records"),
                "rank_stability": rank_df.to_dict("records"),
            }
        ),
        {
            "command": "sensitivity-mar-mnar",
            "panel": args.panel,
            "profile": args.profile,
            "folds": folds,
            "repeats": repeats,
            "methods": methods,
            "delta_grid": list(DELTA_GRID),
        },
    )
    print(f"\n[run] {run_dir}")


if __name__ == "__main__":
    main()
