"""R003：手工可验算的确定性 LP fixture。

现有 toy 问题（``make_toy_problem``）带 6 个目标、20 个场景、机会约束，
能验证 MILP 机制，但**没人能手算它的最优解**，因此无法判断求解器
「算对了」还是「算出了一个自洽的错答案」。本文件补一个可逐行验算的 LP。

## 一个容易踩的语义陷阱

``use_chance_constraint=False`` **不是**「确定性硬约束」，而是
「完全不加营养约束」——``rows`` 里营养那部分直接为 0。这是 D2
（场景期望、不管营养）的语义。要做「单场景硬约束」，正确写法是
``S=1 + epsilon=0 + use_chance_constraint=True``：此时
``z_sum ≤ floor(0×1) = 0`` 强制 ``z=0``，机会约束退化为硬约束。
本文件第 4 个测试专门钉住这个区别。

## Fixture A：内点最优（不触碰任何边界）

    min  q1 + 3·q2
    s.t. 2·q1 + 1·q2 ≥ 8      (营养 A)
         1·q1 + 3·q2 ≥ 9      (营养 B)
         0 ≤ q1, q2 ≤ 10

两个约束在最优处**同时紧**，解方程组：

    2q1 + q2 = 8
    q1 + 3q2 = 9
    ⇒ q1 = 3, q2 = 2

手算顶点比较：

| 顶点 | 可行性 | 成本 q1 + 3q2 |
|---|---|---|
| (3, 2)   | A、B 均紧，可行 | **9** |
| (10, 0)  | A: 20≥8 ✓，B: 10≥9 ✓ | 10 |
| (0, 10)  | A: 10≥8 ✓，B: 30≥9 ✓ | 30 |
| (4, 0)   | B: 4≥9 ✗ | — |
| (0, 3)   | A: 3≥8 ✗ | — |

最优 (3, 2)，成本 9。**最优解不在任何边界上**，因此能区分
「真的在解 LP」与「把变量推到某个 bound 上」。

## Fixture B：上界紧约束

把 q_upper 收到 (2.5, 10)。此时 q1=3 不可行，最优解被上界截断：

    q1 = 2.5 ⇒ A: 5 + q2 ≥ 8 ⇒ q2 ≥ 3
               B: 2.5 + 3q2 ≥ 9 ⇒ q2 ≥ 2.167
    ⇒ q2 = 3，成本 2.5 + 9 = 11.5

## Fixture C：不可行

营养下界 (100, 100) 但 q_upper=(10,10)，A 的最大可达量只有 2·10+1·10=30 < 100。
求解器必须**明确报告不可行**，不能返回一个假装成功的解。
"""

from __future__ import annotations

import unittest

import numpy as np

from src.robust_modopt import solve_chance_modopt

COST = np.array([1.0, 3.0])
MATRIX = np.array([[2.0, 1.0], [1.0, 3.0]])


def _solve(
    q_upper: tuple[float, float],
    nutrient_lower: tuple[float, float],
    *,
    use_chance: bool = True,
    epsilon: float = 0.0,
):
    return solve_chance_modopt(
        objective_coeff=np.array([[[1.0, 3.0]]]),           # [S=1, L=1, K=2]
        nutrient_coeff=np.array([[[2.0, 1.0], [1.0, 3.0]]]),  # [S=1, J=2, K=2]
        nutrient_lower=np.array(nutrient_lower, dtype=float),
        nutrient_upper=np.array([np.inf, np.inf]),
        q_lower=np.array([0.0, 0.0]),
        q_upper=np.array(q_upper, dtype=float),
        objective_weights=np.array([1.0]),
        epsilon=epsilon,
        use_chance_constraint=use_chance,
    )


class HandCheckableLPTest(unittest.TestCase):
    def test_interior_optimum_matches_hand_solution(self) -> None:
        result = _solve((10.0, 10.0), (8.0, 9.0))
        self.assertTrue(result.success, result.message)
        np.testing.assert_allclose(result.q, [3.0, 2.0], atol=1e-6)
        # 手工成本：1×3 + 3×2 = 9
        self.assertAlmostEqual(float(COST @ result.q), 9.0, places=6)

    def test_interior_optimum_satisfies_both_constraints_with_equality(self) -> None:
        result = _solve((10.0, 10.0), (8.0, 9.0))
        # 两个约束都紧——这是手算结果的直接推论
        np.testing.assert_allclose(MATRIX @ result.q, [8.0, 9.0], atol=1e-6)

    def test_upper_bound_binds(self) -> None:
        result = _solve((2.5, 10.0), (8.0, 9.0))
        self.assertTrue(result.success, result.message)
        np.testing.assert_allclose(result.q, [2.5, 3.0], atol=1e-6)
        self.assertAlmostEqual(float(COST @ result.q), 11.5, places=6)
        self.assertAlmostEqual(float(result.q[0]), 2.5, places=6)

    def test_infeasible_reports_failure_not_fake_solution(self) -> None:
        result = _solve((10.0, 10.0), (100.0, 100.0))
        self.assertFalse(result.success, "不可行问题必须返回 success=False")
        self.assertFalse(np.isfinite(result.q).all(), "不可行时不应返回有限解")

    def test_disabling_chance_constraint_drops_nutrition_entirely(self) -> None:
        """``use_chance_constraint=False`` 等于「无营养约束」，与硬约束不是一回事。

        这是 D2 的语义：不管营养，只看成本，于是解被推到最便宜的角点 (0, 0)。
        若不钉住这条，很容易把它误当成「确定性硬约束」而得出错误结论。
        """
        relaxed = _solve((10.0, 10.0), (8.0, 9.0), use_chance=False)
        self.assertTrue(relaxed.success, relaxed.message)
        np.testing.assert_allclose(relaxed.q, [0.0, 0.0], atol=1e-6)
        # 营养约束被完全违反，证明它确实没被施加
        self.assertTrue(np.all(MATRIX @ relaxed.q < np.array([8.0, 9.0])))


if __name__ == "__main__":
    unittest.main()
