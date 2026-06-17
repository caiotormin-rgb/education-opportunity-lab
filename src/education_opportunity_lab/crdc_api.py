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


# CRDC is biennial — only these panel years have data
CRDC_YEARS: tuple[int, ...] = (2012, 2014, 2016, 2018, 2021)

# Chronic absenteeism was added in the 2015-16 CRDC wave
CRDC_ABSENTEEISM_START = 2016

MISSING_CODES = {"", "-1", "-2", "-9", "-99", "-999"}


def _missing(value: str) -> bool:
    return value in MISSING_CODES


def _safe_rate(numerator: str, denominator: str) -> str:
    if _missing(numerator) or _missing(denominator):
        return ""
    try:
        num = float(numerator)
        den = float(denominator)
    except ValueError:
        return ""
    if den <= 0:
        return ""
    return f"{num / den:.6f}"


def _sum_fields(row: dict[str, Any], *keys: str) -> str:
    total = 0.0
    found = False
    for key in keys:
        raw = clean_number(row.get(key))
        if raw == "":
            continue
        try:
            total += float(raw)
            found = True
        except ValueError:
            pass
    if not found:
        return ""
    return str(int(total)) if total.is_integer() else str(total)


def _get_field(row: dict[str, Any], *candidate_keys: str) -> str:
    """Try field name variants in order; return the first non-missing value."""
    for key in candidate_keys:
        v = clean_number(row.get(key))
        if v != "":
            return v
    return ""


def fetch_crdc_discipline(
    year: int,
    delay: float,
    timeout: int,
    fail_fast: bool,
    failures: list[dict[str, str]],
) -> list[dict[str, Any]]:
    return fetch_endpoint(
        f"/school-districts/crdc/discipline/{year}/",
        delay,
        timeout,
        fail_fast,
        failures,
    )


