"""B2 框架的最小可验证测试。

只测**机制**，不测数值结论：合同能装配、偏移让能量可行、联合约束真的生效、
无机会约束时营养确实不管、Wilson 区间与 gap 的符号语义正确。
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.b2_evaluate import objective_gap, wilson_interval, direction, flip_flags
from src.b2_problem import Contract, minimal_conflict_set, reachable_bounds
from src.robust_modopt import solve_chance_modopt


class B2ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = Contract.load()
        cls.province = cls.contract.complete_provinces()[0][0]
        cls.inst = cls.contract.instance(cls.province, "CDG")

    def test_groups_and_nutrients(self) -> None:
        self.assertEqual(self.inst.groups, ("G02", "G05", "G06", "G08"))
        self.assertEqual(len(self.inst.nutrients), 11)

    def test_shapes(self) -> None:
        k = self.inst.k_count
        self.assertEqual(self.inst.objective_coeff.shape, (1, 3, k))
        self.assertEqual(self.inst.nutrient_coeff.shape, (1, 11, k))
        self.assertEqual(self.inst.q_lower.shape, (k,))
        self.assertEqual(self.inst.nutrient_offset.shape, (11,))

    def test_offset_makes_energy_reachable(self) -> None:
        """不含偏移时能量不可达；含偏移后必须可达。这是偏移存在的唯一理由。"""
        inst = self.inst
        energy = inst.nutrients.index("能量")
        coeff = inst.nutrient_coeff[0, energy]
        without_offset = float(coeff @ inst.q_upper)
        raw_lower = inst.nutrient_lower_raw[energy]
        self.assertLess(without_offset, raw_lower, "若无偏移就够，说明偏移是多余的")
        with_offset = without_offset + inst.nutrient_offset[energy]
        self.assertGreaterEqual(with_offset, raw_lower - 1e-9)

    def test_non_actionable_are_excluded_from_active_set(self) -> None:
        inst = self.inst
        self.assertIsNotNone(inst.active_mask)
        self.assertTrue(inst.active_mask.any())
        for name, _reason in inst.non_actionable:
            self.assertFalse(inst.active_mask[inst.nutrients.index(name)])

    def test_joint_constraint_present(self) -> None:
        self.assertEqual(len(self.inst.extra_constraints), 1)
        coeff, lo, hi = self.inst.extra_constraints[0]
        self.assertAlmostEqual(float(coeff.sum()), 2.0)  # G05 + G06
        self.assertAlmostEqual(lo, 40.0)
        self.assertAlmostEqual(hi, 75.0)

    def test_all_seven_provinces_are_complete(self) -> None:
        """浙江曾因禽类（G05）9 年零观测被排除，现已由批发价桥接回退补齐。"""
        ok, excluded = self.contract.complete_provinces()
        self.assertEqual(len(ok), 7)
        self.assertIn("浙江", ok)
        self.assertEqual(excluded, {})

    def test_bridged_price_is_flagged_not_truth_eligible(self) -> None:
        """桥接值是换算值，不是实测值：必须打标，且不得进入真值参照。"""
        import pandas as pd

        from src.b2_problem import PROCESSED

        price = pd.read_csv(PROCESSED / "group_prices.csv", encoding="utf-8-sig")
        bridged = price[price["price_source"].eq("bridged")]
        self.assertGreater(len(bridged), 0)
        self.assertFalse(bridged["truth_eligible"].any(), "桥接行不得标记为 truth_eligible")

        zj = price[(price["province"].eq("浙江")) & (price["group_id"].eq("G05"))]
        self.assertTrue(zj["price_source"].eq("bridged").all())
        self.assertTrue(zj["price_cny_kg"].notna().all())

    def test_bridge_does_not_perturb_observed_provinces(self) -> None:
        """桥接只允许在「整组零观测」时回退，不得改动已冻结的省-组均值。

        **2026-10-27 修订**：G06 的主口径由「缺失品类按已观测品类归一」改为
        「缺失品类先桥接补全、再按完整结构加权」（CHANGELOG §31），
        所以 G06 的结构加权均值从 **43.92 → 47.03**。
        等权口径（`price_equal_weight`）不涉及权重，仍为 54.43，未动。
        """
        import pandas as pd

        from src.b2_problem import PROCESSED

        price = pd.read_csv(PROCESSED / "group_prices.csv", encoding="utf-8-sig")
        g06 = price[(price["group_id"].eq("G06")) & price["observed"]]
        self.assertAlmostEqual(g06["price_cny_kg"].mean(), 47.03, places=1)
        self.assertAlmostEqual(g06["price_equal_weight"].mean(), 54.43, places=1)

    def test_g06_partial_structure_uses_full_weights(self) -> None:
        """G06 缺品类时必须用完整结构加权，不能丢掉牛肉/羊肉的权重（§31）。

        回归背景：旧口径把 `pork=1.000` 当组价，权重质量损失 21.2%，
        组价低估中位 21.7%。现在 21 行用桥接补全，只有 3 行（福建）
        桥接也没有，标 `lowerbound`——它们是**下界**，不是无偏估计。
        """
        import pandas as pd

        from src.b2_problem import PROCESSED

        price = pd.read_csv(PROCESSED / "group_prices.csv", encoding="utf-8-sig")
        g06 = price[price["group_id"].eq("G06")]

        agg = g06["aggregation"].str.split("(").str[0].value_counts().to_dict()
        self.assertEqual(agg.get("structure_weighted_complete"), 27)
        self.assertEqual(agg.get("structure_weighted_bridged"), 21)
        self.assertEqual(agg.get("structure_weighted_partial_lowerbound"), 3)

        # 残留的 3 行下界必须全部在福建（其余省份桥接表都有牛肉/羊肉）
        left = g06[g06["aggregation"].str.startswith("structure_weighted_partial")]
        self.assertEqual(sorted(left["province"].unique()), ["福建"])

        # 「pork=1.000」只允许出现在显式标注的下界行上；
        # 标了 complete/bridged 的行必须是完整结构权重。
        pork_only = g06["aggregation"].str.contains("pork=1.000", regex=False)
        self.assertTrue(
            g06.loc[pork_only, "aggregation"].str.startswith(
                "structure_weighted_partial_lowerbound"
            ).all(),
            "pork=1.000 只能出现在 lowerbound 行上",
        )
        complete_or_bridged = g06["aggregation"].str.contains(
            "structure_weighted_complete|structure_weighted_bridged", regex=True
        )
        self.assertTrue(
            g06.loc[complete_or_bridged, "aggregation"]
            .str.contains("pork=0.788/beef=0.136/lamb=0.076", regex=False)
            .all(),
            "完整结构加权必须用 pork=.788/beef=.136/lamb=.076（标签按权重降序规范排序）",
        )


class ReachabilityTest(unittest.TestCase):
    """可操作性预检必须在 box ∩ 联合约束 上判，不能用 box 角点。

    用**手算可验**的两变量玩具例子，不依赖真实数据：
        q1 ∈ [0, 10], q2 ∈ [0, 10],  q1 + q2 ≤ 4
    目标营养素 = q2。
    box 角点给 max = 10；加上联合约束后真实 max = 4。
    """

    def test_joint_constraint_shrinks_reachable_range(self) -> None:
        n_mat = np.array([[0.0, 1.0]])
        q_lower = np.array([0.0, 0.0])
        q_upper = np.array([10.0, 10.0])
        box_lo, box_hi = reachable_bounds(n_mat, q_lower, q_upper, extra=None)
        self.assertAlmostEqual(float(box_hi[0]), 10.0)

        joint = [(np.array([1.0, 1.0]), -np.inf, 4.0)]
        lp_lo, lp_hi = reachable_bounds(n_mat, q_lower, q_upper, extra=joint)
        self.assertAlmostEqual(float(lp_hi[0]), 4.0, places=6)
        self.assertAlmostEqual(float(lp_lo[0]), 0.0, places=6)
        self.assertLess(float(lp_hi[0]), float(box_hi[0]))

    def test_empty_region_returns_nan(self) -> None:
        n_mat = np.array([[1.0, 0.0]])
        # q1 ≥ 8 与 q1 + q2 ≤ 4 无交集
        joint = [(np.array([1.0, 1.0]), -np.inf, 4.0)]
        lo, hi = reachable_bounds(
            n_mat, np.array([8.0, 0.0]), np.array([10.0, 10.0]), extra=joint
        )
        self.assertTrue(np.isnan(lo[0]) and np.isnan(hi[0]))

    def test_minimal_conflict_set_finds_pairwise_clash(self) -> None:
        """逐项可达但合起来不可行：x1 ≥ 9 与 x1 + x2 ≤ 4 与 x2 ≥ 0 冲突。"""
        n_mat = np.array([[1.0, 0.0], [0.0, 1.0]])
        lower = np.array([9.0, 0.0])
        upper = np.array([np.inf, np.inf])
        joint = [(np.array([1.0, 1.0]), -np.inf, 4.0)]
        idx = minimal_conflict_set(
            n_mat, np.array([0.0, 0.0]), np.array([10.0, 10.0]), lower, upper, joint
        )
        self.assertIsNotNone(idx)
        self.assertIn(0, idx)


class B2FeasibilityTest(unittest.TestCase):
    """真实合同上的可行性判定：区分「约束自相矛盾」与「优化器失败」。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = Contract.load()

    def test_zhejiang_thiamine_excluded_only_after_joint_awareness(self) -> None:
        """浙江硫胺素：box 下可达 0.83，加联合约束后仅 0.60，必须被排除。

        这条钉住的是「角点公式会高估可达范围」这个具体后果——
        旧实现把硫胺素当可操作，导致浙江整个实例被判为求解失败。
        """
        inst = self.contract.instance("浙江", "CDG")
        excluded = [name for name, _ in inst.non_actionable]
        self.assertIn("硫胺素", excluded)
        self.assertFalse(inst.active_mask[inst.nutrients.index("硫胺素")])
        self.assertTrue(inst.hard_feasible, "排除不可操作项后，浙江应当硬可行")

    def test_shandong_hard_infeasible_has_named_conflict(self) -> None:
        """山东：碳水上界与硒下界冲突，属约束集自相矛盾，不是优化器问题。"""
        inst = self.contract.instance("山东", "CDG")
        self.assertFalse(inst.hard_feasible)
        self.assertIn("碳水化合物", inst.conflict_set)
        self.assertIn("硒", inst.conflict_set)

    def test_other_provinces_are_hard_feasible(self) -> None:
        for province in ("上海", "江苏", "安徽", "江西", "浙江", "福建"):
            with self.subTest(province=province):
                inst = self.contract.instance(province, "CDG")
                self.assertTrue(inst.hard_feasible, f"{province} 不应硬不可行")
                self.assertEqual(inst.conflict_set, ())


