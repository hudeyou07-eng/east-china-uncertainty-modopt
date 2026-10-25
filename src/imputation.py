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


def hierarchical_rw_predict(
    train: pd.DataFrame,
    target: pd.DataFrame,
    ridge: float = 1.0,
    year_rw: float = 4.0,
    parameterisation: str = "original",
    interaction_ridge: float | None = None,
    interaction_min_observations: int | None = None,
) -> Prediction:
    """Gaussian additive MAP model with random-effect shrinkage and a RW1 year penalty.

    Parameters
    ----------
    ridge
        Prior precision on the province and group effects (default 1.0, the
        value hard-coded before this signature existed).
    year_rw
        Weight on the first-order random-walk penalty over year effects
        (default 4.0, likewise the historical constant).
    parameterisation
        ``"original"`` (default) reproduces the historical all-dummies design
        bit for bit. ``"year_centered"`` removes only the intercept-versus-year
        collinearity by centring the year effects to sum to zero, leaving the
        province and group priors untouched. ``"reference"`` switches to
        reference coding, which also removes the ridge from one province and
        one group level and therefore defines a *different* prior.
    interaction_ridge
        When given, add one province-by-group interaction effect per observed
        series, shrunk with this prior precision. ``None`` (default) keeps the
        purely additive specification.
    interaction_min_observations
        Only create an interaction effect for a series that still has at least
        this many observed values. ``None`` (default) creates one for every
        series present in ``train``, including series that are entirely masked
        and therefore cannot inform the effect.
    """
    observed = train.dropna(subset=["value"]).copy()
    if len(observed) < 10 or (observed["value"] <= 0).any():
        raise ValueError("Hierarchical RW model requires at least ten positive observations")
    provinces = sorted(train["province"].unique())
    groups = sorted(train["group_raw"].unique())
    years = sorted(train["year"].unique())

    if parameterisation == "reference":
        return _hierarchical_rw_reference(
            observed, target, provinces, groups, years, ridge, year_rw
        )
    if parameterisation == "year_centered":
        return _hierarchical_rw_year_centered(
            observed, target, provinces, groups, years, ridge, year_rw
        )
    if parameterisation != "original":
        raise ValueError(f"Unknown parameterisation: {parameterisation}")

    if interaction_ridge is None:
        series = []
    elif interaction_min_observations is None:
        series = sorted({(p, g) for p, g in zip(train["province"], train["group_raw"])})
    else:
        counts = observed.groupby(["province", "group_raw"]).size()
        series = sorted(k for k, n in counts.items()
                        if n >= int(interaction_min_observations))
    series_index = {k: i for i, k in enumerate(series)}
    n_int = len(series) if interaction_ridge is not None else 0
    n_main = 1 + len(provinces) + len(groups) + len(years)
    p = n_main + n_int

    def design(frame: pd.DataFrame) -> np.ndarray:
        x = np.zeros((len(frame), p))
        x[:, 0] = 1.0
        for row_pos, (_, row) in enumerate(frame.iterrows()):
            x[row_pos, 1 + provinces.index(row["province"])] = 1.0
            x[row_pos, 1 + len(provinces) + groups.index(row["group_raw"])] = 1.0
            x[row_pos, 1 + len(provinces) + len(groups) + years.index(row["year"])] = 1.0
            if n_int:
                idx = series_index.get((row["province"], row["group_raw"]))
                if idx is not None:
                    x[row_pos, n_main + idx] = 1.0
        return x

    x = design(observed)
    y = np.log(observed["value"].to_numpy(float))
    p = x.shape[1]
    precision = np.eye(p) * 1e-6
    precision[1 : 1 + len(provinces), 1 : 1 + len(provinces)] += np.eye(len(provinces)) * ridge
    g0 = 1 + len(provinces)
    precision[g0 : g0 + len(groups), g0 : g0 + len(groups)] += np.eye(len(groups)) * ridge
    y0 = 1 + len(provinces) + len(groups)
    diff = np.zeros((max(len(years) - 1, 0), len(years)))
    for i in range(len(years) - 1):
        diff[i, i], diff[i, i + 1] = -1.0, 1.0
    if len(diff):
        precision[y0 : y0 + len(years), y0 : y0 + len(years)] += year_rw * (diff.T @ diff)
    if n_int:
        precision[n_main:, n_main:] += np.eye(n_int) * float(interaction_ridge)
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


