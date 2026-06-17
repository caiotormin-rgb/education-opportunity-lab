from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from education_opportunity_lab.urban_api import (
    clean_number,
    clean_text,
    get_json,
    parse_year_range,
    write_csv,
)


CENSUS_BASE = "https://api.census.gov"
ACS_START_YEAR = 2009

ACS_VARIABLES = [
    "B15003_022E",  # Bachelor's degree
    "B15003_023E",  # Master's degree
    "B15003_024E",  # Professional school degree
    "B15003_025E",  # Doctorate degree
    "B15003_001E",  # Total population 25+ (BA+ denominator)
    "B05012_003E",  # Foreign born
    "B05012_001E",  # Total population (foreign born denominator)
    "B23025_005E",  # Unemployed
    "B23025_002E",  # In labor force (unemployment denominator)
    "B25070_007E",  # Renters paying 30.0–34.9% of income on housing
    "B25070_008E",  # 35.0–39.9%
    "B25070_009E",  # 40.0–49.9%
    "B25070_010E",  # 50.0%+
    "B25070_001E",  # Total renter-occupied units (housing burden denominator)
    "B09002_008E",  # Female householder, no husband, with own children
    "B09002_015E",  # Male householder, no wife, with own children
    "B09002_001E",  # Total households with own children (single-parent denominator)
]

# Census suppression codes — treat as missing
CENSUS_MISSING = {"-666666666", "-222222222", "-888888888", "-999999999", "N", "null"}


def _is_missing(value: str) -> bool:
    return value.strip() in CENSUS_MISSING or (value.strip().lstrip("-").isdigit() and int(value) < -1)


def _safe_rate(numerator: str, denominator: str) -> str:
    if _is_missing(numerator) or _is_missing(denominator):
        return ""
    try:
        num = float(numerator)
        den = float(denominator)
    except (ValueError, TypeError):
        return ""
    if den <= 0:
        return ""
    return f"{num / den:.6f}"


def _sum_fields(row: dict[str, str], keys: list[str]) -> str:
    total = 0.0
    found = False
    for key in keys:
        v = row.get(key, "")
        if not v or _is_missing(v):
            continue
        try:
            total += float(v)
            found = True
        except ValueError:
            pass
    return str(int(total)) if found and total.is_integer() else (str(total) if found else "")


def fetch_saipe_year(year: int, timeout_seconds: int = 20) -> list[dict[str, str]]:
    url = (
        f"{CENSUS_BASE}/data/timeseries/poverty/saipe/schdist"
        f"?get=SDNAME,SAEPOVRTALL_PT,SAEMHI_PT"
        f"&for=school%20district%20(unified):*&in=state:*&time={year}"
    )
    payload: Any = get_json(url, attempts=2, timeout_seconds=timeout_seconds)
    if not isinstance(payload, list) or len(payload) < 2:
        return []

    header = payload[0]
    try:
        name_idx = header.index("SDNAME")
        pov_idx = header.index("SAEPOVRTALL_PT")
        inc_idx = header.index("SAEMHI_PT")
        state_idx = header.index("state")
        dist_idx = header.index("school district (unified)")
    except ValueError:
        return []

    rows: list[dict[str, str]] = []
    for data_row in payload[1:]:
        state_fips = str(data_row[state_idx]).zfill(2)
        dist_code = str(data_row[dist_idx]).zfill(5)
        district_id = state_fips + dist_code

        pov_raw = str(data_row[pov_idx]) if data_row[pov_idx] is not None else ""
        inc_raw = str(data_row[inc_idx]) if data_row[inc_idx] is not None else ""

        poverty_rate = ""
        if pov_raw and not _is_missing(pov_raw):
            try:
                poverty_rate = f"{float(pov_raw) / 100:.6f}"
            except ValueError:
                pass

        median_income = ""
        if inc_raw and not _is_missing(inc_raw):
            median_income = clean_number(inc_raw)

        rows.append({
            "district_id": district_id,
            "year": str(year),
            "median_income": median_income,
            "poverty_rate": poverty_rate,
        })

    return rows


