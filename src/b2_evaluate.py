"""B2 真值评估：在遮蔽前真值上判断一个决策「好不好」。

**四个指标的操作定义**（Plan 只给了名字，这里把口径钉死，必须随结果报告）：

1. **联合营养可行（joint feasibility）**
   把决策 ``q`` 代回**真值**营养系数，加上非决策组的基线偏移，
   判断 11 个硬营养素是否**同时**落在 ``[ℓ_j, u_j]``。
   报告两个口径：

   * ``feasible_all``：全部 11 个营养素（含结构上不可达的，见下）
   * ``feasible_active``：仅机会约束里实际施加的那些（``inst.active_mask``）

   两者都要报。只报后者等于隐藏了「约束集本身就不完整」这件事。

2. **方向翻转（direction flip）——辅助指标**
   对每个组定义 ``direction_k = sign(q_k − b_k)``，其中 ``b`` 是该省基线。
   ``|q_k − b_k| < tol``（默认 1 g/day）记为 0（维持）。
   参考方向由**真值最优解** ``q*`` 给出（用真值系数、无机会约束求解）。
   某组翻转 ⟺ 方法给出的方向与 ``q*`` 的方向不同。
   翻转率 = 翻转组数 / 决策组数，跨重复聚合。

   **为什么以 q\\* 为参照而不是"增大/减小"二分类**：q\\* 是本问题的可辩护目标，
   方法偏离它就意味着建议方向错了；而"是否增减"没有客观基准。

   **为什么降为辅助（CHANGELOG §26.8 裁定 4）**：它只看方向，对幅度完全盲。
   实测 RNI 下 D0 与 D1 的决策差达 49–111 g/day，``flip_rate`` 只报 0.0003。
   主指标改为 ``dq_ref_*``（见 3.5）。

3. **objective_gap（目标间隙，有符号）**
   ``gap = [F(q) − F(q*)] / |F(q*)|``，其中 ``F`` 是与求解器**同一套**归一化后的
   加权目标和（逐目标用真值 payoff 区间缩放）。

   **为什么叫 gap 而不叫 regret**：``q*`` 是**真值可行**最优解（硬营养约束）。
   一个忽略营养约束的方法（如 D2）会得到比 ``q*`` 更低的目标值，
   此时 gap 为负。把负值叫「负 regret」会误导——它不是「比最优还好」，
   而是「靠违反约束换来的便宜」。负号本身就是不可行的信号，
   必须与 ``feasible_*`` 一起读，不能单独解释。

   p95 gap 取所有 (省, 重复) 的 95 分位。

4. **决策位移 ``dq_ref``（主指标）**
   ``dq_ref = max_k |q_k − q*_k|``（g/day），即与真值最优解在最敏感那一组上的差距。
   汇总给均值 / 中位 / p95 / 最大值，以及
   ``dq_ref_change_rate``（``dq_ref > DQ_CHANGE_TOL`` 的重复占比）。

   **为什么它当主指标**：它与 ``flip_rate`` 同量纲（比例 / 克每天），
   但**不会漏掉幅度变化**。``flip_rate`` 为 0 而 ``dq_ref`` 达 111 g/day 的情形
   已在 RNI 口径下实测到（CHANGELOG §26.8）。
   论文报告应写成「决策位移中位 X g/day、变化率 Y%」，
   而不是「翻转率 Z%」。

5. **Wilson 区间**
   可行率是比例，n 小的时候正态近似不可靠，一律给 Wilson 95% 区间。

**真值的来源与局限**：本模块接受任意 ``truth_*`` 系数张量。
在最小可跑版本里，真值 = 冻结合同的点估计（无噪声），这意味着
「场景中心 = 真值」，会系统性有利于后验均值类方法。
**正式 R200–R203 必须换成遮蔽前保留的伪完整面板**，否则不构成论文证据。
"""

from __future__ import annotations

import numpy as np

from src.b2_problem import Instance, OBJECTIVES

