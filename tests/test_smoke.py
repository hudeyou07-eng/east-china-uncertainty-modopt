from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
