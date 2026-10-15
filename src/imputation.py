from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.experimental import enable_iterative_imputer  # noqa: F401
from sklearn.impute import IterativeImputer
from sklearn.linear_model import BayesianRidge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


@dataclass
class Prediction:
    mean: np.ndarray
    lower80: np.ndarray
    upper80: np.ndarray
    lower95: np.ndarray
    upper95: np.ndarray


def _normal_intervals(mean: np.ndarray, std: np.ndarray) -> Prediction:
    std = np.maximum(std, 1e-8)
    return Prediction(
        mean=mean,
        lower80=mean - 1.2815515655 * std,
        upper80=mean + 1.2815515655 * std,
        lower95=mean - 1.9599639845 * std,
        upper95=mean + 1.9599639845 * std,
    )


def group_mean_predict(train: pd.DataFrame, target: pd.DataFrame) -> Prediction:
    observed = train.dropna(subset=["value"])
    group_mean = observed.groupby("group_raw")["value"].mean()
    global_mean = float(observed["value"].mean())
    mean = target["group_raw"].map(group_mean).fillna(global_mean).to_numpy(float)
    residuals = observed["value"] - observed["group_raw"].map(group_mean).fillna(global_mean)
    std = np.full(len(target), max(float(residuals.std(ddof=1)), 1e-6))
    return _normal_intervals(mean, std)


def interpolation_predict(train: pd.DataFrame, target: pd.DataFrame) -> Prediction:
    mean = []
    residual_pool = []
    for _, frame in train.dropna(subset=["value"]).groupby(["province", "group_raw"]):
        if len(frame) >= 3:
            ordered = frame.sort_values("year")
            years = ordered["year"].to_numpy(float)
            values = ordered["value"].to_numpy(float)
            for i in range(len(ordered)):
                keep = np.arange(len(ordered)) != i
                fitted = np.interp(years[i], years[keep], values[keep])
                residual_pool.append(values[i] - fitted)
    fallback = group_mean_predict(train, target)
    for pos, (_, row) in enumerate(target.iterrows()):
        series = train[
            (train["province"] == row["province"])
            & (train["group_raw"] == row["group_raw"])
        ].dropna(subset=["value"]).sort_values("year")
        if len(series) >= 2:
            mean.append(float(np.interp(row["year"], series["year"], series["value"])))
        else:
            mean.append(float(fallback.mean[pos]))
    std_value = float(np.std(residual_pool, ddof=1)) if len(residual_pool) >= 2 else float(np.std(train["value"].dropna()))
    return _normal_intervals(np.asarray(mean), np.full(len(target), max(std_value, 1e-6)))


def mice_predict(train: pd.DataFrame, target: pd.DataFrame, seed: int, draws: int) -> Prediction:
    matrix = train.pivot(index=["province", "group_raw"], columns="year", values="value")
    imputer = IterativeImputer(
        estimator=BayesianRidge(),
        max_iter=20,
        sample_posterior=True,
        random_state=seed,
        skip_complete=False,
        keep_empty_features=True,
    )
    imputer.fit(matrix)
    samples = []
    index_lookup = {key: i for i, key in enumerate(matrix.index)}
    year_lookup = {year: i for i, year in enumerate(matrix.columns)}
    for _ in range(draws):
        completed = imputer.transform(matrix)
        predictions = []
        for _, row in target.iterrows():
            key = (row["province"], row["group_raw"])
            if key not in index_lookup or row["year"] not in year_lookup:
                predictions.append(np.nan)
            else:
                predictions.append(completed[index_lookup[key], year_lookup[row["year"]]])
        samples.append(predictions)
    samples_arr = np.asarray(samples, dtype=float)
    if np.isnan(samples_arr).any():
        fallback = group_mean_predict(train, target).mean
        samples_arr = np.where(np.isnan(samples_arr), fallback[None, :], samples_arr)
    return Prediction(
        mean=np.mean(samples_arr, axis=0),
        lower80=np.quantile(samples_arr, 0.10, axis=0),
        upper80=np.quantile(samples_arr, 0.90, axis=0),
        lower95=np.quantile(samples_arr, 0.025, axis=0),
        upper95=np.quantile(samples_arr, 0.975, axis=0),
    )