DIRECTION_TOL = 1.0  # g/day，小于此视为维持
DQ_CHANGE_TOL = 1.0  # g/day，决策位移超过此值即记为「真的变了」


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """比例的 Wilson 得分区间。total=0 时返回 (nan, nan)。"""
    if total <= 0:
        return (float("nan"), float("nan"))
    p = successes / total
    denom = 1.0 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * np.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (float(max(0.0, centre - half)), float(min(1.0, centre + half)))


def nutrient_totals(
    q: np.ndarray,
    nutrient_coeff: np.ndarray,
    nutrient_offset: np.ndarray,
) -> np.ndarray:
    """决策组贡献 + 非决策组基线偏移 = 全日总摄入量。"""
    return nutrient_coeff @ np.asarray(q, dtype=float) + nutrient_offset


def feasible_mask(
    q: np.ndarray,
    nutrient_coeff: np.ndarray,
    nutrient_offset: np.ndarray,
    nutrient_lower: np.ndarray,
    nutrient_upper: np.ndarray,
    tol: float = 1e-6,
) -> np.ndarray:
    """逐营养素的可行性布尔向量。``nutrient_lower/upper`` 须为**原始**边界（未减偏移）。"""
    total = nutrient_totals(q, nutrient_coeff, nutrient_offset)
    lower_ok = total >= nutrient_lower - tol
    upper_ok = np.isinf(nutrient_upper) | (total <= nutrient_upper + tol)
    return lower_ok & upper_ok


def joint_feasible(
    q: np.ndarray,
    nutrient_coeff: np.ndarray,
    nutrient_offset: np.ndarray,
    nutrient_lower: np.ndarray,
    nutrient_upper: np.ndarray,
    active_mask: np.ndarray | None = None,
) -> bool:
    mask = feasible_mask(q, nutrient_coeff, nutrient_offset, nutrient_lower, nutrient_upper)
    if active_mask is not None:
        mask = mask[active_mask]
    return bool(mask.all())


def direction(q: np.ndarray, baseline: np.ndarray, tol: float = DIRECTION_TOL) -> np.ndarray:
    delta = np.asarray(q, dtype=float) - np.asarray(baseline, dtype=float)
    out = np.sign(delta)
    out[np.abs(delta) < tol] = 0.0
    return out


def flip_flags(q: np.ndarray, q_ref: np.ndarray, baseline: np.ndarray) -> np.ndarray:
    """逐组的翻转布尔向量。方向不同的组记 True。"""
    return direction(q, baseline) != direction(q_ref, baseline)


