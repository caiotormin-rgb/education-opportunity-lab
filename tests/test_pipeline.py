from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from education_opportunity_lab.pipeline import build_panel, write_csv
from education_opportunity_lab.schema import validate_panel
from education_opportunity_lab.urban_api import normalize_ccd_directory, normalize_f33_finance


class PipelineTest(unittest.TestCase):
    def test_build_panel_adds_derived_finance_and_policy_features(self) -> None:
        result = build_panel(REPO_ROOT / "samples")
        rows = {(row["district_id"], row["year"]): row for row in result.rows}

        autauga_2023 = rows[("0100001", "2023")]
        self.assertEqual(autauga_2023["teacher_pay_reform_active"], "1")
        self.assertEqual(autauga_2023["funding_reform_active"], "0")
        self.assertEqual(autauga_2023["spending_per_student"], "11800.000000")
        self.assertEqual(autauga_2023["instruction_spending_pp"], "6972.972973")
        self.assertEqual(autauga_2023["special_education_rate"], "0.142703")
        self.assertEqual(autauga_2023["special_education_spending_pp"], "12200.000000")
        self.assertEqual(autauga_2023["math_proficiency_rate"], "0.439")

        springfield_2022 = rows[("2500001", "2022")]
        self.assertEqual(springfield_2022["funding_reform_active"], "0")

        springfield_2023 = rows[("2500001", "2023")]
        self.assertEqual(springfield_2023["funding_reform_active"], "1")
        self.assertIn("Student Opportunity Act", springfield_2023["active_policy_events"])
        self.assertEqual(springfield_2023["violent_crime_rate"], "5.61")

    def test_written_panel_validates_against_schema(self) -> None:
        result = build_panel(REPO_ROOT / "samples")
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "panel.csv"
            write_csv(result.rows, output)
            columns = validate_panel(output, REPO_ROOT / "config" / "panel_schema.json")

        self.assertIn("district_id", columns)
        self.assertIn("spending_per_student", columns)
        self.assertIn("special_education_rate", columns)
        self.assertIn("graduation_rate", columns)

    def test_duplicate_keys_raise_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir)
            for path in (REPO_ROOT / "samples").glob("*.csv"):
                target = input_dir / path.name
                target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

            ccd_path = input_dir / "ccd.csv"
            with ccd_path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["0100001", "2023", "AL", "Duplicate", "01001", "Town", "9250", "14", "552"])

            with self.assertRaises(ValueError):
                build_panel(input_dir)

    def test_urban_normalizers_map_real_endpoint_fields(self) -> None:
        ccd = normalize_ccd_directory(
            {
                "leaid": "0100005",
                "year": 2022,
                "state_location": "AL",
                "lea_name": "Albertville City",
                "county_code": "1095",
                "urban_centric_locale": 32,
                "enrollment": 5900,
                "number_of_schools": 6,
                "teachers_total_fte": 322.5,
                "english_language_learners": -1,
                "migrant_students": 4,
            }
        )
        self.assertEqual(ccd["district_id"], "0100005")
        self.assertEqual(ccd["county_fips"], "01095")
        self.assertEqual(ccd["english_language_learners"], "")

        f33 = normalize_f33_finance(
            {
                "leaid": "0100005",
                "year": 2020,
                "rev_total": 74420000,
                "rev_fed_total": 10327000,
                "rev_state_total": 46000000,
                "rev_local_total": 18093000,
                "rev_local_prop_tax": 12000000,
                "exp_current_elsec_total": 70100000,
                "exp_current_instruction_total": 42000000,
                "exp_current_general_admin": 1200000,
                "exp_current_sch_admin": 2300000,
                "outlay_capital_total": -1,
                "rev_fed_state_idea": 991000,
            }
        )
        self.assertEqual(f33["administration_spending"], "3500000")
        self.assertEqual(f33["capital_outlay"], "")
        self.assertEqual(f33["idea_part_b_revenue"], "991000")


if __name__ == "__main__":
    unittest.main()