class B2SolverMechanicsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = Contract.load()
        cls.inst = cls.contract.instance("上海", "CDG")

    def _solve(self, use_chance: bool, epsilon: float):
        mask = self.inst.active_mask
        return solve_chance_modopt(
            objective_coeff=self.inst.objective_coeff,
            nutrient_coeff=self.inst.nutrient_coeff[:, mask, :],
            nutrient_lower=self.inst.nutrient_lower[mask],
            nutrient_upper=self.inst.nutrient_upper[mask],
            q_lower=self.inst.q_lower,
            q_upper=self.inst.q_upper,
            objective_weights=self.inst.objective_weights,
            epsilon=epsilon,
            time_limit=30,
            mip_rel_gap=1e-4,
            extra_constraints=self.inst.extra_constraints,
            use_chance_constraint=use_chance,
        )

    def test_joint_bound_respected(self) -> None:
        res = self._solve(use_chance=True, epsilon=0.0)
        self.assertTrue(res.success, msg=res.message)
        g05 = self.inst.groups.index("G05")
        g06 = self.inst.groups.index("G06")
        total = float(res.q[g05] + res.q[g06])
        self.assertGreaterEqual(total, 40.0 - 1e-6)
        self.assertLessEqual(total, 75.0 + 1e-6)

    def test_without_chance_constraint_nutrition_is_ignored(self) -> None:
        """D2 的语义：没有营养约束，红肉应被压到 0（最贵且排放最高）。"""
        res = self._solve(use_chance=False, epsilon=0.0)
        self.assertTrue(res.success, msg=res.message)
        g06 = self.inst.groups.index("G06")
        self.assertLess(res.q[g06], 1e-6)