def _payoff_scale(coeff: np.ndarray, q_lower: np.ndarray, q_upper: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """逐目标的 (下包络 u, 跨度 d)，与求解器内部归一化一致。"""
    l_count = coeff.shape[0]
    u = np.empty(l_count)
    d = np.empty(l_count)
    for ell in range(l_count):
        minima = np.where(coeff[ell] >= 0, coeff[ell] * q_lower, coeff[ell] * q_upper).sum()
        maxima = np.where(coeff[ell] >= 0, coeff[ell] * q_upper, coeff[ell] * q_lower).sum()
        u[ell] = float(minima)
        d[ell] = float(maxima - minima)
    return u, d


def normalized_objective(
    q: np.ndarray,
    objective_coeff: np.ndarray,
    objective_weights: np.ndarray,
    u: np.ndarray,
    d: np.ndarray,
) -> float:
    active = d > 1e-6 * np.maximum(1.0, np.abs(u))
    if not active.any():
        raise ValueError("所有目标跨度为零，无法归一化")
    w = objective_weights[active]
    w = w / w.sum()
    scaled = (objective_coeff[active] @ np.asarray(q, dtype=float) - u[active]) / d[active]
    return float(np.sum(w * scaled))


def objective_gap(
    q: np.ndarray,
    q_ref: np.ndarray,
    objective_coeff: np.ndarray,
    objective_weights: np.ndarray,
    q_lower: np.ndarray,
    q_upper: np.ndarray,
) -> float:
    """相对目标间隙，以真值可行最优解为基准。q 非有限时返回 nan。

    负值表示该方法的目标值低于真值可行最优解，即它一定违反了营养约束——
    必须与可行率一起解读，不能当作「更优」。
    """
    if not np.isfinite(q).all():
        return float("nan")
    u, d = _payoff_scale(objective_coeff, q_lower, q_upper)
    f_q = normalized_objective(q, objective_coeff, objective_weights, u, d)
    f_ref = normalized_objective(q_ref, objective_coeff, objective_weights, u, d)
    denom = abs(f_ref)
    if denom < 1e-12:
        return float("nan")
    return float((f_q - f_ref) / denom)


def summarize(
    feasible_all: list[bool],
    feasible_active: list[bool],
    flip_counts: list[int],
    group_counts: list[int],
    gaps: list[float],
    dq_refs: list[float] | None = None,
) -> dict[str, object]:
    """把一个方法的重复结果汇总成指标字典（含 Wilson 区间）。

    **主指标是 ``dq_ref_*``，``flip_rate`` 降为辅助。** 原因（CHANGELOG §26.8 裁定 4）：
    ``flip_rate`` 只看**方向**（``sign(q-b)`` 是否与 ``q*`` 一致，1 g/day 容差），
    对**幅度**完全盲。实测 RNI 口径下 D0 与 D1 的决策差达 49–111 g/day，
    但 ``flip_rate`` 只报 **0.0003**——因为它没有改变「增还是减」。
    用 ``flip_rate`` 当主指标会把「大幅位移但方向不变」误判成「没有差异」。

    ``dq_ref_*`` 直接度量 ``max_k |q_k − q*_k|``（g/day），
    ``dq_ref_change_rate`` 是位移超过 ``DQ_CHANGE_TOL`` 的重复占比，
    与 ``flip_rate`` 同量纲（比例），但不会漏掉幅度变化。
    """
    n = len(feasible_all)
    ok_all = int(sum(feasible_all))
    ok_act = int(sum(feasible_active))
    lo_all, hi_all = wilson_interval(ok_all, n)
    lo_act, hi_act = wilson_interval(ok_act, n)

    flips = np.asarray(flip_counts, dtype=float)
    groups = np.asarray(group_counts, dtype=float)
    valid_gap = np.asarray([g for g in gaps if np.isfinite(g)], dtype=float)

    out: dict[str, object] = {
        "n_repeats": n,
        "feasible_all_count": ok_all,
        "feasible_all_rate": ok_all / n if n else float("nan"),
        "feasible_all_wilson95": [lo_all, hi_all],
        "feasible_active_count": ok_act,
        "feasible_active_rate": ok_act / n if n else float("nan"),
        "feasible_active_wilson95": [lo_act, hi_act],
        "gap_mean": float(valid_gap.mean()) if valid_gap.size else float("nan"),
        "gap_p95": float(np.percentile(valid_gap, 95)) if valid_gap.size else float("nan"),
        "gap_n_valid": int(valid_gap.size),
        # ---- 辅助指标：只看方向，对幅度盲 ----
        "flip_rate": float(flips.sum() / groups.sum()) if groups.sum() else float("nan"),
        "flip_rate_per_repeat_mean": (
            float(flips.mean() / groups.mean())
            if groups.size and groups.mean()
            else float("nan")
        ),
    }

    if dq_refs is not None:
        dq = np.asarray([v for v in dq_refs if np.isfinite(v)], dtype=float)
        out.update(
            {
                "dq_ref_n_valid": int(dq.size),
                "dq_ref_mean": float(dq.mean()) if dq.size else float("nan"),
                "dq_ref_median": float(np.median(dq)) if dq.size else float("nan"),
                "dq_ref_p95": float(np.percentile(dq, 95)) if dq.size else float("nan"),
                "dq_ref_max": float(dq.max()) if dq.size else float("nan"),
                "dq_ref_change_rate": (
                    float((dq > DQ_CHANGE_TOL).mean()) if dq.size else float("nan")
                ),
            }
        )
    return out


def objective_totals(q: np.ndarray, inst: Instance) -> dict[str, float]:
    """决策组 + 非决策组的总成本/排放，用于描述性报告（元/天、kg CO2e/天、m2/天）。"""
    coeff = inst.objective_coeff[0]
    decided = coeff @ np.asarray(q, dtype=float)
    return {name: float(decided[i] + inst.objective_offset[i]) for i, name in enumerate(OBJECTIVES)}
