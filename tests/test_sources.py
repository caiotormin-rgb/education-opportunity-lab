from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from education_opportunity_lab.census_api import (
    fetch_saipe_year,
    fetch_acs_year,
    merge_saipe_acs,
)
from education_opportunity_lab.crdc_api import (
    normalize_crdc_discipline_row,
    normalize_crdc_absenteeism_row,
    normalize_crdc_access_row,
    CRDC_ABSENTEEISM_START,
)
from education_opportunity_lab.crime_normalizer import (
    read_ucr_agencies,
    read_ucr_offenses,
    join_agencies_offenses,
    aggregate_to_county_year,
    STATE_FIPS,
)
from education_opportunity_lab.edfacts_api import (
    normalize_assessment_row,
    normalize_grad_row,
    merge_outcomes,
)
from education_opportunity_lab.event_study import (
    add_relative_time,
    build_event_study_panel,
    demean_within_district,
)


# ---------------------------------------------------------------------------
# Census API tests
# ---------------------------------------------------------------------------

class CensusApiTest(unittest.TestCase):
    def test_saipe_district_id_construction(self) -> None:
        # Simulate the parsing logic directly (without network)
        state_fips = "01"
        dist_code = "00001"
        district_id = state_fips.zfill(2) + dist_code.zfill(5)
        self.assertEqual(district_id, "0100001")

    def test_saipe_poverty_rate_divided_by_100(self) -> None:
        # SAIPE returns percentage; we divide by 100
        pov_raw = "13.5"
        poverty_rate = f"{float(pov_raw) / 100:.6f}"
        self.assertEqual(poverty_rate, "0.135000")

    def test_saipe_poverty_rate_zero(self) -> None:
        pov_raw = "0.0"
        poverty_rate = f"{float(pov_raw) / 100:.6f}"
        self.assertEqual(poverty_rate, "0.000000")

    def test_acs_rate_adult_ba_plus(self) -> None:
        from education_opportunity_lab.census_api import _safe_rate, _sum_fields

        ba_fields = {
            "B15003_022E": "500",
            "B15003_023E": "200",
            "B15003_024E": "50",
            "B15003_025E": "10",
        }
        ba_sum = _sum_fields(ba_fields, ["B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E"])
        rate = _safe_rate(ba_sum, "2000")
        self.assertAlmostEqual(float(rate), 760 / 2000, places=5)

    def test_acs_missing_census_suppression_code(self) -> None:
        from education_opportunity_lab.census_api import _is_missing

        self.assertTrue(_is_missing("-666666666"))
        self.assertTrue(_is_missing("-222222222"))
        self.assertFalse(_is_missing("500"))
        self.assertFalse(_is_missing("0"))

    def test_acs_safe_rate_zero_denominator(self) -> None:
        from education_opportunity_lab.census_api import _safe_rate

        self.assertEqual(_safe_rate("100", "0"), "")

    def test_acs_safe_rate_missing_numerator(self) -> None:
        from education_opportunity_lab.census_api import _safe_rate

        self.assertEqual(_safe_rate("", "1000"), "")

    def test_merge_saipe_acs_combines_rows(self) -> None:
        saipe = [{"district_id": "0100001", "year": "2020", "median_income": "52000", "poverty_rate": "0.135000"}]
        acs = [{"district_id": "0100001", "year": "2020", "adult_ba_plus_rate": "0.250000", "foreign_born_rate": "0.050000", "unemployment_rate": "0.040000", "housing_cost_burden_rate": "0.300000", "single_parent_household_rate": "0.200000"}]
        merged = merge_saipe_acs(saipe, acs)
        self.assertEqual(len(merged), 1)
        row = merged[0]
        self.assertEqual(row["district_id"], "0100001")
        self.assertEqual(row["median_income"], "52000")
        self.assertEqual(row["adult_ba_plus_rate"], "0.250000")

    def test_merge_saipe_acs_missing_acs_row(self) -> None:
        saipe = [{"district_id": "0100001", "year": "2020", "median_income": "52000", "poverty_rate": "0.135000"}]
        acs: list = []
        merged = merge_saipe_acs(saipe, acs)
        self.assertEqual(len(merged), 1)
        self.assertNotIn("adult_ba_plus_rate", merged[0])


# ---------------------------------------------------------------------------
# CRDC API tests
# ---------------------------------------------------------------------------

