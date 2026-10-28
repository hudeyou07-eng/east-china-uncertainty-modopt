from __future__ import annotations

import numpy as np

from .imputation import Prediction

# 名义覆盖率水平：R106 的 coverage–width 曲线在这四个点上取。
NOMINAL_LEVELS = (0.50, 0.80, 0.90, 0.95)

# 各名义水平对应的双侧正态分位数。
_Z = {0.50: 0.6744897502, 0.80: 1.2815515655, 0.90: 1.6448536270, 0.95: 1.9599639845}


def effective_sd(pred: Prediction) -> np.ndarray:
    """由 95% 区间反推的等效正态标准差。

    这样做的原因：``Prediction`` 只携带 80%/95% 两套区间，且不同方法的区间
    构造方式不同（正态、对数正态、分位数）。若要计算 50%/90% 覆盖率，
    必须有一个统一尺度。以 ``(upper95 - lower95) / (2·z95)`` 作为等效 SD，
    对所有方法一视同仁，无需改动各插补实现。

    代价：对数正态类方法（hierarchical_rw / bayesian_additive）的区间不对称，
    用对称正态近似会在 50% 附近有轻微偏差。为此同时输出 ``asymmetry95``，
    让不对称程度可见，而不是被近似掩盖。
    """
    return (np.asarray(pred.upper95, float) - np.asarray(pred.lower95, float)) / (2.0 * _Z[0.95])


def coverage_at(truth: np.ndarray, pred: Prediction, level: float) -> float:
    """给定名义水平下的经验覆盖率。"""
    if level not in _Z:
        raise ValueError(f"Unsupported nominal level {level}; use one of {sorted(_Z)}")
    half = _Z[level] * effective_sd(pred)
    mean = np.asarray(pred.mean, float)
    return float(np.mean((truth >= mean - half) & (truth <= mean + half)))


def calibration_metrics(truth: np.ndarray, pred: Prediction) -> dict[str, float]:
    truth = np.asarray(truth, dtype=float)
    if len(truth) == 0 or not np.isfinite(truth).all():
        raise ValueError("Truth values must be finite and non-empty")
    arrays = [pred.mean, pred.lower80, pred.upper80, pred.lower95, pred.upper95]
    if any(np.asarray(a).shape != truth.shape for a in arrays):
        raise ValueError("Prediction arrays must match truth shape")
    if any(not np.isfinite(np.asarray(a, dtype=float)).all() for a in arrays):
        raise ValueError("Predictions and intervals must be finite")
    if np.any(pred.lower95 > pred.lower80) or np.any(pred.lower80 > pred.mean):
        raise ValueError("Lower interval bounds are not ordered")
    if np.any(pred.mean > pred.upper80) or np.any(pred.upper80 > pred.upper95):
        raise ValueError("Upper interval bounds are not ordered")
    scale = max(float(np.mean(np.abs(truth))), 1e-8)
    log_truth = np.log(np.maximum(truth, 1e-12))
    log_pred = np.log(np.maximum(pred.mean, 1e-12))

    out = {
        "n": int(len(truth)),
        "scaled_mae": float(np.mean(np.abs(pred.mean - truth)) / scale),
        "log_rmse": float(np.sqrt(np.mean((log_pred - log_truth) ** 2))),
        "coverage80": float(np.mean((truth >= pred.lower80) & (truth <= pred.upper80))),
        "coverage95": float(np.mean((truth >= pred.lower95) & (truth <= pred.upper95))),
        "width80": float(np.mean(pred.upper80 - pred.lower80)),
        "width95": float(np.mean(pred.upper95 - pred.lower95)),
        "negative_predictions": int(np.sum(pred.mean <= 0)),
        # 95% 区间的上下不对称度：(上 − 均值) − (均值 − 下)。
        # 正态/分位数法应接近 0；对数正态法为正（右偏）。
        "asymmetry95": float(np.mean((pred.upper95 - pred.mean) - (pred.mean - pred.lower95))),
    }

    # R106：coverage–width 曲线与标定误差
    sd = effective_sd(pred)
    errors = []
    for level in NOMINAL_LEVELS:
        cov = coverage_at(truth, pred, level)
        out[f"coverage{int(level * 100)}"] = cov
        out[f"width{int(level * 100)}"] = float(2.0 * _Z[level] * np.mean(sd))
        errors.append(abs(cov - level))
    out["calibration_error"] = float(np.mean(errors))
    out["coverage_slope"] = float((out["coverage95"] - out["coverage50"]) / 0.45)
    return out
