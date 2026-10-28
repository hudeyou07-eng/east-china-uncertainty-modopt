"""B2 场景生成：占位噪声 与 B1 后验 两条来源。

本模块提供**两种**场景来源，用途不同，不能混用：

``placeholder_scenarios``
    在点估计上乘对数正态扰动（``cv_price`` 默认 5%）。只用于打通
    「场景 → 求解 → 真值评估」链路，**不能作为 C2 证据**。

``posterior_scenarios``
    从 B1 正式批次（``B1_formal_withmice_20261023_124906``）的
    ``cell_predictions.csv`` 抽**经验残差**，作为价格后验。
    这是 R200–R203 转 DONE 所需的那条通路。

## 为什么用「残差重抽样」而不是拟合一个参数分布

B1 的残差**不是正态、也不是零均值**：实测 ``hierarchical_rw`` 在
``single_cell`` 下，水产品系统低估 16%（std 0.38）、猪肉高估 8%（std 0.30）、
禽类高估 10%（std 0.22）、蔬菜低估 8%（std 0.19）、鸡蛋低估 2%（std 0.13）。
用单个 ``cv`` 描述这套结构会同时丢掉三件对决策有影响的东西：

1. **组间异质**：蔬菜的离散度是鸡蛋的 1.5 倍，水产品是 3 倍；
2. **厚尾**：猪肉残差从 −47% 到 +73%，不是对数正态能覆盖的形态；
3. **偏态**：各组均值不同，说明插补有系统偏差。

而 CHANGELOG §24 已证明「CVaR 是否改变决策」取决于
**尾部成本方向相对均值方向的旋转角**——这个角完全由残差的组间结构决定。
用 i.i.d. 对数正态时它只有 0.4–1.1°，换成组特异性结构后升到 8–16°。

## 两个必须说清的口径

**（1）残差衡量的是「价格估计误差」，不是「未来价格波动」。**

``truth/prediction − 1`` 是插补误差。把它当作场景，问的是
「如果我们插补的价格偏了 B1 说它通常会偏的那个量，推荐膳食会变吗」。
这是**决策对价格信息质量的稳健性**，不是「未来价格会怎么走」。
两者都能叫「价格不确定性」，但答案不能互换，论文里必须写清用的是哪一个。

**（2）残差必须去均值。**

场景的均值必须等于点估计，否则 ``min E_s[c_s·q]`` 与 ``min c̄·q``
不再是同一个问题，D3 与 D1 的差异里会混进一个纯粹的平移偏差。
故先减去组内均值，抽样后再归一化到均值 1（见 ``_renormalize``）。

## 已知局限（写论文时要声明）

* **跨省池化**：每个 (省, 组) 的残差样本量只有 5–13，太薄，故按**组**池化
  所有省份。省际误差结构差异没有被捕捉。
* **多品类组**：G06 由猪/牛/羊三个品类加权而成，这里把三者的残差混在一起，
  **忽略了组内加权平均的抵消效应**，故离散度**偏高**（保守方向）。
  这个偏保守的方向对本项目的结论是有利的：若高估离散度下 CVaR 仍不动，
  结论只会更强。
* **G04 只在 ``single_cell`` 下有残差**：``consecutive_years`` 与
  ``province_group`` 两种遮蔽几何没有遮蔽过粮食品类，因此那两种几何下
  无法为 G04 提供后验。``load_residual_pool`` 会显式报错，不会静默回退到占位噪声。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.b2_problem import Instance

CV_PRICE_DEFAULT = 0.05
# 默认**不扰动**营养系数（2026-10-27 作者裁定，CHANGELOG §21.6）。
#
# 食物成分表是固定的物理常数，把它当成 5% 不确定没有依据；而它的影响却极大：
# K=6 下确定性最优点落在营养下界上（零余量），5% 扰动使 19/20 个场景违反，
# 机会约束要求 190/200 场景可行，D3 直接不可行（实测失败 11/12）。
# 也就是说，扰动它会**完全掩盖**真正的不确定性来源——价格（B1 后验）。
#
# 保留这个参数是为了做敏感性对照，正式结果用 0.0。
CV_NUTRIENT_DEFAULT = 0.0

# B1 正式批次：5 折 × 20 重复 × 3 种遮蔽几何 × 4 种方法。
B1_RUN_DEFAULT = "B1_formal_withmice_20261023_124906"
# 主方法：``src/imputation.py`` 的层级随机游走，也是 B1 里标定误差最低的一个
# （R106：三种遮蔽下标定误差 0.054/0.037/0.059）。
B1_METHOD_DEFAULT = "hierarchical_rw"
# 只有 ``single_cell`` 覆盖全部 13 个品类；另外两种几何没遮蔽过粮食。
B1_MASK_DEFAULT = "single_cell"


def _lognormal(rng: np.random.Generator, point: np.ndarray, cv: float, size: int) -> np.ndarray:
    """均值保持为 ``point`` 的对数正态乘子，形状 ``[size, ...point.shape]``。"""
    if cv <= 0:
        return np.repeat(point[None, ...], size, axis=0)
    sigma = np.sqrt(np.log1p(cv * cv))
    mu = -0.5 * sigma * sigma  # 使 E[exp(N(mu,sigma))] = 1
    noise = rng.lognormal(mu, sigma, size=(size,) + point.shape)
    return point[None, ...] * noise


def placeholder_scenarios(
    inst: Instance,
    n_scenarios: int,
    seed: int,
    cv_price: float = CV_PRICE_DEFAULT,
    cv_nutrient: float = CV_NUTRIENT_DEFAULT,
) -> tuple[np.ndarray, np.ndarray]:
    """在点估计上生成对数正态场景（**占位**）。返回 ``([S,L,K], [S,J,K])``。

    ⚠️ 这里的噪声**逐组独立、逐目标独立**，与 B1 后验无关。
    它会让 CVaR 显得「无效」（目标方向只旋转 1° 量级，CHANGELOG §24.3），
    这是**扰动设计**的产物，不是决策问题的性质。正式结果用
    :func:`posterior_scenarios`。
    """
    if n_scenarios < 1:
        raise ValueError("场景数必须 >= 1")
    rng = np.random.default_rng(seed)

    point_obj = inst.objective_coeff[0]  # [L, K]
    # 只有成本（第 0 个目标）逐省变化；ghg/land 是全国系数，但仍允许场景扰动
    obj = _lognormal(rng, point_obj, cv_price, n_scenarios)

    point_nut = inst.nutrient_coeff[0]  # [J, K]
    nut = _lognormal(rng, point_nut, cv_nutrient, n_scenarios)
    return obj, nut


def deterministic(inst: Instance) -> tuple[np.ndarray, np.ndarray]:
    """单场景确定性输入（D0 / D1 用）。"""
    return inst.objective_coeff.copy(), inst.nutrient_coeff.copy()


# ---------------------------------------------------------------------------
# B1 经验残差 → 后验场景
# ---------------------------------------------------------------------------


@dataclass
class ResidualPool:
    """按组聚合的**中心化**相对残差池。

    ``by_group[group_id]`` 是一维数组，元素为 ``truth/prediction − 1`` 减去组内均值。
    长度即该组可用的 (省, 年, 折, 重复) 样本数。
    """

    by_group: dict[str, np.ndarray]
    meta: dict = field(default_factory=dict)

    def coverage(self) -> pd.DataFrame:
        """逐组的样本量与离散度，用于落盘与写论文时声明。"""
        rows = []
        for g, arr in self.by_group.items():
            rows.append(
                {
                    "group_id": g,
                    "n": int(arr.size),
                    "sd": float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
                    "min": float(arr.min()),
                    "max": float(arr.max()),
                }
            )
        return pd.DataFrame(rows).sort_values("group_id").reset_index(drop=True)


def _group_raw_to_id() -> dict[str, str]:
    """价格品类名 → 组 ID。用 ``src/ontology.py`` 的 ``price_categories`` 反查。"""
    from src.ontology import ONTOLOGY

    out: dict[str, str] = {}
    for g in ONTOLOGY:
        for cat in g["price_categories"]:
            out[str(cat)] = str(g["group_id"])
    return out


def load_residual_pool(
    run_dir: str | Path,
    method: str = B1_METHOD_DEFAULT,
    mask_type: str = B1_MASK_DEFAULT,
    groups: tuple[str, ...] | list[str] | None = None,
) -> ResidualPool:
    """从 B1 的 ``cell_predictions.csv`` 抽中心化残差池。

    参数
    ----
    run_dir
        B1 正式批次目录（需含 ``cell_predictions.csv``）。
    method
        用哪种插补方法的残差。默认 ``hierarchical_rw``。
    mask_type
        遮蔽几何。默认 ``single_cell``（唯一覆盖全部品类的几何）。
    groups
        需要覆盖的组；缺任何一组的残差都会**显式报错**，
        而不是静默回退到占位噪声——静默回退会让结果看起来是正式的。
    """
    run_dir = Path(run_dir)
    csv = run_dir / "cell_predictions.csv"
    if not csv.exists():
        raise FileNotFoundError(f"B1 预测表不存在：{csv}")

    df = pd.read_csv(csv)
    need_cols = {"mask_type", "method", "province", "group_raw", "truth", "prediction"}
    missing_cols = need_cols - set(df.columns)
    if missing_cols:
        raise ValueError(f"cell_predictions.csv 缺列：{sorted(missing_cols)}")

    sub = df[df["method"].eq(method) & df["mask_type"].eq(mask_type)].copy()
    if sub.empty:
        raise ValueError(
            f"{run_dir.name} 中没有 method={method!r} & mask_type={mask_type!r} 的行。"
            f"可用方法：{sorted(df['method'].unique())}；"
            f"可用遮蔽：{sorted(df['mask_type'].unique())}"
        )

    sub = sub[np.isfinite(sub["prediction"]) & np.isfinite(sub["truth"])]
    sub = sub[sub["prediction"] > 0]
    if sub.empty:
        raise ValueError("筛选后没有任何可用的 (truth, prediction) 对")

    mapping = _group_raw_to_id()
    sub["group_id"] = sub["group_raw"].map(mapping)
    unmapped = sorted(sub.loc[sub["group_id"].isna(), "group_raw"].unique().tolist())
    if unmapped:
        raise ValueError(f"以下价格品类在 ontology 里没有对应的组：{unmapped}")

    sub["rel"] = sub["truth"] / sub["prediction"] - 1.0

    by_group: dict[str, np.ndarray] = {}
    for gid, chunk in sub.groupby("group_id"):
        arr = chunk["rel"].to_numpy(dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size < 2:
            continue
        by_group[str(gid)] = arr - arr.mean()  # 去均值：E[1+r] = 1

    if groups is not None:
        wanted = [str(g) for g in groups]
        absent = [g for g in wanted if g not in by_group]
        if absent:
            raise ValueError(
                f"以下组在 method={method!r} / mask_type={mask_type!r} 下没有足够残差："
                f"{absent}。已覆盖：{sorted(by_group)}。"
                f"换 mask_type（只有 single_cell 覆盖全部品类）或换 method。"
            )
        by_group = {g: by_group[g] for g in wanted}

    meta = {
        "b1_run": run_dir.name,
        "method": method,
        "mask_type": mask_type,
        "n_pairs": int(len(sub)),
        "provinces": sorted(sub["province"].unique().tolist()),
        "groups": sorted(by_group),
        "note": (
            "残差 = truth/prediction − 1，已减组内均值。"
            "衡量价格估计误差，非未来价格波动。跨省池化，多品类组为混合分布（离散度偏高）"
        ),
    }
    return ResidualPool(by_group=by_group, meta=meta)


def _renormalize(mult: np.ndarray) -> np.ndarray:
    """把抽样后的乘子归一化到列均值为 1。

    保证 ``E_s[c_s] == c_point``——否则 D3 的期望目标与 D1 的确定性目标
    不是同一个函数，两者的差值里会混进一个纯平移偏差。
    """
    mean = mult.mean(axis=0)
    return mult / np.where(np.abs(mean) < 1e-12, 1.0, mean)


def posterior_scenarios(
    inst: Instance,
    n_scenarios: int,
    seed: int,
    run_dir: str | Path | None = None,
    method: str = B1_METHOD_DEFAULT,
    mask_type: str = B1_MASK_DEFAULT,
    clip: tuple[float, float] = (0.2, 5.0),
    pool: ResidualPool | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """从 B1 经验残差抽价格后验场景。返回 ``([S,L,K], [S,J,K])``。

    **只扰动成本目标（第 0 个）**，ghg/land 保持点估计不变。
    理由：残差是「价格估计误差」，把它套到全国环境系数上没有语义依据。
    这与 :func:`placeholder_scenarios`（三个目标都扰动）不同，是有意为之。

    营养系数按作者裁定不扰动（``CV_NUTRIENT_DEFAULT = 0``），返回单场景复制。

    参数
    ----
    clip
        乘子的下/上界，防止极端残差把价格压到 0 或放大到离谱。
        B1 里最极端的是乳制品（+330%），不在 K=6 决策集内，但保留护栏。
    pool
        已加载的残差池；给定则忽略 ``run_dir``，避免在循环里重复读 CSV。
    """
    if n_scenarios < 1:
        raise ValueError("场景数必须 >= 1")
    if pool is None:
        if run_dir is None:
            raise ValueError("必须提供 run_dir 或 pool")
        pool = load_residual_pool(run_dir, method=method, mask_type=mask_type, groups=inst.groups)

    missing = [g for g in inst.groups if g not in pool.by_group]
    if missing:
        raise ValueError(f"残差池缺组 {missing}（池内只有 {sorted(pool.by_group)}）")

    rng = np.random.default_rng(seed)
    k = len(inst.groups)
    mult = np.ones((n_scenarios, k), dtype=float)
    for i, g in enumerate(inst.groups):
        arr = pool.by_group[g]
        draws = rng.choice(arr, size=n_scenarios, replace=True)
        mult[:, i] = np.clip(1.0 + draws, clip[0], clip[1])
    mult = _renormalize(mult)

    point_obj = np.asarray(inst.objective_coeff[0], dtype=float)  # [L, K]
    obj = np.repeat(point_obj[None, ...], n_scenarios, axis=0)
    obj[:, 0, :] = point_obj[0][None, :] * mult  # 只改成本

    nut = np.repeat(np.asarray(inst.nutrient_coeff, dtype=float), n_scenarios, axis=0)
    return obj, nut