def bayesian_additive_predict(train: pd.DataFrame, target: pd.DataFrame) -> Prediction:
    observed = train.dropna(subset=["value"]).copy()
    if len(observed) < 5:
        raise ValueError("At least five observed rows are required for Bayesian additive imputation")
    if (observed["value"] <= 0).any():
        raise ValueError("Bayesian additive model requires strictly positive values")
    features = ["province", "group_raw", "year"]
    preprocessing = ColumnTransformer(
        [
            ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["province", "group_raw"]),
            ("year", StandardScaler(), ["year"]),
        ]
    )
    model = Pipeline([("features", preprocessing), ("model", BayesianRidge())])
    model.fit(observed[features], np.log(observed["value"].to_numpy(float)))
    transformed = model.named_steps["features"].transform(target[features])
    log_mean, log_std = model.named_steps["model"].predict(transformed, return_std=True)
    # Log-normal posterior summaries; all intervals remain positive by construction.
    mean = np.exp(log_mean + 0.5 * log_std**2)
    return Prediction(
        mean=mean,
        lower80=np.exp(log_mean - 1.2815515655 * log_std),
        upper80=np.exp(log_mean + 1.2815515655 * log_std),
        lower95=np.exp(log_mean - 1.9599639845 * log_std),
        upper95=np.exp(log_mean + 1.9599639845 * log_std),
    )


def hierarchical_rw_predict(train: pd.DataFrame, target: pd.DataFrame) -> Prediction:
    """Gaussian additive MAP model with random-effect shrinkage and a RW1 year penalty."""
    observed = train.dropna(subset=["value"]).copy()
    if len(observed) < 10 or (observed["value"] <= 0).any():
        raise ValueError("Hierarchical RW model requires at least ten positive observations")
    provinces = sorted(train["province"].unique())
    groups = sorted(train["group_raw"].unique())
    years = sorted(train["year"].unique())

    def design(frame: pd.DataFrame) -> np.ndarray:
        x = np.zeros((len(frame), 1 + len(provinces) + len(groups) + len(years)))
        x[:, 0] = 1.0
        for row_pos, (_, row) in enumerate(frame.iterrows()):
            x[row_pos, 1 + provinces.index(row["province"])] = 1.0
            x[row_pos, 1 + len(provinces) + groups.index(row["group_raw"])] = 1.0
            x[row_pos, 1 + len(provinces) + len(groups) + years.index(row["year"])] = 1.0
        return x

    x = design(observed)
    y = np.log(observed["value"].to_numpy(float))
    p = x.shape[1]
    precision = np.eye(p) * 1e-6
    precision[1 : 1 + len(provinces), 1 : 1 + len(provinces)] += np.eye(len(provinces))
    g0 = 1 + len(provinces)
    precision[g0 : g0 + len(groups), g0 : g0 + len(groups)] += np.eye(len(groups))
    y0 = 1 + len(provinces) + len(groups)
    diff = np.zeros((max(len(years) - 1, 0), len(years)))
    for i in range(len(years) - 1):
        diff[i, i], diff[i, i + 1] = -1.0, 1.0
    if len(diff):
        precision[y0:, y0:] += 4.0 * (diff.T @ diff)
    system = x.T @ x + precision
    beta = np.linalg.solve(system, x.T @ y)
    residual = y - x @ beta
    sigma2 = max(float(np.sum(residual**2) / max(len(y) - min(p, len(y) - 1), 1)), 1e-6)
    covariance = sigma2 * np.linalg.inv(system)
    xt = design(target)
    log_mean = xt @ beta
    log_var = np.einsum("ij,jk,ik->i", xt, covariance, xt) + sigma2
    log_std = np.sqrt(np.maximum(log_var, 1e-12))
    mean = np.exp(log_mean + 0.5 * log_var)
    return Prediction(
        mean=mean,
        lower80=np.exp(log_mean - 1.2815515655 * log_std),
        upper80=np.exp(log_mean + 1.2815515655 * log_std),
        lower95=np.exp(log_mean - 1.9599639845 * log_std),
        upper95=np.exp(log_mean + 1.9599639845 * log_std),
    )


def predict(method: str, train: pd.DataFrame, target: pd.DataFrame, seed: int, draws: int) -> Prediction:
    if method == "group_mean":
        return group_mean_predict(train, target)
    if method == "interpolation":
        return interpolation_predict(train, target)
    if method == "mice":
        return mice_predict(train, target, seed, draws)
    if method == "bayesian_additive":
        return bayesian_additive_predict(train, target)
    if method == "hierarchical_rw":
        return hierarchical_rw_predict(train, target)
    raise ValueError(f"Unknown imputation method: {method}")