class B2EvaluateTest(unittest.TestCase):
    def test_wilson_bounds(self) -> None:
        lo, hi = wilson_interval(0, 10)
        self.assertGreaterEqual(lo, 0.0)
        self.assertLess(hi, 0.35)
        lo, hi = wilson_interval(10, 10)
        self.assertGreater(lo, 0.65)
        self.assertLessEqual(hi, 1.0)
        self.assertTrue(np.isnan(wilson_interval(0, 0)[0]))

    def test_gap_is_zero_at_reference(self) -> None:
        rng = np.random.default_rng(0)
        coeff = rng.uniform(1, 5, size=(2, 3))
        q = np.array([1.0, 2.0, 3.0])
        gap = objective_gap(q, q, coeff, np.array([0.5, 0.5]), np.zeros(3), np.full(3, 10.0))
        self.assertAlmostEqual(gap, 0.0, places=12)

    def test_direction_tolerance(self) -> None:
        q = np.array([10.5, 20.0, 30.0])
        base = np.array([10.0, 20.0, 40.0])
        d = direction(q, base, tol=1.0)
        self.assertEqual(d.tolist(), [0.0, 0.0, -1.0])

    def test_flip_flags(self) -> None:
        q = np.array([5.0, 20.0, 50.0])
        ref = np.array([10.0, 20.0, 30.0])
        base = np.array([10.0, 20.0, 30.0])
        self.assertEqual(flip_flags(q, ref, base).tolist(), [True, False, True])


