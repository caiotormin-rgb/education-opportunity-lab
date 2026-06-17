from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://educationdata.urban.org/api/v1"
USER_AGENT = "education-opportunity-lab/0.1"
MISSING_CODES = {-1, -2, -9, -99, -999}


def fetch_urban_district_data(
    output_dir: str | Path,
    start_year: int,
    end_year: int,
    delay_seconds: float = 0.05,
    timeout_seconds: int = 20,
    finance_timeout_seconds: int | None = None,
    fail_fast: bool = False,
    resume: bool = False,
) -> dict[str, int]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    by_year_path = output_path / "by_year"
    by_year_path.mkdir(parents=True, exist_ok=True)
    finance_timeout_seconds = finance_timeout_seconds or timeout_seconds

    failures: list[dict[str, str]] = []
    counts: dict[str, int] = {}

    for year in range(start_year, end_year + 1):
        ccd_year_path = by_year_path / f"ccd_{year}.csv"
        f33_year_path = by_year_path / f"f33_{year}.csv"
        special_education_year_path = by_year_path / f"special_education_{year}.csv"

        if resume and ccd_year_path.exists() and f33_year_path.exists() and special_education_year_path.exists():
            directory_count = count_csv_rows(ccd_year_path)
            finance_count = count_csv_rows(f33_year_path)
            print(f"Skipping {year}: directory={directory_count} finance={finance_count}", flush=True)
        else:
            print(f"Fetching {year} CCD directory...", flush=True)
            directory = fetch_endpoint(
                f"/school-districts/ccd/directory/{year}/",
                delay_seconds,
                timeout_seconds,
                fail_fast,
                failures,
            )
            directory_rows = [normalize_ccd_directory(row) for row in directory]
            special_education_rows = [normalize_directory_special_education(row) for row in directory]
            directory_count = len(directory_rows)

            print(f"Fetching {year} CCD finance...", flush=True)
            finance = fetch_endpoint(
                f"/school-districts/ccd/finance/{year}/",
                delay_seconds,
                finance_timeout_seconds,
                fail_fast,
                failures,
            )
            finance_rows = [normalize_f33_finance(row) for row in finance]
            special_education_rows.extend(normalize_finance_special_education(row) for row in finance)
            finance_count = len(finance_rows)

            write_csv(ccd_year_path, directory_rows)
            write_csv(f33_year_path, finance_rows)
            write_csv(special_education_year_path, collapse_special_education(special_education_rows))

        counts[f"ccd_directory_{year}"] = directory_count
        counts[f"ccd_finance_{year}"] = finance_count
        if failures:
            write_csv(output_path / "fetch_failures.csv", failures)
        print(
            f"Finished {year}: directory={directory_count} finance={finance_count}",
            flush=True,
        )

    combine_year_files(by_year_path, output_path, "ccd", start_year, end_year)
    combine_year_files(by_year_path, output_path, "f33", start_year, end_year)
    combine_year_files(by_year_path, output_path, "special_education", start_year, end_year)
    failure_path = output_path / "fetch_failures.csv"
    if not failures and failure_path.exists():
        failure_path.unlink()
    return counts


def fetch_endpoint(
    path: str,
    delay_seconds: float,
    timeout_seconds: int,
    fail_fast: bool,
    failures: list[dict[str, str]],
) -> list[dict[str, Any]]:
    url = f"{BASE_URL}{path}"
    rows: list[dict[str, Any]] = []

    while url:
        try:
            payload = get_json(url, timeout_seconds=timeout_seconds)
        except RuntimeError as exc:
            if fail_fast:
                raise
            failures.append({"endpoint": path, "url": url, "error": str(exc)})
            print(f"Failed endpoint, continuing: {path} ({exc})", flush=True)
            return rows
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise ValueError(f"Unexpected results payload for {url}")
        rows.extend(results)
        url = payload.get("next")
        if url and delay_seconds:
            time.sleep(delay_seconds)

    return rows


def get_json(url: str, attempts: int = 2, timeout_seconds: int = 20) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                return {"results": [], "next": None}
            last_error = exc
        except (TimeoutError, URLError, json.JSONDecodeError) as exc:
            last_error = exc

        if attempt < attempts:
            time.sleep(1.5 * attempt)

    raise RuntimeError(f"Failed to fetch {url}: {last_error}") from last_error


def normalize_ccd_directory(row: dict[str, Any]) -> dict[str, str]:
    return {
        "district_id": clean_text(row.get("leaid")),
        "year": clean_text(row.get("year")),
        "state": clean_text(row.get("state_location") or row.get("state_mailing")),
        "district_name": clean_text(row.get("lea_name")),
        "county_fips": normalize_county_fips(row.get("county_code")),
        "urbanicity": clean_text(row.get("urban_centric_locale")),
        "enrollment": clean_number(row.get("enrollment")),
        "school_count": clean_number(row.get("number_of_schools")),
        "teacher_count": clean_number(row.get("teachers_total_fte")),
        "english_language_learners": clean_number(row.get("english_language_learners")),
        "migrant_students": clean_number(row.get("migrant_students")),
    }