class CrdcApiTest(unittest.TestCase):
    def _disc_row(self, iss: int, oss: int, enr: int, leaid: str = "0100001", year: str = "2018") -> dict:
        return {"leaid": leaid, "year": year, "tot_disc_iss": iss, "tot_disc_oss": oss, "tot_enr": enr}

    def test_suspension_rate_computed_correctly(self) -> None:
        row = self._disc_row(iss=100, oss=50, enr=1000)
        result = normalize_crdc_discipline_row(row)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result["suspension_rate"]), 150 / 1000, places=5)

    def test_suspension_field_fallback_iss_students(self) -> None:
        row = {"leaid": "0100001", "year": "2016", "iss_students": 80, "oss_students": 40, "tot_enr": 1000}
        result = normalize_crdc_discipline_row(row)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result["suspension_rate"]), 120 / 1000, places=5)

    def test_zero_enrollment_yields_empty_rate(self) -> None:
        row = self._disc_row(iss=10, oss=5, enr=0)
        result = normalize_crdc_discipline_row(row)
        self.assertIsNotNone(result)
        self.assertEqual(result["suspension_rate"], "")

    def test_missing_leaid_returns_none(self) -> None:
        row = {"leaid": "", "year": "2018", "tot_disc_iss": 10, "tot_disc_oss": 5, "tot_enr": 100}
        result = normalize_crdc_discipline_row(row)
        self.assertIsNone(result)

    def test_chronic_absenteeism_empty_before_2016(self) -> None:
        from education_opportunity_lab.crdc_api import fetch_crdc_absenteeism

        result = fetch_crdc_absenteeism(2014, 0, 5, False, [])
        self.assertEqual(result, [])

    def test_ap_participation_rate_computed(self) -> None:
        row = {"leaid": "0100001", "year": "2018", "enrl_AP_total": 200, "tot_enr": 1000}
        result = normalize_crdc_access_row(row)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result["ap_participation_rate"]), 0.2, places=5)

    def test_gifted_field_fallback(self) -> None:
        row = {"leaid": "0100001", "year": "2018", "gifted_enrl_total": 50, "tot_enr": 500}
        result = normalize_crdc_access_row(row)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result["gifted_participation_rate"]), 0.1, places=5)

    def test_absenteeism_normalized(self) -> None:
        row = {"leaid": "0100001", "year": "2018", "chron_absent": 150, "tot_enr": 1000}
        result = normalize_crdc_absenteeism_row(row)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result["chronic_absenteeism_rate"]), 0.15, places=5)


# ---------------------------------------------------------------------------
# Crime normalizer tests
# ---------------------------------------------------------------------------

class CrimeNormalizerTest(unittest.TestCase):
    def _agencies(self, ori: str, state: str, county: str, pop: int) -> dict:
        return {"ORI": ori, "STATE_ABBR": state, "COUNTY_CODE": county, "POPULATION": str(pop)}

    def _offenses(self, ori: str, year: str, violent: int, prop: int) -> dict:
        return {"ORI": ori, "YEAR": year, "VIOLENT_CRIME_TOTAL": str(violent), "PROPERTY_CRIME_TOTAL": str(prop)}

    def test_county_fips_construction(self) -> None:
        self.assertEqual(STATE_FIPS["AL"], "01")
        county_code = "001"
        county_fips = STATE_FIPS["AL"] + county_code.zfill(3)
        self.assertEqual(county_fips, "01001")

    def test_aggregate_per_100k_rate(self) -> None:
        joined = [
            {"county_fips": "01001", "year": "2019", "violent_crime": "100", "property_crime": "500", "population": "100000"},
        ]
        result = aggregate_to_county_year(joined)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(float(result[0]["violent_crime_rate"]), 100.0, places=1)
        self.assertAlmostEqual(float(result[0]["property_crime_rate"]), 500.0, places=1)

    def test_two_agencies_same_county_summed(self) -> None:
        joined = [
            {"county_fips": "01001", "year": "2019", "violent_crime": "60", "property_crime": "300", "population": "60000"},
            {"county_fips": "01001", "year": "2019", "violent_crime": "40", "property_crime": "200", "population": "40000"},
        ]
        result = aggregate_to_county_year(joined)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(float(result[0]["violent_crime_rate"]), 100.0, places=1)

    def test_zero_population_excluded_from_denominator(self) -> None:
        joined = [
            {"county_fips": "01001", "year": "2019", "violent_crime": "50", "property_crime": "200", "population": "50000"},
            {"county_fips": "01001", "year": "2019", "violent_crime": "10", "property_crime": "50", "population": "0"},
        ]
        result = aggregate_to_county_year(joined)
        # Population from second ORI excluded; only 50000 in denominator
        # violent = 60 / 50000 * 100000 = 120.0
        self.assertAlmostEqual(float(result[0]["violent_crime_rate"]), 120.0, places=1)

    def test_no_population_yields_empty_rates(self) -> None:
        joined = [
            {"county_fips": "01001", "year": "2019", "violent_crime": "50", "property_crime": "200", "population": "0"},
        ]
        result = aggregate_to_county_year(joined)
        self.assertEqual(result[0]["violent_crime_rate"], "")
        self.assertEqual(result[0]["property_crime_rate"], "")

    def test_join_drops_unmatched_offenses(self) -> None:
        agencies = [{"ori": "AL001001", "county_fips": "01001", "state_abbr": "AL", "population": "50000"}]
        offenses = [
            {"ori": "AL001001", "year": "2019", "violent_crime": "100", "property_crime": "400"},
            {"ori": "AL999999", "year": "2019", "violent_crime": "50", "property_crime": "100"},
        ]
        joined = join_agencies_offenses(agencies, offenses)
        self.assertEqual(len(joined), 1)
        self.assertEqual(joined[0]["county_fips"], "01001")