def _hierarchical_rw_year_centered(
    observed: pd.DataFrame,
    target: pd.DataFrame,
    provinces: list,
    groups: list,
    years: list,
    ridge: float,
    year_rw: float,
) -> Prediction:
    """Minimal fix for the rank deficiency: year effects constrained to sum to zero.

    The intercept, all province dummies and all group dummies are kept exactly
    as in the original design, so the province and group priors are unchanged.
    Only the year block is reparameterised: ``Y - 1`` free contrasts with the
    last year implied by ``sum(e) = 0``. The RW1 penalty is applied to the
    full year vector reconstructed from those contrasts.
    """
    n_prov, n_group, n_year = len(provinces), len(groups), len(years)
    n_free_year = max(n_year - 1, 0)
    p = 1 + n_prov + n_group + n_free_year

    def design(frame: pd.DataFrame) -> np.ndarray:
        x = np.zeros((len(frame), p))
        x[:, 0] = 1.0
        y0 = 1 + n_prov + n_group
        for row_pos, (_, row) in enumerate(frame.iterrows()):
            x[row_pos, 1 + provinces.index(row["province"])] = 1.0
            x[row_pos, 1 + n_prov + groups.index(row["group_raw"])] = 1.0
            yi = years.index(row["year"])
            if yi < n_free_year:
                x[row_pos, y0 + yi] = 1.0
            elif n_free_year:
                x[row_pos, y0 : y0 + n_free_year] = -1.0
        return x

    x = design(observed)
    y = np.log(observed["value"].to_numpy(float))
    precision = np.eye(p) * 1e-6
    precision[1 : 1 + n_prov, 1 : 1 + n_prov] += np.eye(n_prov) * ridge
    g0 = 1 + n_prov
    precision[g0 : g0 + n_group, g0 : g0 + n_group] += np.eye(n_group) * ridge
    y0 = g0 + n_group
    if n_free_year:
        # contrast basis C: (n_year x n_free_year), last year implied by sum-to-zero
        basis = np.zeros((n_year, n_free_year))
        basis[:n_free_year, :] = np.eye(n_free_year)
        basis[n_free_year, :] = -1.0
        diff = np.zeros((n_year - 1, n_year))
        for i in range(n_year - 1):
            diff[i, i], diff[i, i + 1] = -1.0, 1.0
        dc = diff @ basis
        precision[y0:, y0:] += year_rw * (dc.T @ dc)
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


def _hierarchical_rw_reference(
    observed: pd.DataFrame,
    target: pd.DataFrame,
    provinces: list,
    groups: list,
    years: list,
    ridge: float,
    year_rw: float,
) -> Prediction:
    """Reference-coded variant: intercept + (P-1) + (G-1) + (Y-1) free effects.

    The last province, last group and last year serve as reference levels. Note
    that this also drops the ridge from one province and one group level, so it
    defines a *different* prior rather than merely a different parameterisation.
    """
    n_prov, n_group, n_year = len(provinces), len(groups), len(years)
    p = 1 + (n_prov - 1) + (n_group - 1) + (n_year - 1)

    def design(frame: pd.DataFrame) -> np.ndarray:
        x = np.zeros((len(frame), p))
        x[:, 0] = 1.0
        for row_pos, (_, row) in enumerate(frame.iterrows()):
            pi = provinces.index(row["province"])
            gi = groups.index(row["group_raw"])
            yi = years.index(row["year"])
            if pi < n_prov - 1:
                x[row_pos, 1 + pi] = 1.0
            if gi < n_group - 1:
                x[row_pos, 1 + (n_prov - 1) + gi] = 1.0
            if yi < n_year - 1:
                x[row_pos, 1 + (n_prov - 1) + (n_group - 1) + yi] = 1.0
        return x

    x = design(observed)
    y = np.log(observed["value"].to_numpy(float))
    precision = np.eye(p) * 1e-6
    precision[1 : 1 + (n_prov - 1), 1 : 1 + (n_prov - 1)] += np.eye(max(n_prov - 1, 0)) * ridge
    g0 = 1 + (n_prov - 1)
    precision[g0 : g0 + (n_group - 1), g0 : g0 + (n_group - 1)] += np.eye(max(n_group - 1, 0)) * ridge
    y0 = g0 + (n_group - 1)
    n_free_year = n_year - 1
    if n_free_year > 0:
        diff = np.zeros((n_free_year, n_free_year))
        for i in range(n_free_year):
            diff[i, i] = 1.0
            if i > 0:
                diff[i, i] = -1.0
                diff[i, i - 1] = 1.0
        precision[y0:, y0:] += year_rw * (diff.T @ diff)
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


def predict(
    method: str,
    train: pd.DataFrame,
    target: pd.DataFrame,
    seed: int,
    draws: int,
    **kwargs,
) -> Prediction:
    if method == "group_mean":
        return group_mean_predict(train, target)
    if method == "interpolation":
        return interpolation_predict(train, target)
    if method == "mice":
        return mice_predict(train, target, seed, draws)
    if method == "bayesian_additive":
        return bayesian_additive_predict(train, target)
    if method == "hierarchical_rw":
        return hierarchical_rw_predict(train, target, **kwargs)
    raise ValueError(f"Unknown imputation method: {method}")
