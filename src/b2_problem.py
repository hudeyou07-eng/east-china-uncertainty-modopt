"""B2 决策问题的装配：把冻结合同翻译成求解器要的张量。

**职责边界**：本模块只负责「读合同 → 建张量」，不做插补、不生成场景、不求解、不评估。
场景由 ``src/b2_scenarios.py`` 提供，求解由 ``src/robust_modopt.py`` 提供，
真值评估由 ``src/b2_evaluate.py`` 提供。

**决策变量**：K 个食物组的每日摄入量（g/day），组集合由
``group_audit.csv`` 的 ``include == 1`` 决定，不写死。

**目标**（L = 3，全部折算到「每日支出/排放」）：

===========  ==========================================
cost          ``Σ price_cny_kg / 1000 * q``    元/天
ghg           ``Σ ghg_per_kg / 1000 * q``      kg CO2e/天
land          ``Σ land_per_kg / 1000 * q``     m2/天
===========  ==========================================

**营养约束**（J = 11 硬营养素）：系数 ``value_per_kg / 1000``，上下界来自
``data/input/external/nutrient_bounds.csv``。该文件**必须存在**，
缺失时直接抛错——营养需求边界是 D3 的核心，不允许静默默认。

**联合约束**：``decision_bounds.csv`` 中 ``bound_type == "joint"`` 的行
（如 CDG 的 ``G05+G06 ∈ [40, 75]``）无法用逐组 box bound 表达，
转为 ``extra_constraints`` 传给求解器。仅当**全部成员组都在决策集内**时才施加；
成员不全必须整条跳过，绝不能退化成对单个成员的约束。

**非决策组的基线偏移（关键）**：模型只优化 K 个纳入组，其余 12−K 个组的摄入量
**固定在基线**，其营养与成本贡献作为常数项移到约束右侧：

.. math::

    \\sum_{k \\in K} n_{jk} q_k \\;+\\; \\underbrace{\\sum_{g \\notin K} n_{jg} b_g}_{\\text{offset}_j}
    \\;\\in\\; [\\ell_j, u_j]

这不是可选的技巧，而是必需的口径。**不加偏移则问题不可行**：仅靠蛋类/禽肉/红肉/蔬菜
四组，能量最多 4937 kJ（需 7520）、碳水 73 g（需 250）、钙 168 mg（需 800）、
硫胺素 0.82 mg（需 1.3）——因为主食（G04）、奶类（G01）、食用油（G11）都不在决策集内。
一个家庭并不会因为这四组被优化就停止吃米饭。

约束右侧因此变为 ``ℓ_j − offset_j`` 与 ``u_j − offset_j``，可能为负，属正常。

**已知简化**（必须随结果报告）：

1. 价格与基线取该省 2016–2024 的**跨年均值**，因为 ``decision_bounds`` 只到
   省×情景、没有年份维度。用均值会让「年度波动」与「缺失不确定性」混在一起。
2. 营养与环境系数是**全国组级**，没有省间差异（源表本身如此）。
3. 目标权重 ``cost 0.5 / ghg 0.25 / land 0.25`` 是占位值，需作者裁定；
   Plan B3 的 A6 正是「原权重 vs 等权」的消融，届时会替换。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

from src.ontology import HARD_NUTRIENTS

# 可达区间 LP 的容差。HiGHS 对 4 变量小问题精度在 1e-9 量级，1e-7 足够区分
# 「刚好卡在边界」与「差一点点」。
_REACH_TOL = 1e-7

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
EXTERNAL = ROOT / "data" / "input" / "external"

OBJECTIVES = ("cost", "ghg", "land")
DEFAULT_OBJECTIVE_WEIGHTS = {"cost": 0.5, "ghg": 0.25, "land": 0.25}
EPSILON_DEFAULT = 0.05


def _lp_rows(
    extra: list[tuple[np.ndarray, float, float]] | None,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """把 ``(coeff, lower, upper)`` 形式的联合约束转成 ``A_ub x <= b_ub``。"""
    rows: list[np.ndarray] = []
    rhs: list[float] = []
    for coeff, lo, hi in extra or ():
        coeff = np.asarray(coeff, dtype=float)
        if np.isfinite(lo):
            rows.append(-coeff)
            rhs.append(-float(lo))
        if np.isfinite(hi):
            rows.append(coeff)
            rhs.append(float(hi))
    if not rows:
        return None, None
    return np.vstack(rows), np.asarray(rhs, dtype=float)


def reachable_bounds(
    n_mat: np.ndarray,
    q_lower: np.ndarray,
    q_upper: np.ndarray,
    extra: list[tuple[np.ndarray, float, float]] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """在 ``box + 联合约束`` 下逐营养素求可达的 ``[min, max]``。

    **为什么不能只用角点公式**：只有 box 约束时，线性函数的最值必然在角点取得，
    ``n_mat @ (上界或下界)`` 就是精确解。但一旦存在联合约束
    （如 CDG 的 ``q_G05 + q_G06 ∈ [40, 75]``），角点通常不可行，公式会**高估**
    可达范围。

    实测后果：浙江的硫胺素在 box 下可达 0.83 mg，加上联合约束后只有 0.60 mg，
    而需求是 0.82 mg。旧预检据此判定「可操作」，把硫胺素放进机会约束，
    结果每个场景都必然违反、``z`` 全为 1，整个实例被判为求解失败——
    失败原因被错记成「优化器不行」，实际是约束集自相矛盾。

    返回 ``(low, high)``，LP 不可行时对应元素为 ``nan``。
    """
    n_mat = np.asarray(n_mat, dtype=float)
    q_lower = np.asarray(q_lower, dtype=float)
    q_upper = np.asarray(q_upper, dtype=float)
    j_count = n_mat.shape[0]

    a_ub, b_ub = _lp_rows(extra)
    if a_ub is None:
        # 快路径：无联合约束，角点即最优。
        q_at_min = np.where(n_mat >= 0, q_lower[None, :], q_upper[None, :])
        q_at_max = np.where(n_mat >= 0, q_upper[None, :], q_lower[None, :])
        return (n_mat * q_at_min).sum(axis=1), (n_mat * q_at_max).sum(axis=1)

    from scipy.optimize import linprog

    bounds = list(zip(q_lower.tolist(), q_upper.tolist()))
    low = np.full(j_count, np.nan)
    high = np.full(j_count, np.nan)
    for j in range(j_count):
        row = n_mat[j]
        r_min = linprog(row, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method="highs")
        if r_min.success:
            low[j] = float(r_min.fun)
        r_max = linprog(-row, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method="highs")
        if r_max.success:
            high[j] = float(-r_max.fun)
    return low, high


def minimal_conflict_set(
    n_mat: np.ndarray,
    q_lower: np.ndarray,
    q_upper: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    extra: list[tuple[np.ndarray, float, float]] | None = None,
    names: tuple[str, ...] | None = None,
) -> list[int] | None:
    """当硬约束整体不可行时，贪心求一个**近似最小**的冲突营养素集合。

    单个营养素各自可达 ≠ 同时可达。山东就是这种情形：碳水上界与硒下界单独看
    都成立，合在一起却无解。逐项预检抓不到这种冲突，只能靠整体可行性判断。

    返回造成不可行的营养素下标列表；若整体可行返回 ``None``。
    注意这是**近似**最小集（贪心删除，非 IIS 精确算法），足以定位问题，
    但不应写成「最小不可行子集」的严格结论。
    """
    from scipy.optimize import linprog

    n_mat = np.asarray(n_mat, dtype=float)
    a_ub, b_ub = _lp_rows(extra)
    bounds = list(zip(np.asarray(q_lower, float).tolist(), np.asarray(q_upper, float).tolist()))

    def feasible(keep: list[int]) -> bool:
        rows = [] if a_ub is None else [a_ub]
        rhs = [] if b_ub is None else [b_ub]
        for j in keep:
            if np.isfinite(lower[j]):
                rows.append(-n_mat[j][None, :])
                rhs.append(np.array([-float(lower[j])]))
            if np.isfinite(upper[j]):
                rows.append(n_mat[j][None, :])
                rhs.append(np.array([float(upper[j])]))
        a = np.vstack(rows) if rows else None
        b = np.concatenate(rhs) if rhs else None
        res = linprog(
            np.zeros(n_mat.shape[1]), A_ub=a, b_ub=b, bounds=bounds, method="highs"
        )
        return bool(res.success)

    keep = list(range(n_mat.shape[0]))
    if feasible(keep):
        return None
    for j in list(keep):
        trial = [k for k in keep if k != j]
        if not feasible(trial):
            keep = trial
    return keep


@dataclass(frozen=True)
class Instance:
    """一个 (省, 情景) 决策实例。场景维度由外部传入。"""

    province: str
    scenario: str
    groups: tuple[str, ...]
    nutrients: tuple[str, ...]
    objective_coeff: np.ndarray  # [S, L, K]
    nutrient_coeff: np.ndarray  # [S, J, K]
    nutrient_lower: np.ndarray  # [J] 已扣除非决策组偏移的生效下界（求解器用）
    nutrient_upper: np.ndarray  # [J] 已扣除非决策组偏移的生效上界（求解器用）
    nutrient_lower_raw: np.ndarray  # [J] 原始每日下界（真值评估用）
    nutrient_upper_raw: np.ndarray  # [J] 原始每日上界（真值评估用）
    q_lower: np.ndarray  # [K]
    q_upper: np.ndarray  # [K]
    objective_weights: np.ndarray  # [L]
    baseline: np.ndarray  # [K] g/day，用于方向判定
    nutrient_offset: np.ndarray  # [J] 非决策组在基线下贡献的营养量
    objective_offset: np.ndarray  # [L] 非决策组在基线下贡献的成本/排放
    offset_missing: tuple[tuple[str, str], ...] = ()  # 因系数缺失而未计入的 (营养素, 组)
    active_mask: np.ndarray | None = None  # [J] 进入机会约束的营养素；None 表示全部
    non_actionable: tuple[tuple[str, str], ...] = ()  # (营养素, 原因)
    extra_constraints: list[tuple[np.ndarray, float, float]] = field(default_factory=list)
    epsilon: float = EPSILON_DEFAULT
    # 硬约束（box + 联合 + 全部营养素）整体是否可行。False 时 conflict_set 给出
    # 近似最小冲突集——这类实例无论用什么方法都解不出来，必须与「优化器失败」区分。
    hard_feasible: bool = True
    conflict_set: tuple[str, ...] = ()

    @property
    def k_count(self) -> int:
        return len(self.groups)

    def with_prices(self, prices: np.ndarray) -> "Instance":
        """只替换成本行的价格（元/kg），其余全部不变。

        用于价格敏感性扫描：不必重新装配整个实例（省掉 groupby 与可达性预检）。
        注意只改 ``objective_coeff[:, 0, :]``——ghg/land 是全国系数，与价格无关。
        """
        prices = np.asarray(prices, dtype=float)
        if prices.shape != (self.k_count,):
            raise ValueError(f"价格向量长度应为 {self.k_count}，实际 {prices.shape}")
        if np.any(~np.isfinite(prices)) or np.any(prices <= 0):
            raise ValueError("价格必须为有限正数")
        coeff = np.array(self.objective_coeff, dtype=float, copy=True)
        coeff[:, 0, :] = prices / 1000.0
        return replace(self, objective_coeff=coeff)

    def with_scenarios(
        self, objective_coeff: np.ndarray, nutrient_coeff: np.ndarray
    ) -> "Instance":
        """替换场景张量，其余（边界、权重、基线）保持不变。"""
        objective_coeff = np.asarray(objective_coeff, dtype=float)
        nutrient_coeff = np.asarray(nutrient_coeff, dtype=float)
        if objective_coeff.ndim != 3 or objective_coeff.shape[1:] != (len(OBJECTIVES), self.k_count):
            raise ValueError(f"objective_coeff 形状应为 [S,{len(OBJECTIVES)},{self.k_count}]")
        if nutrient_coeff.ndim != 3 or nutrient_coeff.shape[1:] != (len(self.nutrients), self.k_count):
            raise ValueError(f"nutrient_coeff 形状应为 [S,{len(self.nutrients)},{self.k_count}]")
        if objective_coeff.shape[0] != nutrient_coeff.shape[0]:
            raise ValueError("目标与营养的场景数不一致")
        return Instance(
            province=self.province,
            scenario=self.scenario,
            groups=self.groups,
            nutrients=self.nutrients,
            objective_coeff=objective_coeff,
            nutrient_coeff=nutrient_coeff,
            nutrient_lower=self.nutrient_lower,
            nutrient_upper=self.nutrient_upper,
            nutrient_lower_raw=self.nutrient_lower_raw,
            nutrient_upper_raw=self.nutrient_upper_raw,
            q_lower=self.q_lower,
            q_upper=self.q_upper,
            objective_weights=self.objective_weights,
            baseline=self.baseline,
            nutrient_offset=self.nutrient_offset,
            objective_offset=self.objective_offset,
            offset_missing=self.offset_missing,
            active_mask=self.active_mask,
            non_actionable=self.non_actionable,
            extra_constraints=self.extra_constraints,
            epsilon=self.epsilon,
            hard_feasible=self.hard_feasible,
            conflict_set=self.conflict_set,
        )


# 边界门口径 → 审计表。契约数据（价格/营养/基线/边界/环境）覆盖全部 12 组，
# 与口径无关；口径只决定 group_audit.csv 里哪些组 include=1。
# 因此切换 K 只需换审计表，不需要复制整套 processed 数据（实测其余 22 个文件逐字节相同）。
SCOPE_AUDITS = {
    "k4_official": "group_audit.csv",              # 正式：trace=True, c=1.0  → K=4
    "k6_price": "group_audit_trace_c0.95.csv",     # trace=True, c=0.95       → K=6（+G04 +G07）
    "k3_prereg": "group_audit_k3_strict.csv",      # 预注册：trace=False, c=1.0 → K=3
    "k5_notrace": "group_audit_notrace_c0.95.csv", # trace=False, c=0.95      → K=5（+G04）
}

DEFAULT_SCOPE = "k4_official"


class Contract:
    """冻结的 B2 数据合同。加载后所有取数都走这里，不再回头读 CSV。"""

    def __init__(
        self,
        groups: tuple[str, ...],
        nutrients: tuple[str, ...],
        price: pd.DataFrame,
        nutrient: pd.DataFrame,
        env: pd.DataFrame,
        baseline: pd.DataFrame,
        bounds: pd.DataFrame,
        nutrient_bounds: pd.DataFrame,
    ) -> None:
        self.groups = groups
        self.nutrients = nutrients
        self._price = price
        self._nutrient = nutrient
        self._env = env
        self._baseline = baseline
        self._bounds = bounds
        self._nutrient_bounds = nutrient_bounds

    @classmethod
    def load(
        cls,
        processed: Path = PROCESSED,
        external: Path = EXTERNAL,
        audit_file: str = "group_audit.csv",
    ) -> "Contract":
        """装配契约。

        ``audit_file`` 指定用哪张审计表决定入组集合（见 :data:`SCOPE_AUDITS`）。
        默认仍是 ``group_audit.csv``，行为与旧版一致。
        """
        audit = pd.read_csv(processed / audit_file, encoding="utf-8-sig")
        included = audit.loc[audit["include"].astype(bool), "group_id"].tolist()
        if not included:
            raise ValueError("group_audit.csv 中没有任何 include=1 的组")
        groups = tuple(sorted(included))

        nut = pd.read_csv(processed / "nutrients.csv", encoding="utf-8-sig")
        nutrients = tuple(n for n in HARD_NUTRIENTS if n in set(nut["nutrient"]))
        missing = sorted(set(HARD_NUTRIENTS) - set(nutrients))
        if missing:
            raise ValueError(f"nutrients.csv 缺硬营养素 {missing}")

        bounds_path = external / "nutrient_bounds.csv"
        if not bounds_path.exists():
            raise FileNotFoundError(
                f"缺营养素需求边界 {bounds_path}。D3 的联合营养机会约束依赖它，"
                "不允许静默默认。请补齐后再跑。"
            )
        nutrient_bounds = pd.read_csv(bounds_path, encoding="utf-8-sig")
        absent = sorted(set(nutrients) - set(nutrient_bounds["nutrient"]))
        if absent:
            raise ValueError(f"nutrient_bounds.csv 缺 {absent} 的每日边界")

        return cls(
            groups=groups,
            nutrients=nutrients,
            price=pd.read_csv(processed / "group_prices.csv", encoding="utf-8-sig"),
            nutrient=nut,
            env=pd.read_csv(processed / "environment.csv", encoding="utf-8-sig"),
            baseline=pd.read_csv(processed / "baseline_consumption.csv", encoding="utf-8-sig"),
            bounds=pd.read_csv(processed / "decision_bounds.csv", encoding="utf-8-sig"),
            nutrient_bounds=nutrient_bounds,
        )

    @classmethod
    def load_scope(
        cls, scope: str, processed: Path = PROCESSED, external: Path = EXTERNAL
    ) -> "Contract":
        """按口径名装配契约（``k4_official`` / ``k6_price`` / ``k3_prereg`` / ``k5_notrace``）。"""
        if scope not in SCOPE_AUDITS:
            raise ValueError(f"未知口径 {scope}，可选：{sorted(SCOPE_AUDITS)}")
        return cls.load(processed=processed, external=external, audit_file=SCOPE_AUDITS[scope])

    # ---- 系数面板 -------------------------------------------------------

    def price_panel(self) -> pd.DataFrame:
        """省 × 组的跨年均价（元/kg）。"""
        sub = self._price[self._price["group_id"].isin(self.groups)]
        if sub.empty:
            raise ValueError("group_prices.csv 中没有任何决策组的价格")
        return (
            sub.groupby(["province", "group_id"], as_index=False)["price_cny_kg"]
            .mean()
            .pivot(index="province", columns="group_id", values="price_cny_kg")
            .reindex(columns=list(self.groups))
        )

    def pooled_price(
        self,
        provinces: list[str] | None = None,
        panel: pd.DataFrame | None = None,
    ) -> np.ndarray:
        """跨省合并均价（元/kg），顺序同 ``self.groups``。

        ``provinces`` 显式指定参与平均的省份集合。**必须与调用方的决策省集合一致**：
        B2 的 D0 用 ``price_panel().reindex(provinces).mean(axis=0)``（只含决策省），
        而 :meth:`instance` 的 ``price_mode="pooled"`` 用全表均值（含被排除的省）。
        两者在安徽可差到 1 个顶点（见 CHANGELOG §25.9 更正三）。

        ``panel`` 可传入已施加遮蔽位移的插补面板（省 × 组），
        避免调用方在「合并价」上再算一遍口径。

        历史上「合并价」在三处各算一遍，口径不一致导致过诊断结论错误；
        新增本方法作为唯一入口，新代码一律走这里。
        """
        if panel is None:
            panel = self.price_panel()
        if provinces is not None:
            missing = [p for p in provinces if p not in panel.index]
            if missing:
                raise ValueError(f"价格面板缺省份 {missing}")
            panel = panel.loc[list(provinces)]
        return panel.mean(axis=0, skipna=True).to_numpy(dtype=float)

    def nutrient_panel(self) -> pd.DataFrame:
        sub = self._nutrient[self._nutrient["group_id"].isin(self.groups)]
        return sub.pivot(index="nutrient", columns="group_id", values="value_per_kg").reindex(
            index=list(self.nutrients), columns=list(self.groups)
        )

    def all_groups(self) -> list[str]:
        return sorted(self._nutrient["group_id"].unique().tolist())

    def nutrient_panel_all(self) -> pd.DataFrame:
        return self._nutrient.pivot(
            index="nutrient", columns="group_id", values="value_per_kg"
        ).reindex(index=list(self.nutrients))

    def baseline_all(self, province: str) -> pd.Series:
        sub = self._baseline[self._baseline["province"].eq(province)]
        return sub.groupby("group_id")["value_g_day"].mean()

    def env_panel(self) -> dict[str, pd.DataFrame]:
        sub = self._env[
            self._env["group_id"].isin(self.groups) & self._env["dataset"].eq("global_pn")
        ]
        out = {}
        for impact in ("ghg", "land"):
            block = sub[sub["impact"].eq(impact)]
            if block.empty:
                raise ValueError(f"environment.csv 缺主口径 {impact}")
            out[impact] = (
                block.set_index("group_id")["value_per_kg"]
                .reindex(list(self.groups))
                .to_frame()
                .T
            )
        return out

    def baseline_vector(self, province: str) -> np.ndarray:
        sub = self._baseline[
            self._baseline["province"].eq(province) & self._baseline["group_id"].isin(self.groups)
        ]
        if sub.empty:
            raise ValueError(f"baseline_consumption.csv 缺省份 {province}")
        vec = sub.groupby("group_id")["value_g_day"].mean().reindex(list(self.groups))
        if vec.isna().any():
            raise ValueError(f"省份 {province} 的基线缺组 {vec[vec.isna()].index.tolist()}")
        return vec.to_numpy(dtype=float)

    def intake_bounds(self, province: str, scenario: str) -> tuple[np.ndarray, list]:
        sub = self._bounds[
            self._bounds["province"].eq(province) & self._bounds["scenario"].eq(scenario)
        ]
        if sub.empty:
            raise ValueError(f"decision_bounds.csv 缺 {province}/{scenario}")

        single = sub[sub["bound_type"].eq("single")].set_index("group_id")
        lower = np.zeros(len(self.groups))
        upper = np.full(len(self.groups), np.inf)
        for i, gid in enumerate(self.groups):
            if gid not in single.index:
                raise ValueError(f"{province}/{scenario} 缺单组边界 {gid}")
            row = single.loc[gid]
            lower[i] = float(row["lower_g_day"])
            upper[i] = float(row["upper_g_day"])

        extra: list[tuple[np.ndarray, float, float]] = []
        for _, row in sub[sub["bound_type"].eq("joint")].iterrows():
            members = [m for m in str(row["group_id"]).split("+") if m]
            if not set(members).issubset(set(self.groups)):
                # 成员不全：整条跳过，绝不退化为单组约束
                continue
            coeff = np.zeros(len(self.groups))
            for m in members:
                coeff[self.groups.index(m)] = 1.0
            extra.append((coeff, float(row["lower_g_day"]), float(row["upper_g_day"])))
        return lower, upper, extra

    def nutrient_limits(self, basis: str = "rni") -> tuple[np.ndarray, np.ndarray]:
        """返回营养素的 (下界, 上界) 数组。

        ``basis="rni"`` 用 ``lower_per_day``（默认，预注册口径）；
        ``basis="ear"`` 优先用 ``ear_per_day``，该列为空时（能量/AMDR/蛋白质）
        回退到 ``lower_per_day`` 并在 ``bounds_basis_fallback`` 中记录。

        RNI 是**个体覆盖率**指标（RNI = EAR + 2SD，覆盖 97.5% 个体），
        拿它当人群均值硬下界等于要求「人人达标」；EAR 才是人群评估的 cut-point。
        两者的差异会直接决定可行域是否非空，故必须可切换、可审计。
        """
        if basis not in {"rni", "ear"}:
            raise ValueError(f"未知的边界口径 {basis!r}，只支持 'rni' 或 'ear'")
        idx = self._nutrient_bounds.set_index("nutrient").reindex(list(self.nutrients))
        lower = idx["lower_per_day"].to_numpy(dtype=float)
        upper = idx["upper_per_day"].to_numpy(dtype=float)
        upper = np.where(np.isnan(upper), np.inf, upper)

        if basis == "ear" and "ear_per_day" in idx.columns:
            ear = idx["ear_per_day"].to_numpy(dtype=float)
            has_ear = ~np.isnan(ear)
            lower = np.where(has_ear, ear, lower)

        if not np.isfinite(lower).all():
            raise ValueError("nutrient_bounds.csv 存在非有限的下界")
        if np.any(lower > upper):
            raise ValueError("nutrient_bounds.csv 存在 lower > upper")
        return lower, upper

    def bounds_basis_fallback(self, basis: str = "ear") -> list[str]:
        """在 ``basis="ear"`` 下没有 EAR、只能回退到 RNI/AMDR 的营养素。"""
        idx = self._nutrient_bounds.set_index("nutrient").reindex(list(self.nutrients))
        if "ear_per_day" not in idx.columns:
            return list(self.nutrients)
        ear = idx["ear_per_day"].to_numpy(dtype=float)
        return [n for n, v in zip(self.nutrients, ear) if np.isnan(v)]

    def skipped_joint(self, province: str, scenario: str) -> list[str]:
        """因成员不全被跳过的联合约束，供结果标注。"""
        sub = self._bounds[
            self._bounds["province"].eq(province)
            & self._bounds["scenario"].eq(scenario)
            & self._bounds["bound_type"].eq("joint")
        ]
        out = []
        for _, row in sub.iterrows():
            members = [m for m in str(row["group_id"]).split("+") if m]
            if not set(members).issubset(set(self.groups)):
                out.append(str(row["group_id"]))
        return out

    # ---- 装配 -----------------------------------------------------------

    def instance(
        self,
        province: str,
        scenario: str,
        epsilon: float = EPSILON_DEFAULT,
        objective_weights: dict[str, float] | None = None,
        price_mode: str = "province",
        bounds_basis: str = "rni",
        price_override: np.ndarray | None = None,
    ) -> Instance:
        """装配一个实例。

        ``price_mode="province"`` 用该省价格；``"pooled"`` 用跨省合并均值，
        用于模拟 D0 的「均值填充」——遮蔽后缺失格被总体均值替换，
        省份信息丢失。两者价格不同，D0 与 D1 因此不会退化为同一个解。

        ``bounds_basis`` 选择营养下界的口径：``"rni"``（默认，预注册）
        或 ``"ear"``（人群均值参照，见 :meth:`nutrient_limits`）。

        ``price_override`` 直接给定元/kg 的价格向量（长度 = K，顺序同
        ``self.groups``），优先于 ``price_mode``。用于 B2 的遮蔽协议：
        把「基于某次插补结果的价格」装配成决策实例，而不改动正式合同。
        """
        panel = self.price_panel()
        if price_override is not None:
            prices = np.asarray(price_override, dtype=float)
            if prices.shape != (len(self.groups),):
                raise ValueError(
                    f"price_override 长度应为 {len(self.groups)}（组顺序 {list(self.groups)}），"
                    f"实际 {prices.shape}"
                )
        elif price_mode == "province":
            if province not in panel.index:
                raise ValueError(f"价格面板缺省份 {province}")
            prices = panel.loc[province].to_numpy(dtype=float)
        elif price_mode == "pooled":
            prices = panel.mean(axis=0, skipna=True).to_numpy(dtype=float)
        else:
            raise ValueError(f"未知 price_mode: {price_mode}")
        if np.isnan(prices).any():
            raise ValueError(f"省份 {province} 的价格面板有缺失组（price_mode={price_mode}）")
        if np.any(prices <= 0):
            raise ValueError(f"省份 {province} 出现非正价格：{prices}")
        nut = self.nutrient_panel().to_numpy(dtype=float)
        if np.isnan(nut).any():
            raise ValueError("营养系数面板有缺失格")
        env = self.env_panel()

        # 统一折算到「每 g」：合同是每 kg
        cost = prices / 1000.0
        ghg = env["ghg"].iloc[0].to_numpy(dtype=float) / 1000.0
        land = env["land"].iloc[0].to_numpy(dtype=float) / 1000.0
        if np.isnan(ghg).any() or np.isnan(land).any():
            raise ValueError("环境系数有缺失组")

        coeff = np.stack([cost, ghg, land], axis=0)[None, :, :]  # [1, L, K]
        nutrient_coeff = (nut / 1000.0)[None, :, :]  # [1, J, K]

        lower, upper, extra = self.intake_bounds(province, scenario)
        n_lower, n_upper = self.nutrient_limits(basis=bounds_basis)

        # 非决策组固定在基线，其营养贡献移到约束右侧
        non_decided = [g for g in self.all_groups() if g not in self.groups]
        n_all = self.nutrient_panel_all()
        b_all = self.baseline_all(province)
        offset = np.zeros(len(self.nutrients))
        missing: list[tuple[str, str]] = []
        for j, nut_name in enumerate(self.nutrients):
            total = 0.0
            for g in non_decided:
                if g not in n_all.columns:
                    missing.append((nut_name, g))
                    continue
                value = n_all.at[nut_name, g]
                if pd.isna(value):
                    missing.append((nut_name, g))
                    continue
                total += float(value) / 1000.0 * float(b_all.get(g, 0.0))
            offset[j] = total
        effective_lower = n_lower - offset
        effective_upper = np.where(np.isfinite(n_upper), n_upper - offset, np.inf)

        # 可操作性预检：若某个营养素在**可行决策域**内无法进入 [ℓ,u]，
        # 则它在机会约束里对每个场景都必然违反，z 全为 1，
        # 使 z_sum <= floor(eps*S) 直接不可行——这与决策质量无关，是约束集本身的问题。
        # 这类营养素不进入机会约束，但**仍参与真值评估**，两个口径都报告。
        #
        # 关键：可行决策域是 box ∩ 联合约束，不是 box。用角点公式会高估可达范围，
        # 把本该排除的营养素误判为可操作（详见 reachable_bounds 的文档）。
        n_mat = nut / 1000.0  # [J, K]
        feasible_lo, feasible_hi = reachable_bounds(n_mat, lower, upper, extra)
        if np.isnan(feasible_lo).any() or np.isnan(feasible_hi).any():
            raise ValueError(
                f"{province}/{scenario}：决策边界与联合约束的交集为空，"
                f"没有任何 q 同时满足组内上下界与 {len(extra)} 条联合约束"
            )
        action_lo = feasible_hi >= effective_lower - 1e-9
        action_hi = feasible_lo <= effective_upper + 1e-9
        active = action_lo & action_hi
        non_actionable: list[tuple[str, str]] = []
        for j, nut_name in enumerate(self.nutrients):
            if action_lo[j] and action_hi[j]:
                continue
            reason = []
            if not action_lo[j]:
                reason.append(f"最大可达 {feasible_hi[j]:.4g} < 下界 {effective_lower[j]:.4g}")
            if not action_hi[j]:
                reason.append(f"最小可达 {feasible_lo[j]:.4g} > 上界 {effective_upper[j]:.4g}")
            non_actionable.append((nut_name, "；".join(reason)))
        if not active.any():
            raise ValueError("没有任何营养素能被决策集影响，机会约束无意义")

        # 逐项可达 ≠ 同时可达。整体可行性单独判一次，否则「约束自相矛盾」
        # 会被记成「求解器失败」，混淆两类完全不同的失败原因。
        #
        # 判定范围只取 **active** 营养素：非可操作项本来就不进求解器，
        # 把它们算进来只会重复报告同一件事（实测会让 7 省全部报「硫胺素」）。
        # 这里要回答的是「送进求解器的这套约束是否自洽」。
        check_lower = np.where(active, effective_lower, -np.inf)
        check_upper = np.where(active, effective_upper, np.inf)
        conflict_idx = minimal_conflict_set(
            n_mat, lower, upper, check_lower, check_upper, extra
        )
        hard_feasible = conflict_idx is None
        conflict_set = () if hard_feasible else tuple(self.nutrients[j] for j in conflict_idx)

        # 非决策组的成本/排放：优化中是常数（不影响 argmin），仅用于描述性汇总
        obj_offset = np.zeros(len(OBJECTIVES))
        price_all = self._price.groupby(["province", "group_id"])["price_cny_kg"].mean()
        if province in price_all.index.get_level_values(0):
            pv = price_all.loc[province]
            for g in non_decided:
                if g in pv.index and not np.isnan(pv[g]):
                    obj_offset[0] += float(pv[g]) / 1000.0 * float(b_all.get(g, 0.0))
        env_all = self._env[self._env["dataset"].eq("global_pn")]
        for idx, impact in enumerate(("ghg", "land"), start=1):
            row = env_all[env_all["impact"].eq(impact)].set_index("group_id")["value_per_kg"]
            for g in non_decided:
                if g in row.index and not np.isnan(row[g]):
                    obj_offset[idx] += float(row[g]) / 1000.0 * float(b_all.get(g, 0.0))

        w = dict(DEFAULT_OBJECTIVE_WEIGHTS)
        if objective_weights:
            w.update(objective_weights)
        weights = np.array([w[o] for o in OBJECTIVES], dtype=float)
        if np.any(weights <= 0):
            raise ValueError("目标权重必须为正")

        return Instance(
            province=province,
            scenario=scenario,
            groups=self.groups,
            nutrients=self.nutrients,
            objective_coeff=coeff,
            nutrient_coeff=nutrient_coeff,
            nutrient_lower=effective_lower,
            nutrient_upper=effective_upper,
            nutrient_lower_raw=n_lower,
            nutrient_upper_raw=n_upper,
            q_lower=lower,
            q_upper=upper,
            objective_weights=weights,
            baseline=self.baseline_vector(province),
            nutrient_offset=offset,
            objective_offset=obj_offset,
            offset_missing=tuple(sorted(set(missing))),
            active_mask=active,
            non_actionable=tuple(non_actionable),
            extra_constraints=extra,
            epsilon=epsilon,
            hard_feasible=hard_feasible,
            conflict_set=conflict_set,
        )

    def provinces(self) -> list[str]:
        return sorted(self._bounds["province"].unique().tolist())

    def baseline_adequacy(self, province: str) -> dict[str, dict[str, float | bool]]:
        """诊断：该省**现状膳食**（12 组全按基线）是否满足各营养素的原始边界。

        这是判断「营养边界定得合不合理」的第一道检查。若基线本身就不达标，
        把该边界当硬下界会让问题不可行，或让所有方法的可行率同为 0（无区分度）。
        实测钙与硫胺素在全部省份都不达标，根因是用了 RNI 而非 EAR——
        RNI 覆盖 97.5% 个体，不能当作人群均值的硬下界。
        """
        n_all = self.nutrient_panel_all()
        b_all = self.baseline_all(province)
        lo, hi = self.nutrient_limits()
        out: dict[str, dict[str, float | bool]] = {}
        for j, nut in enumerate(self.nutrients):
            total = 0.0
            skipped = []
            for g in n_all.columns:
                value = n_all.at[nut, g]
                if pd.isna(value):
                    skipped.append(g)
                    continue
                total += float(value) / 1000.0 * float(b_all.get(g, 0.0))
            out[nut] = {
                "baseline": total,
                "lower": float(lo[j]),
                "upper": float(hi[j]) if np.isfinite(hi[j]) else float("nan"),
                "meets_lower": bool(total >= lo[j]),
                "within_upper": bool(not np.isfinite(hi[j]) or total <= hi[j]),
                "groups_without_coefficient": skipped,
            }
        return out

    def complete_provinces(self) -> tuple[list[str], dict[str, list[str]]]:
        """返回价格面板对**全部决策组**都无缺失的省份，以及被排除者的缺组明细。

        这不是可选的过滤：价格是目标函数系数，缺一组就无法装配实例。
        实测浙江的禽肉（G05）在 2016–2024 全部 9 年**零观测**，
        因此浙江无法进入 K=4 模型（它的禽肉价格根本没有数据）。
        """
        panel = self.price_panel()
        ok, excluded = [], {}
        for prov in panel.index:
            gaps = [g for g in self.groups if pd.isna(panel.at[prov, g])]
            if gaps:
                excluded[str(prov)] = gaps
            else:
                ok.append(str(prov))
        return ok, excluded

    def scenarios(self) -> list[str]:
        return sorted(self._bounds["scenario"].unique().tolist())
