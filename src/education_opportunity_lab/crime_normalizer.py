from __future__ import annotations

import argparse
import csv
from pathlib import Path

from education_opportunity_lab.pipeline import read_csv, write_csv


# Postal abbreviation → 2-digit state FIPS
STATE_FIPS: dict[str, str] = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
    "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18",
    "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23",
    "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55",
    "WY": "56", "PR": "72",
}

# UCR agencies CSV field name variants
_ORI_KEYS = ("ORI", "ori", "ORI9", "ori9", "Agency ORI")
_STATE_KEYS = ("STATE_ABBR", "state_abbr", "State Abbr", "STATE", "state")
_COUNTY_KEYS = ("COUNTY_CODE", "county_code", "County Code", "COUNTYCODE", "countycode")
_POP_KEYS = ("POPULATION", "population", "Pop", "pop")

# UCR offenses CSV field name variants
_VIOLENT_KEYS = ("VIOLENT_CRIME_TOTAL", "violent_crime_total", "Violent Crime Total", "violent_crime", "VIOLENT")
_PROPERTY_KEYS = ("PROPERTY_CRIME_TOTAL", "property_crime_total", "Property Crime Total", "property_crime", "PROPERTY")
_YEAR_KEYS = ("YEAR", "year", "Year", "DATA_YEAR", "data_year")


def _first(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        if key in row and row[key].strip():
            return row[key].strip()
    return ""


def _parse_int(value: str) -> int | None:
    v = value.strip().replace(",", "")
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def read_ucr_agencies(path: str | Path) -> list[dict[str, str]]:
    """Read UCR agencies CSV; normalize ORI, county_fips (5-char), population."""
    raw_rows = read_csv(path)
    result: list[dict[str, str]] = []
    for row in raw_rows:
        ori = _first(row, *_ORI_KEYS)
        if not ori:
            continue

        state_abbr = _first(row, *_STATE_KEYS).upper()
        state_fips = STATE_FIPS.get(state_abbr, "")

        county_raw = _first(row, *_COUNTY_KEYS)
        county_fips = ""
        if state_fips and county_raw:
            try:
                county_fips = state_fips + str(int(county_raw)).zfill(3)
            except ValueError:
                pass

        pop_raw = _first(row, *_POP_KEYS)
        population = str(_parse_int(pop_raw)) if pop_raw else ""

        result.append({
            "ori": ori.upper(),
            "county_fips": county_fips,
            "state_abbr": state_abbr,
            "population": population,
        })
    return result


def read_ucr_offenses(path: str | Path) -> list[dict[str, str]]:
    """Read UCR offenses CSV; normalize ORI, year, violent_crime, property_crime."""
    raw_rows = read_csv(path)
    result: list[dict[str, str]] = []
    for row in raw_rows:
        ori = _first(row, *_ORI_KEYS)
        if not ori:
            continue

        year_raw = _first(row, *_YEAR_KEYS)
        violent_raw = _first(row, *_VIOLENT_KEYS)
        property_raw = _first(row, *_PROPERTY_KEYS)

        result.append({
            "ori": ori.upper(),
            "year": year_raw,
            "violent_crime": str(_parse_int(violent_raw)) if violent_raw else "",
            "property_crime": str(_parse_int(property_raw)) if property_raw else "",
        })
    return result


def join_agencies_offenses(
    agencies: list[dict[str, str]],
    offenses: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Inner-join offenses onto agencies by ORI."""
    agency_index = {row["ori"]: row for row in agencies}
    joined: list[dict[str, str]] = []
    for offense in offenses:
        agency = agency_index.get(offense["ori"])
        if agency is None or not agency["county_fips"]:
            continue
        joined.append({
            "county_fips": agency["county_fips"],
            "year": offense["year"],
            "violent_crime": offense["violent_crime"],
            "property_crime": offense["property_crime"],
            "population": agency["population"],
        })
    return joined


def aggregate_to_county_year(joined: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sum crimes and population by (county_fips, year); compute per-100k rates."""
    sums: dict[tuple[str, str], dict[str, float]] = {}
    pops: dict[tuple[str, str], float] = {}

    for row in joined:
        key = (row["county_fips"], row["year"])
        if key not in sums:
            sums[key] = {"violent": 0.0, "property": 0.0}

        if row["violent_crime"]:
            try:
                sums[key]["violent"] += float(row["violent_crime"])
            except ValueError:
                pass
        if row["property_crime"]:
            try:
                sums[key]["property"] += float(row["property_crime"])
            except ValueError:
                pass

        # Only count population from ORIs with positive population
        if row["population"]:
            try:
                pop = float(row["population"])
                if pop > 0:
                    pops[key] = pops.get(key, 0.0) + pop
            except ValueError:
                pass

    result: list[dict[str, str]] = []
    for key, crime_sums in sorted(sums.items()):
        county_fips, year = key
        pop = pops.get(key, 0.0)

        if pop > 0:
            violent_rate = f"{crime_sums['violent'] / pop * 100_000:.2f}"
            property_rate = f"{crime_sums['property'] / pop * 100_000:.2f}"
        else:
            violent_rate = ""
            property_rate = ""

        result.append({
            "county_fips": county_fips,
            "year": year,
            "violent_crime_rate": violent_rate,
            "property_crime_rate": property_rate,
        })
    return result


def normalize_crime_data(
    agencies_path: str | Path,
    offenses_path: str | Path,
    output_path: str | Path,
    year: str | None = None,
) -> int:
    """Read agencies + offenses → join → aggregate → write crime.csv. Returns row count."""
    agencies = read_ucr_agencies(agencies_path)
    offenses = read_ucr_offenses(offenses_path)

    if year:
        for row in offenses:
            if not row["year"]:
                row["year"] = year

    joined = join_agencies_offenses(agencies, offenses)
    county_rows = aggregate_to_county_year(joined)
    write_csv(county_rows, output_path)
    return len(county_rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize FBI UCR crime data to county-year crime rates. "
            "Download UCR agencies and offenses CSV files from the FBI Crime Data Explorer "
            "(https://cde.fbi.gov/downloads) before running."
        )
    )
    parser.add_argument("--agencies", required=True, help="Path to UCR agencies CSV file.")
    parser.add_argument("--offenses", required=True, help="Path to UCR offenses CSV file.")
    parser.add_argument("--output", required=True, help="Output crime.csv path.")
    parser.add_argument("--year", default=None, help="Override year if offenses file lacks a year column.")
    args = parser.parse_args(argv)

    count = normalize_crime_data(args.agencies, args.offenses, args.output, args.year)
    print(f"Wrote {count} county-year rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
