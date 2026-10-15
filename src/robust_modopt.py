from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix


@dataclass
class ModoptResult:
    q: np.ndarray
    z: np.ndarray
    objective: float
    success: bool
    message: str
    mip_gap: float | None


def _box_extrema(coeff: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> tuple[float, float]:
    minimum = np.where(coeff >= 0, coeff * lower, coeff * upper).sum()
    maximum = np.where(coeff >= 0, coeff * upper, coeff * lower).sum()
    return float(minimum), float(maximum)


def solve_chance_modopt(
    objective_coeff: np.ndarray,
    nutrient_coeff: np.ndarray,
    nutrient_lower: np.ndarray,
    nutrient_upper: np.ndarray,
    q_lower: np.ndarray,
    q_upper: np.ndarray,
    objective_weights: np.ndarray,
    epsilon: float,
    time_limit: float = 300.0,
    mip_rel_gap: float = 1e-3,
) -> ModoptResult:
    """Solve the scenario MILP.

    objective_coeff: [S, L, K]
    nutrient_coeff: [S, J, K]
    """
    objective_coeff = np.asarray(objective_coeff, dtype=float)
    nutrient_coeff = np.asarray(nutrient_coeff, dtype=float)
    if not np.isfinite(objective_coeff).all() or not np.isfinite(nutrient_coeff).all():
        raise ValueError("Objective and nutrient coefficients must be finite")
    s_count, l_count, k_count = objective_coeff.shape
    if nutrient_coeff.shape[0] != s_count or nutrient_coeff.shape[2] != k_count:
        raise ValueError("Objective and nutrient scenario shapes are inconsistent")
    j_count = nutrient_coeff.shape[1]
    arrays = [nutrient_lower, nutrient_upper, q_lower, q_upper, objective_weights]
    if not all(np.isfinite(np.asarray(a, dtype=float)).all() for a in arrays):
        raise ValueError("All bounds and weights must be finite")
    if np.any(q_lower < 0) or np.any(q_lower > q_upper):
        raise ValueError("Invalid decision bounds")
    if np.any(objective_weights <= 0) or len(objective_weights) != l_count:
        raise ValueError("Objective weights must be positive and match objective count")
    if not 0 <= epsilon < 1:
        raise ValueError("epsilon must be in [0, 1)")

    # Common lower bound and payoff-table scale, frozen before the MILP.
    u = np.empty(l_count)
    d = np.empty(l_count)
    for ell in range(l_count):
        minima, maxima = zip(
            *[_box_extrema(objective_coeff[s, ell], q_lower, q_upper) for s in range(s_count)]
        )
        u[ell] = min(minima)
        d[ell] = max(maxima) - u[ell]
    active = d > 1e-6 * np.maximum(1.0, np.abs(u))
    if not active.any():
        raise ValueError("All objectives have zero or near-zero scale")
    active_weights = objective_weights[active]
    active_weights = active_weights / active_weights.sum()
    c_q = np.zeros(k_count)
    for s in range(s_count):
        c_q += np.sum(
            active_weights[:, None] * objective_coeff[s, active] / d[active, None], axis=0
        ) / s_count
    c = np.concatenate([c_q, np.zeros(s_count)])

    n_vars = k_count + s_count
    rows = 2 * s_count * j_count + 1
    matrix = lil_matrix((rows, n_vars), dtype=float)
    lower_constraints = np.full(rows, -np.inf)
    upper_constraints = np.full(rows, np.inf)
    row = 0
    for s in range(s_count):
        for j in range(j_count):
            coeff = nutrient_coeff[s, j]
            min_value, max_value = _box_extrema(coeff, q_lower, q_upper)
            m_minus = max(0.0, float(nutrient_lower[j] - min_value))
            m_plus = max(0.0, float(max_value - nutrient_upper[j]))
            matrix[row, :k_count] = coeff
            matrix[row, k_count + s] = m_minus
            lower_constraints[row] = nutrient_lower[j]
            row += 1
            matrix[row, :k_count] = coeff
            matrix[row, k_count + s] = -m_plus
            upper_constraints[row] = nutrient_upper[j]
            row += 1
    matrix[row, k_count:] = 1.0
    upper_constraints[row] = np.floor(epsilon * s_count + 1e-12)

    bounds = Bounds(
        np.concatenate([q_lower, np.zeros(s_count)]),
        np.concatenate([q_upper, np.ones(s_count)]),
    )
    integrality = np.concatenate([np.zeros(k_count, dtype=int), np.ones(s_count, dtype=int)])
    result = milp(
        c=c,
        integrality=integrality,
        bounds=bounds,
        constraints=LinearConstraint(matrix.tocsr(), lower_constraints, upper_constraints),
        options={"time_limit": time_limit, "mip_rel_gap": mip_rel_gap},
    )
    if result.x is None:
        return ModoptResult(
            q=np.full(k_count, np.nan),
            z=np.full(s_count, np.nan),
            objective=float("nan"),
            success=False,
            message=str(result.message),
            mip_gap=getattr(result, "mip_gap", None),
        )
    return ModoptResult(
        q=result.x[:k_count],
        z=np.rint(result.x[k_count:]),
        objective=float(result.fun),
        success=bool(result.success),
        message=str(result.message),
        mip_gap=getattr(result, "mip_gap", None),
    )


def make_toy_problem(seed: int, scenarios: int = 20) -> dict[str, np.ndarray | float]:
    rng = np.random.default_rng(seed)
    k_count, l_count, j_count = 3, 6, 2
    objective = rng.uniform(0.5, 3.0, size=(scenarios, l_count, k_count))
    nutrient_base = np.array([[1.4, 0.9, 0.4], [0.2, 1.2, 1.0]])
    nutrient = nutrient_base[None, :, :] * rng.lognormal(0.0, 0.06, size=(scenarios, j_count, k_count))
    return {
        "objective_coeff": objective,
        "nutrient_coeff": nutrient,
        "nutrient_lower": np.array([70.0, 55.0]),
        "nutrient_upper": np.array([220.0, 180.0]),
        "q_lower": np.array([0.0, 0.0, 0.0]),
        "q_upper": np.array([120.0, 120.0, 120.0]),
        "objective_weights": np.array([0.5, 0.1, 0.1, 0.1, 0.1, 0.1]),
        "epsilon": 0.05,
    }
