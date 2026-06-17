from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from education_opportunity_lab.urban_api import (
    clean_number,
    clean_text,
    fetch_endpoint,
    parse_year_range,
    read_local_csv,
    write_csv,
)


# Assessment data (NCLB/ESSA proficiency) starts with 2009 reporting year
ASSESSMENT_START_YEAR = 2009

# 4-year adjusted cohort graduation rate became federal requirement for 2011
GRAD_START_YEAR = 2011

OUTCOME_COLUMNS = (
    "district_id",
    "year",
    "math_proficiency_rate",
    "reading_proficiency_rate",
    "graduation_rate",
    "attendance_rate",
    "dropout_rate",
    "college_enrollment_rate",
)


def _pct_to_rate(value: str) -> str:
    """Convert a 0–100 percentage string to a 0–1 rate string. Returns '' if missing."""
    if not value:
        return ""
    try:
        v = float(value)
        if v < 0:
            return ""
        # If already in 0–1 range (unlikely from Urban API but guard defensively)
        if v <= 1.0:
            return f"{v:.6f}"
        return f"{v / 100:.6f}"
    except ValueError:
        return ""


def fetch_assessments_year(
    year: int,
    delay: float,
    timeout: int,
    fail_fast: bool,
    failures: list[dict[str, str]],
) -> list[dict[str, Any]]:
    return fetch_endpoint(
        f"/school-districts/edfacts/assessments/{year}/",
        delay,
        timeout,
        fail_fast,
        failures,
    )


def fetch_grad_rates_year(
    year: int,
    delay: float,
    timeout: int,
    fail_fast: bool,
    failures: list[dict[str, str]],
) -> list[dict[str, Any]]:
    return fetch_endpoint(
        f"/school-districts/edfacts/grad-rates/{year}/",
        delay,
        timeout,
        fail_fast,
        failures,
    )


def normalize_assessment_row(row: dict[str, Any]) -> dict[str, str] | None:
    leaid = clean_text(row.get("leaid"))
    year = clean_text(row.get("year"))
    if not leaid or not year:
        return None

    # Urban API field names for math/reading proficiency midpoints
    math_raw = clean_number(
        row.get("math_test_pct_prof_midpt")
        or row.get("math_pct_prof_midpt")
        or row.get("pct_prof_adv_math")
    )
    reading_raw = clean_number(
        row.get("read_test_pct_prof_midpt")
        or row.get("read_pct_prof_midpt")
        or row.get("pct_prof_adv_read")
    )

    return {
        "district_id": leaid,
        "year": year,
        "math_proficiency_rate": _pct_to_rate(math_raw),
        "reading_proficiency_rate": _pct_to_rate(reading_raw),
    }


def normalize_grad_row(row: dict[str, Any]) -> dict[str, str] | None:
    leaid = clean_text(row.get("leaid"))
    year = clean_text(row.get("year"))
    if not leaid or not year:
        return None

    # Try field name variants across EDFacts releases
    grad_raw = clean_number(
        row.get("adjusted_cohort_grad_rate")
        or row.get("grad_rate_midpt")
        or row.get("grad_rate")
        or row.get("cohort_grad_rate")
    )

    return {
        "district_id": leaid,
        "year": year,
        "graduation_rate": _pct_to_rate(grad_raw),
    }


def merge_outcomes(
    assessment_rows: list[dict[str, str]],
    grad_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Left-join grad rates onto assessments by district_id+year; fill remaining outcome columns."""
    grad_index = {(r["district_id"], r["year"]): r for r in grad_rows}

    result: list[dict[str, str]] = []
    for assess in assessment_rows:
        key = (assess["district_id"], assess["year"])
        grad = grad_index.get(key, {})
        row: dict[str, str] = {
            "district_id": assess["district_id"],
            "year": assess["year"],
            "math_proficiency_rate": assess.get("math_proficiency_rate", ""),
            "reading_proficiency_rate": assess.get("reading_proficiency_rate", ""),
            "graduation_rate": grad.get("graduation_rate", ""),
            "attendance_rate": "",
            "dropout_rate": "",
            "college_enrollment_rate": "",
        }
        result.append(row)
    return result


def fetch_edfacts_data(
    output_dir: str | Path,
    start_year: int,
    end_year: int,
    delay: float = 0.05,
    timeout: int = 20,
    fail_fast: bool = False,
    resume: bool = False,
) -> dict[str, int]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    by_year_path = output_path / "by_year"
    by_year_path.mkdir(parents=True, exist_ok=True)

    failures: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    all_rows: list[dict[str, str]] = []

    eff_start_assess = max(start_year, ASSESSMENT_START_YEAR)
    eff_start_grad = max(start_year, GRAD_START_YEAR)

    for year in range(start_year, end_year + 1):
        year_path = by_year_path / f"outcomes_{year}.csv"

        if resume and year_path.exists():
            cached = read_local_csv(year_path)
            all_rows.extend(cached)
            counts[f"outcomes_{year}"] = len(cached)
            print(f"Skipping {year}: {len(cached)} cached rows", flush=True)
            continue

        assessment_rows: list[dict[str, str]] = []
        if year >= eff_start_assess:
            print(f"Fetching {year} EDFacts assessments...", flush=True)
            raw = fetch_assessments_year(year, delay, timeout, fail_fast, failures)
            assessment_rows = [r for raw_row in raw if (r := normalize_assessment_row(raw_row)) is not None]

        grad_rows: list[dict[str, str]] = []
        if year >= eff_start_grad:
            print(f"Fetching {year} EDFacts graduation rates...", flush=True)
            raw = fetch_grad_rates_year(year, delay, timeout, fail_fast, failures)
            grad_rows = [r for raw_row in raw if (r := normalize_grad_row(raw_row)) is not None]

        if assessment_rows:
            year_rows = merge_outcomes(assessment_rows, grad_rows)
        elif grad_rows:
            # Grad data with no assessment data for this year
            year_rows = [
                {
                    "district_id": r["district_id"],
                    "year": r["year"],
                    "math_proficiency_rate": "",
                    "reading_proficiency_rate": "",
                    "graduation_rate": r["graduation_rate"],
                    "attendance_rate": "",
                    "dropout_rate": "",
                    "college_enrollment_rate": "",
                }
                for r in grad_rows
            ]
        else:
            year_rows = []

        write_csv(year_rows, year_path)
        all_rows.extend(year_rows)
        counts[f"outcomes_{year}"] = len(year_rows)
        print(f"Finished {year}: {len(year_rows)} districts", flush=True)

    write_csv(all_rows, output_path / "outcomes.csv")

    if failures:
        write_csv(failures, output_path / "fetch_failures.csv")
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch district-year EDFacts outcomes from Urban Institute API.")
    parser.add_argument("--output-dir", default="data/interim/edfacts", help="Output directory for normalized CSV files.")
    parser.add_argument("--years", default="2012:2022", help="Year or inclusive range, e.g. 2012:2022.")
    parser.add_argument("--delay-seconds", type=float, default=0.05, help="Delay between API calls.")
    parser.add_argument("--timeout-seconds", type=int, default=20, help="HTTP timeout per request.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on the first endpoint failure.")
    parser.add_argument("--resume", action="store_true", help="Reuse completed by-year CSV files.")
    args = parser.parse_args(argv)

    start_year, end_year = parse_year_range(args.years)
    counts = fetch_edfacts_data(
        args.output_dir,
        start_year,
        end_year,
        args.delay_seconds,
        args.timeout_seconds,
        args.fail_fast,
        args.resume,
    )
    for name in sorted(counts):
        print(f"{name}: {counts[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