if __name__ == "__main__":
    unittest.main()


class SummarizeMetricPriorityTest(unittest.TestCase):
    """指标主次：dq_ref 为主、flip_rate 为辅（CHANGELOG §26.8 裁定 4）。

    核心要钉住的是：flip_rate = 0 与 dq_ref 很大可以**同时成立**。
    若有人把 flip_rate 改回主指标，这个测试仍然通过（它只验证口径），
    但会在注释与 docstring 里留下反对理由。
    """

    def test_flip_zero_but_large_displacement(self) -> None:
        from src.b2_evaluate import summarize

        # 10 次重复：方向一个都没翻，但每次都偏离 q* 达 60 g/day
        out = summarize(
            feasible_all=[True] * 10,
            feasible_active=[True] * 10,
            flip_counts=[0] * 10,
            group_counts=[6] * 10,
            gaps=[0.01] * 10,
            dq_refs=[60.0] * 10,
        )
        self.assertEqual(out["flip_rate"], 0.0)
        self.assertAlmostEqual(out["dq_ref_median"], 60.0)
        self.assertAlmostEqual(out["dq_ref_change_rate"], 1.0)

    def test_change_rate_uses_threshold(self) -> None:
        from src.b2_evaluate import summarize

        out = summarize(
            feasible_all=[True] * 4,
            feasible_active=[True] * 4,
            flip_counts=[0] * 4,
            group_counts=[6] * 4,
            gaps=[0.0] * 4,
            dq_refs=[0.5, 0.9, 1.1, 80.0],  # 前两个 < 1 g/day，后两个超阈值
        )
        self.assertAlmostEqual(out["dq_ref_change_rate"], 0.5)
        self.assertAlmostEqual(out["dq_ref_max"], 80.0)
        self.assertEqual(out["dq_ref_n_valid"], 4)

    def test_nan_displacements_are_dropped(self) -> None:
        from src.b2_evaluate import summarize

        out = summarize(
            feasible_all=[True] * 3,
            feasible_active=[True] * 3,
            flip_counts=[0] * 3,
            group_counts=[6] * 3,
            gaps=[0.0] * 3,
            dq_refs=[float("nan"), 2.0, 4.0],
        )
        self.assertEqual(out["dq_ref_n_valid"], 2)
        self.assertAlmostEqual(out["dq_ref_median"], 3.0)

    def test_without_dq_refs_keeps_legacy_keys(self) -> None:
        from src.b2_evaluate import summarize

        out = summarize(
            feasible_all=[True], feasible_active=[True],
            flip_counts=[0], group_counts=[6], gaps=[0.0],
        )
        self.assertNotIn("dq_ref_median", out)
        self.assertIn("flip_rate", out)