def normalize_f33_finance(row: dict[str, Any]) -> dict[str, str]:
    administration = sum_clean_numbers(row.get("exp_current_general_admin"), row.get("exp_current_sch_admin"))
    return {
        "district_id": clean_text(row.get("leaid")),
        "year": clean_text(row.get("year")),
        "total_revenue": clean_number(row.get("rev_total")),
        "local_revenue": clean_number(row.get("rev_local_total")),
        "state_revenue": clean_number(row.get("rev_state_total")),
        "federal_revenue": clean_number(row.get("rev_fed_total")),
        "property_tax_revenue": clean_number(row.get("rev_local_prop_tax")),
        "total_current_expenditure": clean_number(row.get("exp_current_elsec_total")),
        "instruction_spending": clean_number(row.get("exp_current_instruction_total") or row.get("exp_instruction")),
        "administration_spending": administration,
        "capital_outlay": clean_number(row.get("outlay_capital_total")),
        "idea_part_b_revenue": clean_number(row.get("rev_fed_state_idea")),
        "esser_revenue": clean_number(row.get("rev_arp_esser") or row.get("rev_crrsa_esser_ii") or row.get("rev_cares_act_relief_esser")),
    }


def normalize_directory_special_education(row: dict[str, Any]) -> dict[str, str]:
    return {
        "district_id": clean_text(row.get("leaid")),
        "year": clean_text(row.get("year")),
        "special_education_enrollment": clean_number(row.get("spec_ed_students")),
    }


def normalize_finance_special_education(row: dict[str, Any]) -> dict[str, str]:
    return {
        "district_id": clean_text(row.get("leaid")),
        "year": clean_text(row.get("year")),
        "special_education_expenditure": clean_number(row.get("exp_sped_current")),
        "special_education_instruction_expenditure": clean_number(row.get("exp_sped_instruction")),
        "special_education_pupil_support_expenditure": clean_number(row.get("exp_sped_pupil_support_services")),
        "special_education_staff_support_expenditure": clean_number(row.get("exp_sped_staff_support_services")),
        "special_education_transport_expenditure": clean_number(row.get("exp_sped_trans_support_services")),
        "special_education_teacher_salaries": clean_number(row.get("salaries_teachers_sped")),
    }


def collapse_special_education(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    collapsed: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["district_id"], row["year"])
        target = collapsed.setdefault(key, {"district_id": row["district_id"], "year": row["year"]})
        for column, value in row.items():
            if column in {"district_id", "year"}:
                continue
            if value != "":
                target[column] = value
    return list(collapsed.values())


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = sorted({column for row in rows for column in row})
    priority = ["district_id", "year", "state", "district_name", "county_fips", "urbanicity", "enrollment"]
    ordered = [column for column in priority if column in fieldnames]
    ordered.extend(column for column in fieldnames if column not in ordered)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered)
        writer.writeheader()
        writer.writerows(rows)


def read_local_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def count_csv_rows(path: Path) -> int:
    return len(read_local_csv(path))


def combine_year_files(by_year_path: Path, output_path: Path, stem: str, start_year: int, end_year: int) -> None:
    rows: list[dict[str, str]] = []
    for year in range(start_year, end_year + 1):
        rows.extend(read_local_csv(by_year_path / f"{stem}_{year}.csv"))
    write_csv(output_path / f"{stem}.csv", rows)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clean_number(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return clean_text(value)
    if int(number) == number and int(number) in MISSING_CODES:
        return ""
    if number in MISSING_CODES:
        return ""
    if number.is_integer():
        return str(int(number))
    return str(number)


def sum_clean_numbers(*values: Any) -> str:
    total = 0.0
    found = False
    for value in values:
        cleaned = clean_number(value)
        if cleaned == "":
            continue
        total += float(cleaned)
        found = True
    if not found:
        return ""
    if total.is_integer():
        return str(int(total))
    return str(total)


def normalize_county_fips(value: Any) -> str:
    cleaned = clean_text(value)
    if cleaned == "":
        return ""
    try:
        return f"{int(float(cleaned)):05d}"
    except ValueError:
        return cleaned


def parse_year_range(value: str) -> tuple[int, int]:
    if ":" in value:
        start, end = value.split(":", 1)
        return int(start), int(end)
    year = int(value)
    return year, year


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch district-year data from Urban Institute Education Data API.")
    parser.add_argument("--output-dir", default="data/interim/urban", help="Output directory for normalized CSV files.")
    parser.add_argument("--years", default="2020:2022", help="Year or inclusive range, e.g. 2018:2022.")
    parser.add_argument("--delay-seconds", type=float, default=0.05, help="Delay between paginated API calls.")
    parser.add_argument("--timeout-seconds", type=int, default=20, help="HTTP timeout per request.")
    parser.add_argument(
        "--finance-timeout-seconds",
        type=int,
        default=None,
        help="HTTP timeout per finance request. Defaults to --timeout-seconds.",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Stop on the first endpoint failure.")
    parser.add_argument("--resume", action="store_true", help="Reuse completed by-year CSV files.")
    args = parser.parse_args(argv)

    start_year, end_year = parse_year_range(args.years)
    counts = fetch_urban_district_data(
        args.output_dir,
        start_year,
        end_year,
        args.delay_seconds,
        args.timeout_seconds,
        args.finance_timeout_seconds,
        args.fail_fast,
        args.resume,
    )
    for name in sorted(counts):
        print(f"{name}: {counts[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
