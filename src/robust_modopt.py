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


def normalized_cost_matrix(
    objective_coeff: np.ndarray,
    objective_weights: np.ndarray,
    q_lower: np.ndarray,
    q_upper: np.ndarray,
) -> np.ndarray:
    """逐场景的归一化目标系数 ``[S, K]``，其跨场景均值等于 :func:`normalized_cost_vector`。

    抽出来的原因：期望目标只用到均值，**风险度量（CVaR）需要逐场景的成本**。
    两者必须共用同一套 ``d_ℓ`` 缩放与权重归一，否则「求解时最小化的」与
    「事后评估的」不是同一个函数，regret 之类的量会算错（R304 踩过）。
    """
    objective_coeff = np.asarray(objective_coeff, dtype=float)
    objective_weights = np.asarray(objective_weights, dtype=float)
    q_lower = np.asarray(q_lower, dtype=float)
    q_upper = np.asarray(q_upper, dtype=float)
    s_count, l_count, k_count = objective_coeff.shape
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
    return np.einsum(
        "l,slk->sk", active_weights / d[active], objective_coeff[:, active, :]
    )


def normalized_cost_vector(
    objective_coeff: np.ndarray,
    objective_weights: np.ndarray,
    q_lower: np.ndarray,
    q_upper: np.ndarray,
) -> np.ndarray:
    """把多目标压成单一线性目标 ``c_q``（求解器实际最小化的那个向量）。

    归一化口径：每个目标用**payoff 区间** ``d_ℓ = max_s max − min_s min`` 缩放，
    再按权重求和、跨场景取均值。零尺度的目标（``d_ℓ ≈ 0``）被剔除后重新归一权重。

    抽成独立函数是为了让「事后评估某个 q 的加权目标值」与求解器**用同一个口径**——
    否则 R304 这类 regret 计算会因为归一化不一致而与求解器结果对不上。
    """
    # 实现下沉到 normalized_cost_matrix，保证「均值目标」与「逐场景目标」
    # 永远不会出现两套缩放口径。
    return normalized_cost_matrix(
        objective_coeff, objective_weights, q_lower, q_upper
    ).mean(axis=0)