def fetch_acs_year(year: int, timeout_seconds: int = 20) -> list[dict[str, str]]:
    vars_param = ",".join(["NAME"] + ACS_VARIABLES)
    url = (
        f"{CENSUS_BASE}/data/{year}/acs/acs5"
        f"?get={vars_param}"
        f"&for=school%20district%20(unified):*&in=state:*"
    )
    payload: Any = get_json(url, attempts=2, timeout_seconds=timeout_seconds)
    if not isinstance(payload, list) or len(payload) < 2:
        return []

    header = [str(h) for h in payload[0]]

    def idx(name: str) -> int | None:
        try:
            return header.index(name)
        except ValueError:
            return None

    state_i = idx("state")
    dist_i = idx("school district (unified)")
    if state_i is None or dist_i is None:
        return []

    def get_field(data_row: list, name: str) -> str:
        i = idx(name)
        if i is None or i >= len(data_row):
            return ""
        v = data_row[i]
        return "" if v is None else str(v)

    rows: list[dict[str, str]] = []
    for data_row in payload[1:]:
        state_fips = str(data_row[state_i]).zfill(2)
        dist_code = str(data_row[dist_i]).zfill(5)
        district_id = state_fips + dist_code

        def f(name: str) -> str:
            return get_field(data_row, name)

        ba_sum = _sum_fields(
            {k: f(k) for k in ["B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E"]},
            ["B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E"],
        )
        housing_sum = _sum_fields(
            {k: f(k) for k in ["B25070_007E", "B25070_008E", "B25070_009E", "B25070_010E"]},
            ["B25070_007E", "B25070_008E", "B25070_009E", "B25070_010E"],
        )
        single_parent_sum = _sum_fields(
            {k: f(k) for k in ["B09002_008E", "B09002_015E"]},
            ["B09002_008E", "B09002_015E"],
        )

        rows.append({
            "district_id": district_id,
            "year": str(year),
            "adult_ba_plus_rate": _safe_rate(ba_sum, f("B15003_001E")),
            "foreign_born_rate": _safe_rate(f("B05012_003E"), f("B05012_001E")),
            "unemployment_rate": _safe_rate(f("B23025_005E"), f("B23025_002E")),
            "housing_cost_burden_rate": _safe_rate(housing_sum, f("B25070_001E")),
            "single_parent_household_rate": _safe_rate(single_parent_sum, f("B09002_001E")),
        })

    return rows


def merge_saipe_acs(
    saipe_rows: list[dict[str, str]],
    acs_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    acs_index = {(r["district_id"], r["year"]): r for r in acs_rows}
    merged: list[dict[str, str]] = []
    for saipe in saipe_rows:
        key = (saipe["district_id"], saipe["year"])
        acs = acs_index.get(key, {})
        row = dict(saipe)
        for col, val in acs.items():
            if col not in ("district_id", "year"):
                row[col] = val
        merged.append(row)
    return merged


def fetch_census_district_data(
    output_dir: str | Path,
    start_year: int,
    end_year: int,
    delay_seconds: float = 0.1,
    timeout_seconds: int = 30,
) -> dict[str, int]:
    import time

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    by_year_path = output_path / "by_year"
    by_year_path.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}

    for year in range(start_year, end_year + 1):
        print(f"Fetching {year} SAIPE...", flush=True)
        saipe_rows = fetch_saipe_year(year, timeout_seconds)
        print(f"  SAIPE: {len(saipe_rows)} districts", flush=True)

        acs_rows: list[dict[str, str]] = []
        if year >= ACS_START_YEAR:
            print(f"Fetching {year} ACS 5-year...", flush=True)
            acs_rows = fetch_acs_year(year, timeout_seconds)
            print(f"  ACS: {len(acs_rows)} districts", flush=True)

        year_rows = merge_saipe_acs(saipe_rows, acs_rows)
        write_csv(by_year_path / f"acs_{year}.csv", year_rows)
        all_rows.extend(year_rows)
        counts[f"acs_{year}"] = len(year_rows)

        if delay_seconds:
            time.sleep(delay_seconds)

    write_csv(output_path / "acs.csv", all_rows)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch district-year Census SAIPE and ACS demographic data.")
    parser.add_argument("--output-dir", default="data/interim/census", help="Output directory for normalized CSV files.")
    parser.add_argument("--years", default="2015:2022", help="Year or inclusive range, e.g. 2015:2022.")
    parser.add_argument("--delay-seconds", type=float, default=0.1, help="Delay between API calls.")
    parser.add_argument("--timeout-seconds", type=int, default=30, help="HTTP timeout per request.")
    args = parser.parse_args(argv)

    start_year, end_year = parse_year_range(args.years)
    counts = fetch_census_district_data(
        args.output_dir,
        start_year,
        end_year,
        args.delay_seconds,
        args.timeout_seconds,
    )
    for name in sorted(counts):
        print(f"{name}: {counts[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