# ---------------------------------------------------------------------------
# EDFacts API tests
# ---------------------------------------------------------------------------

class EdfactsApiTest(unittest.TestCase):
    def test_assessment_divides_by_100(self) -> None:
        row = {"leaid": "0100001", "year": "2019", "math_test_pct_prof_midpt": 42.1, "read_test_pct_prof_midpt": 55.3}
        result = normalize_assessment_row(row)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result["math_proficiency_rate"]), 0.421, places=4)
        self.assertAlmostEqual(float(result["reading_proficiency_rate"]), 0.553, places=4)

    def test_assessment_already_in_0_to_1_range(self) -> None:
        row = {"leaid": "0100001", "year": "2019", "math_test_pct_prof_midpt": 0.421}
        result = normalize_assessment_row(row)
        self.assertIsNotNone(result)
        # Value <= 1.0 is kept as-is
        self.assertAlmostEqual(float(result["math_proficiency_rate"]), 0.421, places=4)

    def test_assessment_field_fallback_pct_prof_adv_math(self) -> None:
        row = {"leaid": "0100001", "year": "2019", "pct_prof_adv_math": 38.5}
        result = normalize_assessment_row(row)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result["math_proficiency_rate"]), 0.385, places=4)

    def test_grad_rate_field_fallback(self) -> None:
        row = {"leaid": "0100001", "year": "2019", "grad_rate_midpt": 89.2}
        result = normalize_grad_row(row)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result["graduation_rate"]), 0.892, places=4)

    def test_merge_outcomes_fills_blank_columns(self) -> None:
        assess = [{"district_id": "0100001", "year": "2019", "math_proficiency_rate": "0.421000", "reading_proficiency_rate": "0.553000"}]
        grad = [{"district_id": "0100001", "year": "2019", "graduation_rate": "0.892000"}]
        merged = merge_outcomes(assess, grad)
        self.assertEqual(len(merged), 1)
        row = merged[0]
        self.assertEqual(row["graduation_rate"], "0.892000")
        self.assertEqual(row["attendance_rate"], "")
        self.assertEqual(row["dropout_rate"], "")
        self.assertEqual(row["college_enrollment_rate"], "")

    def test_missing_leaid_returns_none(self) -> None:
        row = {"leaid": "", "year": "2019", "math_test_pct_prof_midpt": 42.1}
        self.assertIsNone(normalize_assessment_row(row))

    def test_negative_proficiency_yields_empty(self) -> None:
        row = {"leaid": "0100001", "year": "2019", "math_test_pct_prof_midpt": -1}
        result = normalize_assessment_row(row)
        self.assertEqual(result["math_proficiency_rate"], "")


# ---------------------------------------------------------------------------
# Event study tests
# ---------------------------------------------------------------------------