def weighted_objective_value(
    objective_coeff: np.ndarray,
    q: np.ndarray,
    objective_weights: np.ndarray,
    q_lower: np.ndarray,
    q_upper: np.ndarray,
) -> float:
    """在给定权重下评估决策 ``q`` 的加权目标值（与求解器同口径）。"""
    c_q = normalized_cost_vector(objective_coeff, objective_weights, q_lower, q_upper)
    return float(c_q @ np.asarray(q, dtype=float))


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
    extra_constraints: list[tuple[np.ndarray, float, float]] | None = None,
    use_chance_constraint: bool = True,
    big_m: str = "tight",
    chance_mode: str = "joint",
    risk_weight: float = 0.0,
    cvar_alpha: float = 0.90,
) -> ModoptResult:
    """Solve the scenario MILP.

    objective_coeff: [S, L, K]
    nutrient_coeff: [S, J, K]

    extra_constraints: 可选的额外线性约束列表，每项为 ``(coeff, lower, upper)``，
    作用在决策向量 ``q`` 上（长度 K）。用于表达组间联合约束，例如
    CDG 的「畜禽肉合计 40-75 g」需要 ``q[G05] + q[G06] ∈ [40, 75]``，
    这类约束无法用逐组 box bound 表达。默认 ``None`` 时行为与旧版完全一致。

    big_m: 机会约束里 ``z`` 的大 M 取值方式。

        * ``"tight"``（默认）——逐 (场景, 营养素) 由 box 极值推出最小可用 M，
          即 ``M⁻ = max(0, ℓ_j − min_sj)``、``M⁺ = max(0, max_sj − u_j)``。
        * ``"global"``——全部取同一个 ``max(M⁻, M⁺)``。

        M 越大，LP 松弛越松，分支定界越慢。R306 用 ``"global"`` 作对照，
        验证「tight 不是白写的」。**正式结果只用 ``"tight"``。**

    chance_mode: 机会约束的作用方式（R305）。

        * ``"joint"``（默认，正式口径）——每个**场景**一个 ``z_s``，
          预算 ``Σ_s z_s ≤ floor(εS)``。语义是「至少有 1−ε 的场景**全部营养素**
          同时达标」，即**联合**机会约束。
        * ``"marginal"``——每个 **(场景, 营养素)** 一个 ``z_sj``，
          逐营养素预算 ``Σ_s z_sj ≤ floor(εS)``。语义是「**每个营养素**各自
          至少 1−ε 的场景达标」。

        两者的关键差别：marginal 下**联合违反率的上界是 J·ε**，不是 ε。
        若 J=9、ε=0.05，marginal 允许「全部营养素同时达标」的场景比例低到 55%，
        与 joint 的 95% 完全不是一回事。R305 就是量化这个差距。
        **正式结果只用 ``"joint"``；marginal 仅作附录对照。**

    risk_weight: 风险厌恶程度 ``λ ∈ [0, 1]``。默认 ``0.0`` = 纯期望（旧行为，逐位不变）。

        目标改为 ``(1−λ)·E[cost] + λ·CVaR_α(cost)``。

        **为什么需要这个开关**：目标对 ``q`` 线性、价格只进目标不进约束时，
        ``min_q E_s[c_s·q] = min_q (E_s c_s)·q``——**期望的最优解等于最优解的期望**，
        场景平均根本不改变 argmin。实测 D3 ≡ D1（``max|Δq| ≤ 1e-6``），
        即价格**不确定性**对决策结构性零传导（CHANGELOG §21.5b）。
        要让不确定性真正进入决策，目标必须是非线性的，CVaR 是最常用的一种。

    cvar_alpha: CVaR 的置信水平 ``α ∈ [0, 1)``，默认 0.90（关注最差 10% 场景）。

        ``α = 0`` 时 CVaR 退化为期望，此时 ``λ`` 无意义——这也是一个自检点。
    """
    if big_m not in ("tight", "global"):
        raise ValueError(f"未知 big_m: {big_m}")
    if chance_mode not in ("joint", "marginal"):
        raise ValueError(f"未知 chance_mode: {chance_mode}")
    if not 0.0 <= risk_weight <= 1.0:
        raise ValueError("risk_weight 必须在 [0, 1] 内")
    if not 0.0 <= cvar_alpha < 1.0:
        raise ValueError("cvar_alpha 必须在 [0, 1) 内")
    objective_coeff = np.asarray(objective_coeff, dtype=float)
    nutrient_coeff = np.asarray(nutrient_coeff, dtype=float)
    if not np.isfinite(objective_coeff).all() or not np.isfinite(nutrient_coeff).all():
        raise ValueError("Objective and nutrient coefficients must be finite")
    s_count, l_count, k_count = objective_coeff.shape
    if nutrient_coeff.shape[0] != s_count or nutrient_coeff.shape[2] != k_count:
        raise ValueError("Objective and nutrient scenario shapes are inconsistent")
    j_count = nutrient_coeff.shape[1]
    nutrient_lower = np.asarray(nutrient_lower, dtype=float)
    nutrient_upper = np.asarray(nutrient_upper, dtype=float)
    # 营养素上界允许 +inf（「不设上限」是合法语义），下界允许 -inf；
    # 但 NaN 与 q 的边界、权重必须有限。
    if np.isnan(nutrient_lower).any() or np.isnan(nutrient_upper).any():
        raise ValueError("Nutrient bounds must not be NaN")
    if np.any(nutrient_lower > nutrient_upper):
        raise ValueError("Nutrient lower bound exceeds upper bound")
    arrays = [q_lower, q_upper, objective_weights]
    if not all(np.isfinite(np.asarray(a, dtype=float)).all() for a in arrays):
        raise ValueError("All bounds and weights must be finite")
    if np.any(q_lower < 0) or np.any(q_lower > q_upper):
        raise ValueError("Invalid decision bounds")
    if np.any(objective_weights <= 0) or len(objective_weights) != l_count:
        raise ValueError("Objective weights must be positive and match objective count")
    if not 0 <= epsilon < 1:
        raise ValueError("epsilon must be in [0, 1)")

    # 多目标 → 单一线性目标（payoff 归一化，口径与 weighted_objective_value 一致）。
    c_q = normalized_cost_vector(objective_coeff, objective_weights, q_lower, q_upper)
    # z 变量个数：joint = 每场景一个；marginal = 每 (场景, 营养素) 一个。
    n_z = s_count if chance_mode == "joint" else s_count * j_count

    # 风险厌恶：追加 η（1 个）与 u_s（S 个），构成 CVaR 的 Rockafellar–Uryasev 线性化。
    #   CVaR_α(cost) = min_η { η + 1/((1−α)S) · Σ_s max(0, cost_s − η) }
    # 展开后即 u_s ≥ cost_s − η、u_s ≥ 0，目标里加 λ·[η + 1/((1−α)S)·Σu_s]。
    # λ=0 时**完全不追加变量**，保证旧行为逐位不变。
    risk = risk_weight > 0.0
    n_risk = (1 + s_count) if risk else 0
    if risk:
        c_matrix = normalized_cost_matrix(objective_coeff, objective_weights, q_lower, q_upper)
        c = np.concatenate([
            (1.0 - risk_weight) * c_q,
            np.zeros(n_z),
            np.array([risk_weight]),
            np.full(s_count, risk_weight / ((1.0 - cvar_alpha) * s_count)),
        ])
    else:
        c_matrix = None
        c = np.concatenate([c_q, np.zeros(n_z)])

    n_vars = k_count + n_z + n_risk
    eta_col = k_count + n_z
    u_col0 = eta_col + 1

    def _z_index(s: int, j: int) -> int:
        """z 在决策向量里的列号。"""
        return k_count + (s if chance_mode == "joint" else s * j_count + j)

    budget_rows = 1 if chance_mode == "joint" else j_count
    extra = list(extra_constraints or [])
    for coeff, _lo, _hi in extra:
        coeff = np.asarray(coeff, dtype=float)
        if coeff.shape != (k_count,):
            raise ValueError("extra_constraints 的系数长度必须等于决策变量数 K")
        if not np.isfinite(coeff).all():
            raise ValueError("extra_constraints 的系数必须有限")
    rows = (
        (2 * s_count * j_count if use_chance_constraint else 0)
        + budget_rows
        + len(extra)
        + (s_count if risk else 0)
    )
    matrix = lil_matrix((rows, n_vars), dtype=float)
    lower_constraints = np.full(rows, -np.inf)
    upper_constraints = np.full(rows, np.inf)
    row = 0
    if use_chance_constraint:
        # 先算全部 (场景, 营养素) 的 M，便于 global 模式取统一值。
        m_table: list[list[tuple[float, float]]] = []
        for s in range(s_count):
            per_scenario = []
            for j in range(j_count):
                coeff = nutrient_coeff[s, j]
                min_value, max_value = _box_extrema(coeff, q_lower, q_upper)
                m_minus = max(0.0, float(nutrient_lower[j] - min_value))
                m_plus = max(0.0, float(max_value - nutrient_upper[j]))
                per_scenario.append((m_minus, m_plus))
            m_table.append(per_scenario)
        if big_m == "global":
            biggest = max(max(pair) for per_scenario in m_table for pair in per_scenario)
            m_table = [
                [(biggest, biggest) for _ in per_scenario] for per_scenario in m_table
            ]
        for s in range(s_count):
            for j in range(j_count):
                coeff = nutrient_coeff[s, j]
                m_minus, m_plus = m_table[s][j]
                z_col = _z_index(s, j)
                matrix[row, :k_count] = coeff
                matrix[row, z_col] = m_minus
                lower_constraints[row] = nutrient_lower[j]
                row += 1
                matrix[row, :k_count] = coeff
                matrix[row, z_col] = -m_plus
                upper_constraints[row] = nutrient_upper[j]
                row += 1
    if chance_mode == "joint":
        matrix[row, k_count:] = 1.0
        upper_constraints[row] = np.floor(epsilon * s_count + 1e-12)
        row += 1
    else:
        # 逐营养素预算：每个营养素各自允许 floor(εS) 个场景违反。
        # 注意这**不是** ε 保证——联合违反率的上界是 J·ε。
        for j in range(j_count):
            matrix[row, k_count + j :: j_count] = 1.0
            upper_constraints[row] = np.floor(epsilon * s_count + 1e-12)
            row += 1
    for coeff, lo, hi in extra:
        matrix[row, :k_count] = np.asarray(coeff, dtype=float)
        lower_constraints[row] = float(lo)
        upper_constraints[row] = float(hi)
        row += 1

    if risk:
        # 上镜图约束：c_s·q − η − u_s ≤ 0，即 u_s ≥ c_s·q − η（u_s ≥ 0 由边界给出）
        for s in range(s_count):
            matrix[row, :k_count] = c_matrix[s]
            matrix[row, eta_col] = -1.0
            matrix[row, u_col0 + s] = -1.0
            upper_constraints[row] = 0.0
            row += 1

    z_upper = np.ones(n_z) if use_chance_constraint else np.zeros(n_z)
    if risk:
        # η 自由（可为负），u_s ≥ 0 无上界
        lower_full = np.concatenate([
            q_lower, np.zeros(n_z), np.array([-np.inf]), np.zeros(s_count)
        ])
        upper_full = np.concatenate([
            q_upper, z_upper, np.array([np.inf]), np.full(s_count, np.inf)
        ])
        integrality = np.concatenate([
            np.zeros(k_count, dtype=int), np.ones(n_z, dtype=int),
            np.zeros(n_risk, dtype=int),
        ])
    else:
        lower_full = np.concatenate([q_lower, np.zeros(n_z)])
        upper_full = np.concatenate([q_upper, z_upper])
        integrality = np.concatenate([np.zeros(k_count, dtype=int), np.ones(n_z, dtype=int)])
    bounds = Bounds(lower_full, upper_full)
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
            z=np.full(n_z, np.nan),
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