class UniqueSolutionCountTest(unittest.TestCase):
    """解签名的容差聚类（scripts/summarize_dq.py）。

    回归背景：初版用 `round(6)` 后转字符串，把 7.3e-9 g/day 的浮点噪声
    当成两个不同解，EAR/安徽/D3 虚报成「2 个唯一解」。
    """

    @staticmethod
    def _load():
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "scripts" / "summarize_dq.py"
        spec = importlib.util.spec_from_file_location("summarize_dq", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_float_noise_is_merged(self) -> None:
        mod = self._load()
        base = np.array([50.0, 300.0, 15.24007088, 59.75992912, 40.0, 436.06220713])
        noisy = base.copy()
        noisy[5] += 7.3e-9  # 实测噪声量级
        self.assertEqual(mod._n_unique(np.vstack([base, noisy])), 1)

    def test_real_difference_is_counted(self) -> None:
        mod = self._load()
        a = np.array([50.0, 300.0, 15.24, 59.76, 40.0, 436.06])
        b = a.copy()
        b[5] += 49.0  # 安徽 D0↔D1 的真实差
        self.assertEqual(mod._n_unique(np.vstack([a, b])), 2)

    def test_empty_matrix(self) -> None:
        mod = self._load()
        self.assertEqual(mod._n_unique(np.empty((0, 6))), 0)


class LambdaCurveAggregationTest(unittest.TestCase):
    """λ 曲线的「变动幅度」必须按 seed 分组算（scripts/diagnose_lambda_curve.py）。

    回归背景（CHANGELOG §29.6）：初版在**跨 3 个种子**的合并表上取 max/min，
    把种子间抽样差异算成了「λ 效应」，导致 CDG 的 CVaR 变动被报成 1.25–1.54%，
    而真实的 λ 效应是 0.0000%（Δq = 1e-9，解逐位相同）。

    这个测试钉住的正是「跨 seed 波动大、λ 内波动为 0」这个组合——
    用旧口径会报出非 0，用新口径必须报 0。
    """

    @staticmethod
    def _load():
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_lambda_curve.py"
        spec = importlib.util.spec_from_file_location("diagnose_lambda_curve", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_seed_variation_is_not_counted_as_lambda_effect(self) -> None:
        mod = self._load()
        # 每个 seed 内 λ 完全不影响 cvar；但 seed 之间差 1.4%
        rows = []
        for seed, base in [(1, 10.0), (2, 10.10), (3, 10.14)]:
            for lam in (0.0, 0.5, 1.0):
                rows.append({"seed": seed, "lam": lam, "cvar": base, "mean_cost": base})
        df = pd.DataFrame(rows)
        self.assertAlmostEqual(mod._within_seed_range_pct(df, "cvar"), 0.0)
        # 旧口径（合并后取 max/min）会报出约 1.4%，正是这个 bug
        naive = (df["cvar"].max() / df["cvar"].min() - 1.0) * 100.0
        self.assertGreater(naive, 1.0)

    def test_real_lambda_effect_is_detected(self) -> None:
        mod = self._load()
        # 同一 seed 内 λ 让 cvar 从 10.9 降到 9.6（EAT/江西 的实测幅度）
        rows = [
            {"seed": 1, "lam": 0.0, "cvar": 10.9089, "mean_cost": 9.0631},
            {"seed": 1, "lam": 1.0, "cvar": 9.6249, "mean_cost": 8.2200},
        ]
        got = mod._within_seed_range_pct(pd.DataFrame(rows), "cvar")
        self.assertGreater(got, 10.0)

    def test_empty_frame_returns_nan(self) -> None:
        mod = self._load()
        df = pd.DataFrame(columns=["seed", "lam", "cvar", "mean_cost"])
        self.assertTrue(np.isnan(mod._within_seed_range_pct(df, "cvar")))


class TruthEligibilityTest(unittest.TestCase):
    """`truth_eligible` 的判据是「组价里有没有非实测成分」，不是「有没有观测」。

    回归背景（CHANGELOG §32.1）：2026-10-27 修 G06 的部分结构聚合时，把 21 行
    `structure_weighted_bridged`（缺品类用批发价桥接补全，含 21.2% 非实测质量）
    的 `price_cny_kg` 填上了，但 `truth_eligible` 仍按旧判据 `n_obs > 0` 计算，
    于是 20 行被标成 True。这与 `scripts/build_price_bridge.py` 的
    「桥接行一律 False（不能用于真值参照）」直接冲突。

    本测试钉住三条：
      1. 任何 `structure_weighted_bridged` 行都不得 truth_eligible；
      2. 任何 `..._partial_lowerbound` 行（只观测到 1 个品类）也不得 truth_eligible；
      3. `structure_weighted_complete` 且 observed 的行必须 truth_eligible。
    """

    @staticmethod
    def _panel():
        import pandas as pd

        from src.b2_problem import PROCESSED

        return pd.read_csv(PROCESSED / "group_prices.csv", encoding="utf-8-sig")

    def test_bridged_rows_are_not_truth_eligible(self) -> None:
        px = self._panel()
        g06 = px[px["group_id"].eq("G06")]
        bridged = g06[g06["aggregation"].str.startswith("structure_weighted_bridged")]
        self.assertGreater(len(bridged), 0, "G06 应存在桥接补全行，否则本测试失去意义")
        self.assertFalse(
            bridged["truth_eligible"].astype(bool).any(),
            "桥接补全的组价含非实测成分，truth_eligible 必须为 False",
        )

    def test_lowerbound_rows_are_not_truth_eligible(self) -> None:
        px = self._panel()
        lb = px[px["aggregation"].str.contains("partial_lowerbound", regex=False)]
        self.assertGreater(len(lb), 0, "G06 应存在下界行（福建 3 行）")
        self.assertFalse(
            lb["truth_eligible"].astype(bool).any(),
            "只观测到部分品类的组价是下界，truth_eligible 必须为 False",
        )

    def test_complete_rows_remain_truth_eligible(self) -> None:
        px = self._panel()
        ok = px[
            px["aggregation"].str.startswith("structure_weighted_complete")
            & px["observed"].astype(bool)
        ]
        self.assertGreater(len(ok), 0)
        # 完整结构行里若有 data_nature 非「实测」的，允许 False；这里只要求
        # 「绝大多数为 True」，避免把上游 data_nature 的个别标记当成回归。
        share = float(ok["truth_eligible"].astype(bool).mean())
        self.assertGreater(share, 0.9, f"完整结构行应基本全部 truth_eligible，实测 {share:.2f}")
