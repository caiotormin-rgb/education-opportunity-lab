from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from education_opportunity_lab.reports import (
    best_outcomes_per_dollar,
    compute_linear_trend,
    compute_outcome_composite,
    districts_in_decline,
    infrastructure_gap,
    most_improved_districts,
    spending_effectiveness,
)
from education_opportunity_lab.edfacts_api import (
    normalize_dropout_row,
    normalize_absenteeism_row,
    merge_outcomes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(district_id: str, year: int, **kwargs) -> dict[str, str]:
    base = {
        "district_id": district_id,
        "year": str(year),
        "district_name": f"District {district_id}",
        "state": "AL",
        "urbanicity": "Town",
        "enrollment": "5000",
    }
    base.update({k: str(v) for k, v in kwargs.items()})
    return base


def _panel_with_trend(district_id: str, start_year: int, n_years: int, start_outcome: float, slope: float, spending: float = 10000.0) -> list[dict[str, str]]:
    return [
        _row(district_id, start_year + i,
             math_proficiency_rate=start_outcome + slope * i,
             reading_proficiency_rate=start_outcome + slope * i,
             graduation_rate=min(1.0, start_outcome + slope * i + 0.1),
             spending_per_student=spending + 200 * i)
        for i in range(n_years)
    ]


# ---------------------------------------------------------------------------
# compute_linear_trend
# ---------------------------------------------------------------------------

class LinearTrendTest(unittest.TestCase):
    def test_positive_slope(self) -> None:
        pairs = [(2015, 0.4), (2016, 0.5), (2017, 0.6)]
        slope = compute_linear_trend(pairs)
        self.assertAlmostEqual(slope, 0.1, places=5)

    def test_negative_slope(self) -> None:
        pairs = [(2015, 0.6), (2016, 0.5), (2017, 0.4)]
        slope = compute_linear_trend(pairs)
        self.assertAlmostEqual(slope, -0.1, places=5)

    def test_flat_trend(self) -> None:
        pairs = [(2015, 0.5), (2016, 0.5), (2017, 0.5)]
        slope = compute_linear_trend(pairs)
        self.assertAlmostEqual(slope, 0.0, places=10)

    def test_single_point_returns_none(self) -> None:
        self.assertIsNone(compute_linear_trend([(2015, 0.5)]))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(compute_linear_trend([]))

    def test_all_same_x_returns_none(self) -> None:
        self.assertIsNone(compute_linear_trend([(2015, 0.4), (2015, 0.6)]))


# ---------------------------------------------------------------------------
# compute_outcome_composite
# ---------------------------------------------------------------------------

class OutcomeCompositeTest(unittest.TestCase):
    def test_all_metrics_present(self) -> None:
        row = _row("D1", 2020, math_proficiency_rate=0.5, reading_proficiency_rate=0.6,
                   graduation_rate=0.9, attendance_rate=0.95)
        result = compute_outcome_composite(row)
        self.assertIsNotNone(result)
        # Manually: (0.5*1 + 0.6*1 + 0.9*1.5 + 0.95*0.5) / (1+1+1.5+0.5)
        expected = (0.5 + 0.6 + 1.35 + 0.475) / 4.0
        self.assertAlmostEqual(result, expected, places=5)

    def test_partial_metrics(self) -> None:
        row = _row("D1", 2020, math_proficiency_rate=0.5, graduation_rate=0.9)
        result = compute_outcome_composite(row)
        self.assertIsNotNone(result)
        expected = (0.5 * 1.0 + 0.9 * 1.5) / (1.0 + 1.5)
        self.assertAlmostEqual(result, expected, places=5)

    def test_no_metrics_returns_none(self) -> None:
        row = _row("D1", 2020, spending_per_student=10000)
        self.assertIsNone(compute_outcome_composite(row))

    def test_blank_metrics_treated_as_missing(self) -> None:
        row = _row("D1", 2020, math_proficiency_rate=0.5)
        row["graduation_rate"] = ""
        result = compute_outcome_composite(row)
        self.assertAlmostEqual(result, 0.5, places=5)


# ---------------------------------------------------------------------------
# most_improved_districts
# ---------------------------------------------------------------------------

class MostImprovedTest(unittest.TestCase):
    def test_ranks_by_slope_descending(self) -> None:
        panel = (
            _panel_with_trend("D1", 2015, 5, 0.3, 0.05)   # +0.05/yr
            + _panel_with_trend("D2", 2015, 5, 0.4, 0.02)  # +0.02/yr
            + _panel_with_trend("D3", 2015, 5, 0.5, 0.08)  # +0.08/yr
        )
        result = most_improved_districts(panel, min_years=3)
        ids = [r["district_id"] for r in result]
        self.assertEqual(ids[0], "D3")
        self.assertEqual(ids[1], "D1")
        self.assertEqual(ids[2], "D2")

    def test_excludes_below_min_years(self) -> None:
        panel = (
            _panel_with_trend("D1", 2015, 5, 0.4, 0.05)
            + _panel_with_trend("D2", 2015, 2, 0.4, 0.1)   # only 2 years
        )
        result = most_improved_districts(panel, min_years=3)
        ids = [r["district_id"] for r in result]
        self.assertIn("D1", ids)
        self.assertNotIn("D2", ids)

    def test_top_n_limits_results(self) -> None:
        panel = _panel_with_trend("D1", 2015, 5, 0.3, 0.05) + _panel_with_trend("D2", 2015, 5, 0.4, 0.02)
        result = most_improved_districts(panel, min_years=3, top_n=1)
        self.assertEqual(len(result), 1)

    def test_output_has_expected_columns(self) -> None:
        panel = _panel_with_trend("D1", 2015, 5, 0.4, 0.05)
        result = most_improved_districts(panel, min_years=3)
        self.assertIn("improvement_rate_per_year", result[0])
        self.assertIn("initial_outcome", result[0])
        self.assertIn("final_outcome", result[0])
        self.assertIn("years_of_data", result[0])

    def test_empty_panel_returns_empty(self) -> None:
        self.assertEqual(most_improved_districts([], min_years=3), [])


# ---------------------------------------------------------------------------
# best_outcomes_per_dollar
# ---------------------------------------------------------------------------

class BestOutcomesPerDollarTest(unittest.TestCase):
    def test_ranks_by_efficiency(self) -> None:
        panel = [
            _row("D1", 2020, math_proficiency_rate=0.6, graduation_rate=0.9, spending_per_student=8000),
            _row("D2", 2020, math_proficiency_rate=0.6, graduation_rate=0.9, spending_per_student=15000),
        ]
        result = best_outcomes_per_dollar(panel)
        # D1 has lower spending → higher efficiency
        self.assertEqual(result[0]["district_id"], "D1")

    def test_excludes_missing_spending(self) -> None:
        panel = [
            _row("D1", 2020, math_proficiency_rate=0.5, graduation_rate=0.85, spending_per_student=10000),
            _row("D2", 2020, math_proficiency_rate=0.5, graduation_rate=0.85),
        ]
        result = best_outcomes_per_dollar(panel)
        ids = [r["district_id"] for r in result]
        self.assertIn("D1", ids)
        self.assertNotIn("D2", ids)

    def test_excludes_missing_outcomes(self) -> None:
        panel = [_row("D1", 2020, spending_per_student=10000)]
        self.assertEqual(best_outcomes_per_dollar(panel), [])

    def test_output_has_efficiency_score(self) -> None:
        panel = [_row("D1", 2020, math_proficiency_rate=0.5, graduation_rate=0.85, spending_per_student=10000)]
        result = best_outcomes_per_dollar(panel)
        self.assertIn("efficiency_score", result[0])
        self.assertGreater(float(result[0]["efficiency_score"]), 0)

    def test_uses_latest_year(self) -> None:
        panel = [
            _row("D1", 2019, math_proficiency_rate=0.4, graduation_rate=0.8, spending_per_student=8000),
            _row("D1", 2022, math_proficiency_rate=0.6, graduation_rate=0.9, spending_per_student=12000),
        ]
        result = best_outcomes_per_dollar(panel)
        self.assertEqual(result[0]["year"], "2022")


# ---------------------------------------------------------------------------
# spending_effectiveness
# ---------------------------------------------------------------------------

class SpendingEffectivenessTest(unittest.TestCase):
    def test_ranks_by_elasticity(self) -> None:
        # D1: spending grows $200/yr, outcomes grow 0.05/yr → elasticity = 0.05 / (200/10000) = 2.5
        # D2: spending grows $500/yr, outcomes grow 0.02/yr → elasticity = 0.02 / (500/10000) = 0.4
        d1 = _panel_with_trend("D1", 2015, 5, 0.4, 0.05, spending=10000)
        d2 = _panel_with_trend("D2", 2015, 5, 0.4, 0.02, spending=10000)
        # Give D2 a steeper spending increase
        for i, row in enumerate(d2):
            row["spending_per_student"] = str(10000 + 500 * i)
        result = spending_effectiveness(d1 + d2, min_years=3)
        self.assertEqual(result[0]["district_id"], "D1")

    def test_excludes_flat_spending(self) -> None:
        panel = [
            _row("D1", 2015 + i, math_proficiency_rate=0.5 + 0.01 * i,
                 graduation_rate=0.8, spending_per_student=10000)
            for i in range(5)
        ]
        # Spending slope ≈ 0 → excluded
        result = spending_effectiveness(panel, min_years=3)
        self.assertEqual(result, [])

    def test_excludes_below_min_years(self) -> None:
        panel = _panel_with_trend("D1", 2015, 2, 0.4, 0.05)
        result = spending_effectiveness(panel, min_years=3)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# districts_in_decline
# ---------------------------------------------------------------------------

class DistrictsInDeclineTest(unittest.TestCase):
    def test_returns_only_declining(self) -> None:
        panel = (
            _panel_with_trend("D1", 2015, 5, 0.5, -0.04)   # declining
            + _panel_with_trend("D2", 2015, 5, 0.4, 0.03)   # improving
        )
        result = districts_in_decline(panel, min_years=3)
        ids = [r["district_id"] for r in result]
        self.assertIn("D1", ids)
        self.assertNotIn("D2", ids)

    def test_sorted_by_magnitude_of_decline(self) -> None:
        panel = (
            _panel_with_trend("D1", 2015, 5, 0.5, -0.02)
            + _panel_with_trend("D2", 2015, 5, 0.5, -0.08)
        )
        result = districts_in_decline(panel, min_years=3)
        # D2 declines faster → should be first
        self.assertEqual(result[0]["district_id"], "D2")


# ---------------------------------------------------------------------------
# infrastructure_gap
# ---------------------------------------------------------------------------

class InfrastructureGapTest(unittest.TestCase):
    def test_ranks_by_capital_share_ascending(self) -> None:
        panel = [
            _row("D1", 2020, capital_outlay_pp=200, spending_per_student=10000),   # 2% share
            _row("D2", 2020, capital_outlay_pp=1500, spending_per_student=10000),  # 15% share
        ]
        result = infrastructure_gap(panel)
        self.assertEqual(result[0]["district_id"], "D1")

    def test_excludes_missing_capital(self) -> None:
        panel = [
            _row("D1", 2020, capital_outlay_pp=500, spending_per_student=10000),
            _row("D2", 2020, spending_per_student=10000),
        ]
        result = infrastructure_gap(panel)
        ids = [r["district_id"] for r in result]
        self.assertIn("D1", ids)
        self.assertNotIn("D2", ids)

    def test_capital_share_computed_correctly(self) -> None:
        panel = [_row("D1", 2020, capital_outlay_pp=1000, spending_per_student=10000)]
        result = infrastructure_gap(panel)
        self.assertAlmostEqual(float(result[0]["capital_share"]), 0.1, places=4)

    def test_output_includes_outcome_composite(self) -> None:
        panel = [
            _row("D1", 2020, capital_outlay_pp=500, spending_per_student=10000,
                 math_proficiency_rate=0.4, graduation_rate=0.8)
        ]
        result = infrastructure_gap(panel)
        self.assertNotEqual(result[0]["outcome_composite"], "")


# ---------------------------------------------------------------------------
# EDFacts Phase 3 extension tests
# ---------------------------------------------------------------------------

class EdfactsPhase3Test(unittest.TestCase):
    def test_dropout_rate_normalized(self) -> None:
        row = {"leaid": "0100001", "year": "2019", "dropout_rate": 8.3}
        result = normalize_dropout_row(row)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result["dropout_rate"]), 0.083, places=4)

    def test_dropout_field_fallback(self) -> None:
        row = {"leaid": "0100001", "year": "2019", "event_dropout_rate": 5.1}
        result = normalize_dropout_row(row)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result["dropout_rate"]), 0.051, places=4)

    def test_absenteeism_converts_to_attendance(self) -> None:
        row = {"leaid": "0100001", "year": "2019", "chronic_absenteeism_rate": 15.0}
        result = normalize_absenteeism_row(row)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result["attendance_rate"]), 0.85, places=4)

    def test_merge_outcomes_populates_dropout_and_attendance(self) -> None:
        assess = [{"district_id": "0100001", "year": "2019",
                   "math_proficiency_rate": "0.45", "reading_proficiency_rate": "0.50"}]
        grad = [{"district_id": "0100001", "year": "2019", "graduation_rate": "0.88"}]
        dropout = [{"district_id": "0100001", "year": "2019", "dropout_rate": "0.051"}]
        absenteeism = [{"district_id": "0100001", "year": "2019", "attendance_rate": "0.85"}]
        merged = merge_outcomes(assess, grad, dropout, absenteeism)
        self.assertEqual(len(merged), 1)
        row = merged[0]
        self.assertEqual(row["dropout_rate"], "0.051")
        self.assertEqual(row["attendance_rate"], "0.85")
        self.assertEqual(row["graduation_rate"], "0.88")
        self.assertEqual(row["college_enrollment_rate"], "")


if __name__ == "__main__":
    unittest.main()
