from __future__ import annotations

import numpy as np

from .imputation import Prediction


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
    return {
        "n": int(len(truth)),
        "scaled_mae": float(np.mean(np.abs(pred.mean - truth)) / scale),
        "log_rmse": float(np.sqrt(np.mean((log_pred - log_truth) ** 2))),
        "coverage80": float(np.mean((truth >= pred.lower80) & (truth <= pred.upper80))),
        "coverage95": float(np.mean((truth >= pred.lower95) & (truth <= pred.upper95))),
        "width80": float(np.mean(pred.upper80 - pred.lower80)),
        "width95": float(np.mean(pred.upper95 - pred.lower95)),
        "negative_predictions": int(np.sum(pred.mean <= 0)),
    }