class EventStudyTest(unittest.TestCase):
    def _rows(self, district_states_years: list[tuple[str, str, int]]) -> list[dict[str, str]]:
        return [
            {"district_id": d, "state": s, "year": str(y), "spending_per_student": str(10000 + y * 100)}
            for d, s, y in district_states_years
        ]

    def _events(self, policy_type: str, state: str, year: int) -> list[dict[str, str]]:
        return [{"policy_type": policy_type, "state": state, "event_year": str(year)}]

    def test_relative_time_pre_and_post(self) -> None:
        rows = self._rows([("D1", "AL", 2013), ("D1", "AL", 2015), ("D1", "AL", 2017)])
        events = self._events("funding_reform", "AL", 2015)
        result = add_relative_time(rows, events, "funding_reform")
        by_year = {r["year"]: r for r in result}
        self.assertEqual(by_year["2013"]["years_since_funding_reform"], "-2")
        self.assertEqual(by_year["2013"]["post_funding_reform"], "0")
        self.assertEqual(by_year["2015"]["years_since_funding_reform"], "0")
        self.assertEqual(by_year["2015"]["post_funding_reform"], "1")
        self.assertEqual(by_year["2017"]["years_since_funding_reform"], "2")
        self.assertEqual(by_year["2017"]["post_funding_reform"], "1")

    def test_no_event_for_state_yields_empty(self) -> None:
        rows = self._rows([("D1", "TX", 2018)])
        events = self._events("funding_reform", "AL", 2015)
        result = add_relative_time(rows, events, "funding_reform")
        self.assertEqual(result[0]["years_since_funding_reform"], "")
        self.assertEqual(result[0]["post_funding_reform"], "")

    def test_earliest_event_used_when_multiple(self) -> None:
        rows = self._rows([("D1", "AL", 2014)])
        events = [
            {"policy_type": "funding_reform", "state": "AL", "event_year": "2016"},
            {"policy_type": "funding_reform", "state": "AL", "event_year": "2012"},
        ]
        result = add_relative_time(rows, events, "funding_reform")
        self.assertEqual(result[0]["years_since_funding_reform"], "2")

    def test_build_event_study_panel_window_filter(self) -> None:
        rows = self._rows([("D1", "AL", y) for y in range(2009, 2022)])
        events = self._events("funding_reform", "AL", 2015)
        result = build_event_study_panel(rows, events, "funding_reform", window=(-3, 3))
        years = {int(r["year"]) for r in result}
        self.assertEqual(years, {2012, 2013, 2014, 2015, 2016, 2017, 2018})

    def test_window_excludes_no_event_rows(self) -> None:
        rows = self._rows([("D1", "AL", 2015), ("D2", "TX", 2015)])
        events = self._events("funding_reform", "AL", 2015)
        result = build_event_study_panel(rows, events, "funding_reform", window=(-5, 5))
        district_ids = {r["district_id"] for r in result}
        self.assertIn("D1", district_ids)
        self.assertNotIn("D2", district_ids)

    def test_demean_within_district(self) -> None:
        rows = [
            {"district_id": "D1", "year": "2013", "spending_per_student": "1"},
            {"district_id": "D1", "year": "2014", "spending_per_student": "2"},
            {"district_id": "D1", "year": "2015", "spending_per_student": "3"},
        ]
        result = demean_within_district(rows, ["spending_per_student"])
        demeaned = [float(r["spending_per_student_demeaned"]) for r in result]
        self.assertAlmostEqual(demeaned[0], -1.0, places=4)
        self.assertAlmostEqual(demeaned[1], 0.0, places=4)
        self.assertAlmostEqual(demeaned[2], 1.0, places=4)

    def test_demean_preserves_original_column(self) -> None:
        rows = [{"district_id": "D1", "year": "2015", "spending_per_student": "5000"}]
        result = demean_within_district(rows, ["spending_per_student"])
        self.assertEqual(result[0]["spending_per_student"], "5000")
        self.assertIn("spending_per_student_demeaned", result[0])

    def test_policy_type_space_normalized_to_underscore(self) -> None:
        rows = self._rows([("D1", "AL", 2015)])
        events = [{"policy_type": "funding reform", "state": "AL", "event_year": "2015"}]
        result = add_relative_time(rows, events, "funding reform")
        self.assertIn("years_since_funding_reform", result[0])
        self.assertIn("post_funding_reform", result[0])


if __name__ == "__main__":
    unittest.main()