def fetch_crdc_absenteeism(
    year: int,
    delay: float,
    timeout: int,
    fail_fast: bool,
    failures: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if year < CRDC_ABSENTEEISM_START:
        return []
    return fetch_endpoint(
        f"/school-districts/crdc/chronic-absenteeism/{year}/",
        delay,
        timeout,
        fail_fast,
        failures,
    )


def fetch_crdc_access(
    year: int,
    delay: float,
    timeout: int,
    fail_fast: bool,
    failures: list[dict[str, str]],
) -> list[dict[str, Any]]:
    return fetch_endpoint(
        f"/school-districts/crdc/ap-ib-enrollment/{year}/",
        delay,
        timeout,
        fail_fast,
        failures,
    )


def normalize_crdc_discipline_row(row: dict[str, Any]) -> dict[str, str] | None:
    leaid = clean_text(row.get("leaid"))
    year = clean_text(row.get("year"))
    if not leaid or not year:
        return None

    # ISS / OSS field name variants across CRDC waves
    iss = _get_field(row, "tot_disc_iss", "iss_students", "students_ISS_total")
    oss = _get_field(row, "tot_disc_oss", "oss_students", "students_OSS_total")
    enrollment = _get_field(row, "tot_enr", "total_enrollment", "enrl_total")

    total_suspended = _sum_fields({"iss": iss, "oss": oss}, "iss", "oss") if (iss or oss) else ""
    suspension_rate = _safe_rate(total_suspended, enrollment)

    return {
        "district_id": leaid,
        "year": year,
        "suspension_rate": suspension_rate,
        "_enrollment": enrollment,
    }


def normalize_crdc_absenteeism_row(row: dict[str, Any]) -> dict[str, str] | None:
    leaid = clean_text(row.get("leaid"))
    year = clean_text(row.get("year"))
    if not leaid or not year:
        return None

    absent = _get_field(row, "chron_absent", "chrn_absent_students", "students_chronic_absent")
    enrollment = _get_field(row, "tot_enr", "total_enrollment", "enrl_total")

    return {
        "district_id": leaid,
        "year": year,
        "chronic_absenteeism_rate": _safe_rate(absent, enrollment),
    }


def normalize_crdc_access_row(row: dict[str, Any]) -> dict[str, str] | None:
    leaid = clean_text(row.get("leaid"))
    year = clean_text(row.get("year"))
    if not leaid or not year:
        return None

    ap_enr = _get_field(row, "enrl_AP_total", "ap_enrl_total", "students_AP_total")
    gifted = _get_field(row, "enrl_IDEA_GT_total", "gifted_enrl_total", "students_gifted_talented")
    enrollment = _get_field(row, "tot_enr", "total_enrollment", "enrl_total")

    return {
        "district_id": leaid,
        "year": year,
        "ap_participation_rate": _safe_rate(ap_enr, enrollment),
        "gifted_participation_rate": _safe_rate(gifted, enrollment),
    }


def _merge_year_rows(
    disc_rows: list[dict[str, str]],
    abs_rows: list[dict[str, str]],
    access_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    abs_index = {(r["district_id"], r["year"]): r for r in abs_rows}
    access_index = {(r["district_id"], r["year"]): r for r in access_rows}

    result: list[dict[str, str]] = []
    for disc in disc_rows:
        key = (disc["district_id"], disc["year"])
        row: dict[str, str] = {
            "district_id": disc["district_id"],
            "year": disc["year"],
            "suspension_rate": disc.get("suspension_rate", ""),
            "chronic_absenteeism_rate": abs_index.get(key, {}).get("chronic_absenteeism_rate", ""),
            "ap_participation_rate": access_index.get(key, {}).get("ap_participation_rate", ""),
            "gifted_participation_rate": access_index.get(key, {}).get("gifted_participation_rate", ""),
        }
        result.append(row)
    return result


def fetch_crdc_data(
    output_dir: str | Path,
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

    for year in CRDC_YEARS:
        year_path = by_year_path / f"crdc_{year}.csv"

        if resume and year_path.exists():
            rows = read_local_csv(year_path)
            print(f"Skipping {year}: {len(rows)} cached rows", flush=True)
            all_rows.extend(rows)
            counts[f"crdc_{year}"] = len(rows)
            continue

        print(f"Fetching {year} CRDC discipline...", flush=True)
        disc_raw = fetch_crdc_discipline(year, delay, timeout, fail_fast, failures)
        disc_rows = [r for raw in disc_raw if (r := normalize_crdc_discipline_row(raw)) is not None]

        print(f"Fetching {year} CRDC chronic absenteeism...", flush=True)
        abs_raw = fetch_crdc_absenteeism(year, delay, timeout, fail_fast, failures)
        abs_rows = [r for raw in abs_raw if (r := normalize_crdc_absenteeism_row(raw)) is not None]

        print(f"Fetching {year} CRDC AP/gifted access...", flush=True)
        access_raw = fetch_crdc_access(year, delay, timeout, fail_fast, failures)
        access_rows = [r for raw in access_raw if (r := normalize_crdc_access_row(raw)) is not None]

        year_rows = _merge_year_rows(disc_rows, abs_rows, access_rows)
        # Remove internal helper column
        for row in year_rows:
            row.pop("_enrollment", None)

        write_csv(year_path, year_rows)
        all_rows.extend(year_rows)
        counts[f"crdc_{year}"] = len(year_rows)
        print(f"Finished {year}: {len(year_rows)} districts", flush=True)

    write_csv(output_path / "crdc.csv", all_rows)

    if failures:
        write_csv(output_path / "fetch_failures.csv", failures)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch district-year CRDC data from Urban Institute API.")
    parser.add_argument("--output-dir", default="data/interim/crdc", help="Output directory for normalized CSV files.")
    parser.add_argument("--delay-seconds", type=float, default=0.05, help="Delay between API calls.")
    parser.add_argument("--timeout-seconds", type=int, default=20, help="HTTP timeout per request.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on the first endpoint failure.")
    parser.add_argument("--resume", action="store_true", help="Reuse completed by-year CSV files.")
    args = parser.parse_args(argv)

    counts = fetch_crdc_data(
        args.output_dir,
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
