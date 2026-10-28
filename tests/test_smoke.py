from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.imputation import mice_predict
from src.masking import make_mask
from src.robust_modopt import make_toy_problem, solve_chance_modopt


class RobustModoptTest(unittest.TestCase):
    def test_toy_problem_solves_and_respects_budget(self) -> None:
        problem = make_toy_problem(seed=7, scenarios=20)
        result = solve_chance_modopt(**problem, time_limit=60, mip_rel_gap=1e-6)
        self.assertTrue(result.success, msg=result.message)
        self.assertTrue(np.isfinite(result.q).all())
        self.assertTrue((result.q >= problem["q_lower"] - 1e-8).all())
        self.assertTrue((result.q <= problem["q_upper"] + 1e-8).all())
        allowed = int(np.floor(problem["epsilon"] * len(result.z) + 1e-12))
        self.assertLessEqual(int(result.z.sum()), allowed)

    def test_invalid_bounds_fail_loudly(self) -> None:
        problem = make_toy_problem(seed=7, scenarios=10)
        problem["q_lower"] = np.array([2.0, 0.0, 0.0])
        problem["q_upper"] = np.array([1.0, 1.0, 1.0])
        with self.assertRaises(ValueError):
            solve_chance_modopt(**problem)

    def test_nonfinite_coefficients_fail_loudly(self) -> None:
        problem = make_toy_problem(seed=7, scenarios=10)
        problem["objective_coeff"][0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            solve_chance_modopt(**problem)

    def test_chance_mode_joint_vs_marginal_budget(self) -> None:
        """R305：两种模式的预算维度不同，必须各按各的口径检查。

        joint 的预算约束在**场景**上（Σ_s z_s ≤ floor(εS)）；
        marginal 的预算在**每个营养素**上（Σ_s z_sj ≤ floor(εS)），
        所以总 z 数最多是 ``J × floor(εS)``，而不是 ``floor(εS)``。
        这两条一旦混用，marginal 会被误判成「违反预算」。
        """
        problem = make_toy_problem(seed=7, scenarios=20)
        n_scen = problem["objective_coeff"].shape[0]
        n_nut = problem["nutrient_coeff"].shape[1]
        allowed = int(np.floor(problem["epsilon"] * n_scen + 1e-12))

        joint = solve_chance_modopt(**problem, time_limit=60, chance_mode="joint")
        self.assertTrue(joint.success, msg=joint.message)
        self.assertEqual(len(joint.z), n_scen)
        self.assertLessEqual(int(joint.z.sum()), allowed)

        marginal = solve_chance_modopt(**problem, time_limit=60, chance_mode="marginal")
        self.assertTrue(marginal.success, msg=marginal.message)
        self.assertEqual(len(marginal.z), n_scen * n_nut)
        # 逐营养素预算：每个营养素各自的违反数不超过 allowed
        per_nutrient = marginal.z.reshape(n_scen, n_nut).sum(axis=0)
        self.assertTrue((per_nutrient <= allowed).all(), msg=str(per_nutrient))
        self.assertLessEqual(int(marginal.z.sum()), allowed * n_nut)

    def test_chance_mode_rejects_unknown(self) -> None:
        problem = make_toy_problem(seed=7, scenarios=10)
        with self.assertRaises(ValueError):
            solve_chance_modopt(**problem, chance_mode="independent")


class CvarObjectiveTest(unittest.TestCase):
    """风险厌恶目标（CVaR）的线性化必须与定义一致。

    背景：目标对 q 线性、价格只进目标时，``min E[c]·q = min c̄·q``，
    不确定性对决策零传导（CHANGELOG §21.5b）。CVaR 是打破这一点的最小改动，
    所以它的实现必须可验证，否则「改了目标仍然不传导」会分不清是模型性质还是代码 bug。
    """

    def _problem(self):
        problem = make_toy_problem(seed=11, scenarios=20)
        problem["use_chance_constraint"] = False  # 隔离风险项，不掺机会约束
        return problem

    def test_risk_weight_zero_reproduces_expectation(self) -> None:
        problem = self._problem()
        base = solve_chance_modopt(**problem)
        with_switch = solve_chance_modopt(**problem, risk_weight=0.0, cvar_alpha=0.9)
        self.assertAlmostEqual(base.objective, with_switch.objective, places=9)
        np.testing.assert_allclose(base.q, with_switch.q, atol=1e-7)

    def test_alpha_zero_makes_cvar_equal_expectation(self) -> None:
        """α=0 时 CVaR 退化为期望，λ 再怎么大也不该改变目标值。"""
        problem = self._problem()
        base = solve_chance_modopt(**problem)
        full_risk = solve_chance_modopt(**problem, risk_weight=1.0, cvar_alpha=0.0)
        self.assertTrue(full_risk.success, msg=full_risk.message)
        self.assertAlmostEqual(base.objective, full_risk.objective, places=6)

    def test_cvar_objective_matches_definition(self) -> None:
        from src.robust_modopt import normalized_cost_matrix

        problem = self._problem()
        alpha = 0.5
        res = solve_chance_modopt(**problem, risk_weight=1.0, cvar_alpha=alpha)
        self.assertTrue(res.success, msg=res.message)

        c_matrix = normalized_cost_matrix(
            problem["objective_coeff"],
            problem["objective_weights"],
            problem["q_lower"],
            problem["q_upper"],
        )
        costs = c_matrix @ np.asarray(res.q, dtype=float)
        n_tail = int(round((1.0 - alpha) * len(costs)))
        self.assertGreaterEqual(n_tail, 1)
        empirical = float(np.sort(costs)[-n_tail:].mean())
        self.assertAlmostEqual(res.objective, empirical, places=6)

    def test_invalid_risk_parameters_fail_loudly(self) -> None:
        problem = self._problem()
        with self.assertRaises(ValueError):
            solve_chance_modopt(**problem, risk_weight=1.5)
        with self.assertRaises(ValueError):
            solve_chance_modopt(**problem, risk_weight=0.5, cvar_alpha=1.0)


class ScenarioPerturbationTest(unittest.TestCase):
    """场景扰动对象的口径（2026-10-27 作者裁定：只扰动价格）。

    食物成分表是固定物理常数，对 ``nutrient_coeff`` 加噪声会让机会约束的可行性
    完全由它决定（K=6 下 D3 失败 11/12，CHANGELOG §21.6）。故默认 ``cv_nutrient=0``。
    """

    def test_zero_cv_repeats_point_estimate_exactly(self) -> None:
        from src.b2_scenarios import _lognormal

        rng = np.random.default_rng(0)
        point = np.array([[1.5, 2.0], [3.0, 4.0]])
        draws = _lognormal(rng, point, 0.0, 5)
        self.assertEqual(draws.shape, (5, 2, 2))
        for s in range(5):
            np.testing.assert_array_equal(draws[s], point)

    def test_default_nutrient_cv_is_zero(self) -> None:
        from src.b2_scenarios import CV_NUTRIENT_DEFAULT

        self.assertEqual(CV_NUTRIENT_DEFAULT, 0.0)


class ScopeRegistryTest(unittest.TestCase):
    """口径注册表必须两处一致，否则会静默跑出不同的 K。

    ``build_contract_files.SCOPES`` 决定「构建哪张审计表」，
    ``b2_problem.SCOPE_AUDITS`` 决定「加载哪张审计表」。两处对同一个口径名
    指向不同文件时，manifest 记录的组集合与模型实际用的组集合会不一致，
    而日志里只显示一个 K，看不出来。这类错误必须硬失败。
    """

    def test_scope_registries_agree(self) -> None:
        from scripts.build_contract_files import SCOPES
        from src.b2_problem import SCOPE_AUDITS

        overlap = set(SCOPES) & set(SCOPE_AUDITS)
        self.assertTrue(overlap, msg="两张注册表没有任何共同口径，说明改名后未同步")
        for scope in sorted(overlap):
            self.assertEqual(
                SCOPES[scope]["audit_file"],
                SCOPE_AUDITS[scope],
                msg=f"口径 {scope} 的审计表两处不一致",
            )

    def test_configured_decision_scope_is_registered(self) -> None:
        import yaml

        from scripts.build_contract_files import SCOPES
        from src.b2_problem import SCOPE_AUDITS

        root = Path(__file__).resolve().parents[1]
        cfg = yaml.safe_load((root / "configs" / "default.yaml").read_text(encoding="utf-8"))
        scope = cfg["optimization"]["decision_scope"]
        self.assertIn(scope, SCOPES)
        self.assertIn(scope, SCOPE_AUDITS)

    def test_configured_bounds_basis_is_valid(self) -> None:
        """配置里的营养下界口径必须是实现支持的取值。

        2026-10-27 作者裁定切到 ``ear``（CHANGELOG §22.8）。这条测试防的是
        「改了配置但代码没实现」或「改了代码但配置没跟上」两种漂移。
        """
        import yaml

        root = Path(__file__).resolve().parents[1]
        cfg = yaml.safe_load((root / "configs" / "default.yaml").read_text(encoding="utf-8"))
        self.assertIn(cfg["optimization"]["bounds_basis"], ("rni", "ear"))

    def test_every_scope_audit_file_exists(self) -> None:
        from src.b2_problem import SCOPE_AUDITS

        processed = Path(__file__).resolve().parents[1] / "data" / "processed"
        for scope, audit_file in SCOPE_AUDITS.items():
            self.assertTrue(
                (processed / audit_file).exists(),
                msg=f"口径 {scope} 的审计表 {audit_file} 不存在，需先跑 build_contract_files",
            )


    def test_consecutive_year_mask_is_consecutive(self) -> None:
        rows = []
        for year in range(2016, 2025):
            rows.append(
                {
                    "province": "P1",
                    "group_raw": "G1",
                    "year": year,
                    "value": float(year),
                    "observed": True,
                    "truth_eligible": True,
                }
            )
        panel = pd.DataFrame(rows)
        mask = make_mask(
            panel,
            "consecutive_years",
            np.random.default_rng(1),
            fraction=0.1,
            block_years=2,
            min_series_observations=5,
        )
        years = sorted(panel.loc[mask, "year"].tolist())
        self.assertEqual(years[1] - years[0], 1)

    def test_mask_survives_non_contiguous_index(self) -> None:
        """回归测试：调用方过滤过行时，mask 不得错位或越界。

        ``make_mask`` 内部用 ``panel.index`` 回写布尔数组。若索引不连续
        （例如调用方先 dropna 或按条件筛过行），标签 ≠ 位置，
        旧实现会静默错位、甚至抛 IndexError。此测试钉住修复后的行为：
        屏蔽的行数正确，且被屏蔽的确实都是 truth_eligible 的格。
        """
        rows = []
        for province in ["P1", "P2", "P3"]:
            for year in range(2016, 2025):
                rows.append(
                    {
                        "province": province,
                        "group_raw": "G1",
                        "year": year,
                        "value": float(year - 2015),
                        "observed": True,
                        "truth_eligible": True,
                    }
                )
        full = pd.DataFrame(rows)
        filtered = full.iloc[5:].copy()  # 索引从 5 开始，不连续
        self.assertNotEqual(filtered.index[0], 0)

        mask = make_mask(
            filtered,
            "single_cell",
            np.random.default_rng(3),
            fraction=0.2,
            block_years=2,
            fold=0,
            n_folds=2,
            fold_seed=0,
            min_series_observations=5,
        )
        self.assertEqual(len(mask), len(filtered))
        self.assertTrue(mask.any())
        # 被屏蔽的必须都是可用真值，且数量符合 fraction × 折内候选数
        self.assertTrue(filtered.loc[mask, "truth_eligible"].all())
        candidates = int(filtered["truth_eligible"].sum())
        expected = max(1, int(round(candidates / 2 * 0.2)))
        self.assertEqual(int(mask.sum()), expected)

    def test_mice_keeps_empty_year_column(self) -> None:
        rows = []
        for province in ["P1", "P2", "P3"]:
            for group in ["G1", "G2"]:
                for year in [2019, 2020, 2021]:
                    value = np.nan if year == 2020 else float(10 + year - 2019)
                    rows.append(
                        {
                            "province": province,
                            "group_raw": group,
                            "year": year,
                            "value": value,
                        }
                    )
        train = pd.DataFrame(rows)
        target = train.loc[train["year"].eq(2020), ["province", "group_raw", "year"]]
        pred = mice_predict(train, target, seed=3, draws=5)
        self.assertEqual(len(pred.mean), len(target))
        self.assertTrue(np.isfinite(pred.mean).all())


B1_RUN = Path("outputs") / "B1_formal_withmice_20261023_124906"
DECISION_GROUPS = ["G02", "G04", "G05", "G06", "G07", "G08"]


@unittest.skipUnless(
    (B1_RUN / "cell_predictions.csv").exists(), "需要 B1 正式批次产物"
)
class PosteriorScenarioTest(unittest.TestCase):
    """B1 经验残差 → 后验场景（CHANGELOG §25）。"""

    def setUp(self) -> None:
        from src.b2_scenarios import load_residual_pool

        self.pool = load_residual_pool(B1_RUN, groups=DECISION_GROUPS)

    def test_pool_covers_all_decision_groups(self) -> None:
        self.assertEqual(sorted(self.pool.by_group), sorted(DECISION_GROUPS))
        for g, arr in self.pool.by_group.items():
            self.assertGreater(arr.size, 2, msg=f"{g} 残差样本过少")

    def test_residuals_are_centered(self) -> None:
        for g, arr in self.pool.by_group.items():
            self.assertAlmostEqual(float(arr.mean()), 0.0, places=10, msg=g)

    def test_missing_group_raises_instead_of_silent_fallback(self) -> None:
        from src.b2_scenarios import load_residual_pool

        # province_group 几何从未遮蔽粮食(G04)，必须显式报错而不是回退占位噪声
        with self.assertRaises(ValueError):
            load_residual_pool(
                B1_RUN, mask_type="province_group", groups=DECISION_GROUPS
            )

    def test_scenarios_preserve_point_estimate_and_other_objectives(self) -> None:
        from src.b2_problem import Contract
        from src.b2_scenarios import posterior_scenarios

        contract = Contract.load_scope("k6_price")
        province = contract.complete_provinces()[0][0]
        inst = contract.instance(province, "CDG", bounds_basis="ear")
        obj, nut = posterior_scenarios(inst, 64, 20261027, pool=self.pool)

        self.assertEqual(obj.shape, (64,) + inst.objective_coeff[0].shape)
        self.assertEqual(nut.shape, (64,) + inst.nutrient_coeff[0].shape)
        # 场景均值必须等于点估计，否则 D3 与 D1 不是同一个问题
        np.testing.assert_allclose(
            obj[:, 0, :].mean(axis=0), inst.objective_coeff[0][0], rtol=1e-10
        )
        # 只扰动成本：ghg / land 不动
        np.testing.assert_allclose(
            obj[:, 1:, :], np.repeat(inst.objective_coeff[0][1:][None, ...], 64, axis=0)
        )
        # 营养系数不扰动
        np.testing.assert_allclose(nut, np.repeat(inst.nutrient_coeff, 64, axis=0))

    def test_scenarios_are_not_degenerate(self) -> None:
        from src.b2_problem import Contract
        from src.b2_scenarios import posterior_scenarios

        contract = Contract.load_scope("k6_price")
        province = contract.complete_provinces()[0][0]
        inst = contract.instance(province, "CDG", bounds_basis="ear")
        obj, _ = posterior_scenarios(inst, 64, 20261027, pool=self.pool)
        mult = obj[:, 0, :] / inst.objective_coeff[0][0][None, :]
        self.assertGreater(float(mult.std(axis=0).min()), 0.05)
        self.assertTrue((mult > 0).all())


@unittest.skipUnless(
    (B1_RUN / "cell_predictions.csv").exists(), "需要 B1 正式批次产物"
)
class ProtocolTest(unittest.TestCase):
    """遮蔽协议单元 → 价格位移（CHANGELOG §25）。"""

    def test_single_cell_shift_is_diluted_by_year_average(self) -> None:
        """单年遮蔽的组价位移必须被「跨年均值」稀释约一个年数量级。

        合同的组价是 9 年均值，所以单年 20% 的插补误差只让组价动 2% 左右。
        第一版实现直接施加相对误差，把位移放大了 9 倍，这条测试钉住修正。
        """
        from src.b2_protocol import build_shifts

        kw = dict(provinces=["安徽", "山东", "江苏", "江西", "浙江", "福建"], groups=DECISION_GROUPS)
        shifts = build_shifts(B1_RUN, mask_type="single_cell", **kw)
        mean_abs = float(np.mean([np.abs(m.to_numpy()).mean() for m in shifts.values()]))
        max_abs = float(max(np.abs(m.to_numpy()).max() for m in shifts.values()))

        # 位移应在百分之一量级（稀释后），而不是百分之几十（未稀释）
        self.assertLess(mean_abs, 0.01)
        self.assertLess(max_abs, 1.0)

        # 同一批单元格的**原始**相对误差要大一个量级，证明确实被稀释了
        raw = pd.read_csv(B1_RUN / "cell_predictions.csv")
        raw = raw[raw["method"].eq("hierarchical_rw") & raw["mask_type"].eq("single_cell")]
        rel = (raw["prediction"] / raw["truth"] - 1.0).abs()
        self.assertGreater(float(rel.median()), 10 * mean_abs)

    def test_protocol_cells_count_and_shapes(self) -> None:
        from src.b2_protocol import protocol_cells

        cells = protocol_cells(
            B1_RUN,
            mask_type="single_cell",
            folds=2,
            repeats=3,
            provinces=["安徽", "山东"],
            groups=DECISION_GROUPS,
        )
        self.assertEqual(len(cells), 6)
        self.assertEqual(sorted({c.fold for c in cells}), [0, 1])
        for cell in cells:
            self.assertEqual(list(cell.shift.columns), DECISION_GROUPS)
            self.assertEqual(list(cell.shift.index), ["安徽", "山东"])

    def test_apply_shift_scales_prices(self) -> None:
        from src.b2_protocol import apply_shift

        prices = np.array([10.0, 20.0, 30.0])
        shift = pd.Series([0.1, 0.0, -0.5])
        np.testing.assert_allclose(apply_shift(prices, shift), [11.0, 20.0, 15.0])
        with self.assertRaises(ValueError):
            apply_shift(prices, pd.Series([0.1, 0.2]))


if __name__ == "__main__":
    unittest.main()


class PooledPriceScopeTest(unittest.TestCase):
    """合并价的省集合口径（CHANGELOG §25.9 更正三）。

    历史 bug：诊断脚本用 7 省均值（含被排除的上海），正式批次 D0 用 6 省均值，
    导致安徽的价格半径 t 差 4 倍。这里把「两个口径确实不同」钉住，
    防止有人把 pooled_price() 与 price_mode="pooled" 当成同一件事。
    """

    def setUp(self) -> None:
        from src.b2_problem import Contract

        self.contract = Contract.load_scope("k6_price")
        self.usable, self.excluded = self.contract.complete_provinces()

    def test_scope_argument_changes_the_result(self) -> None:
        pooled_decision = self.contract.pooled_price(self.usable)
        pooled_all = self.contract.pooled_price()
        self.assertEqual(pooled_decision.shape, (len(self.contract.groups),))
        self.assertFalse(
            np.allclose(pooled_decision, pooled_all),
            msg="6 省与全表合并价相同——说明被排除的省份没有价格，需重新审视该测试前提",
        )

    def test_scope_matches_reindexed_panel_mean(self) -> None:
        expected = (
            self.contract.price_panel()
            .reindex(self.usable)
            .mean(axis=0, skipna=True)
            .to_numpy(dtype=float)
        )
        np.testing.assert_allclose(self.contract.pooled_price(self.usable), expected)

    def test_unknown_province_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.contract.pooled_price(["不存在的省"])

    def test_accepts_imputed_panel(self) -> None:
        panel = self.contract.price_panel().reindex(self.usable)
        shifted = panel * 1.1
        np.testing.assert_allclose(
            self.contract.pooled_price(self.usable, panel=shifted),
            self.contract.pooled_price(self.usable) * 1.1,
        )
