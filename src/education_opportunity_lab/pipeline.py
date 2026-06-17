from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PANEL_KEY = ("district_id", "year")
COUNTY_YEAR_KEY = ("county_fips", "year")
DISTRICT_YEAR_OPTIONAL_FILES = (
    "f33.csv",
    "acs.csv",
    "crdc.csv",
    "special_education.csv",
    "outcomes.csv",
)


@dataclass(frozen=True)
class BuildResult:
    rows: list[dict[str, str]]
    missing_optional_files: list[str]


def build_panel(input_dir: str | Path) -> BuildResult:
    input_path = Path(input_dir)
    ccd_path = input_path / "ccd.csv"
    if not ccd_path.exists():
        raise FileNotFoundError(f"Required input not found: {ccd_path}")

    rows = filter_valid_keys(read_csv(ccd_path), PANEL_KEY)
    ensure_unique(rows, PANEL_KEY, "ccd.csv")

    missing_optional: list[str] = []
    for filename in DISTRICT_YEAR_OPTIONAL_FILES:
        path = input_path / filename
        if path.exists():
            rows = left_join(rows, read_csv(path), PANEL_KEY, filename)
        else:
            missing_optional.append(filename)

    crime_path = input_path / "crime.csv"
    if crime_path.exists():
        rows = left_join(rows, read_csv(crime_path), COUNTY_YEAR_KEY, "crime.csv")
    else:
        missing_optional.append("crime.csv")

    rows = add_finance_features(rows)
    rows = add_special_education_features(rows)

    policy_path = input_path / "policy_events.csv"
    if policy_path.exists():
        rows = add_policy_features(rows, read_csv(policy_path))
    else:
        missing_optional.append("policy_events.csv")
        rows = add_empty_policy_features(rows)

    return BuildResult(rows=rows, missing_optional_files=missing_optional)


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [clean_row(row) for row in reader]


def write_csv(rows: Iterable[dict[str, str]], path: str | Path) -> None:
    rows = list(rows)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output_path.write_text("", encoding="utf-8")
        return

    fieldnames = sorted({key for row in rows for key in row.keys()})
    ordered = order_columns(fieldnames)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered)
        writer.writeheader()
        writer.writerows(rows)


def clean_row(row: dict[str, str | None]) -> dict[str, str]:
    return {
        key.strip(): "" if value is None else value.strip()
        for key, value in row.items()
        if key is not None and key.strip()
    }


def left_join(
    left_rows: list[dict[str, str]],
    right_rows: list[dict[str, str]],
    key_columns: tuple[str, ...],
    source_name: str,
) -> list[dict[str, str]]:
    right_rows = filter_valid_keys(right_rows, key_columns)
    ensure_unique(right_rows, key_columns, source_name)
    right_index = {row_key(row, key_columns): row for row in right_rows}

    joined: list[dict[str, str]] = []
    for left in left_rows:
        key = row_key(left, key_columns)
        right = right_index.get(key, {})
        merged = dict(left)
        for column, value in right.items():
            if column not in key_columns:
                merged[column] = value
        joined.append(merged)
    return joined


def filter_valid_keys(rows: list[dict[str, str]], key_columns: tuple[str, ...]) -> list[dict[str, str]]:
    return [row for row in rows if has_valid_key(row, key_columns)]


def has_valid_key(row: dict[str, str], key_columns: tuple[str, ...]) -> bool:
    missing_codes = {"", "-1", "-2", "-9", "-99", "-999"}
    return all(row.get(column, "") not in missing_codes for column in key_columns)


def ensure_unique(rows: list[dict[str, str]], key_columns: tuple[str, ...], source_name: str) -> None:
    seen: set[tuple[str, ...]] = set()
    duplicates: list[tuple[str, ...]] = []
    for row in rows:
        key = row_key(row, key_columns)
        if key in seen:
            duplicates.append(key)
        seen.add(key)

    if duplicates:
        sample = ", ".join(str(key) for key in duplicates[:5])
        raise ValueError(f"{source_name} has duplicate keys for {key_columns}: {sample}")


def row_key(row: dict[str, str], key_columns: tuple[str, ...]) -> tuple[str, ...]:
    missing = [column for column in key_columns if column not in row]
    if missing:
        raise KeyError(f"Missing key columns {missing} in row: {row}")
    return tuple(row[column] for column in key_columns)


def add_finance_features(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    for row in rows:
        enrollment = parse_number(row.get("enrollment"))
        total_revenue = parse_number(row.get("total_revenue"))
        current_expenditure = parse_number(row.get("total_current_expenditure"))
        instruction = parse_number(row.get("instruction_spending"))
        administration = parse_number(row.get("administration_spending"))
        capital = parse_number(row.get("capital_outlay"))
        federal = parse_number(row.get("federal_revenue"))
        property_tax = parse_number(row.get("property_tax_revenue"))

        set_ratio(row, "spending_per_student", current_expenditure, enrollment)
        set_ratio(row, "instruction_spending_pp", instruction, enrollment)
        set_ratio(row, "admin_spending_pp", administration, enrollment)
        set_ratio(row, "capital_outlay_pp", capital, enrollment)
        set_ratio(row, "federal_funding_share", federal, total_revenue)
        set_ratio(row, "local_property_tax_share", property_tax, total_revenue)
    return rows


def add_special_education_features(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    for row in rows:
        enrollment = parse_number(row.get("enrollment"))
        special_ed_enrollment = parse_number(row.get("special_education_enrollment"))
        idea_part_b = parse_number(row.get("idea_part_b_enrollment"))
        special_ed_teachers = parse_number(row.get("special_education_teachers"))
        special_ed_spending = parse_number(row.get("special_education_expenditure"))

        set_ratio(row, "special_education_rate", special_ed_enrollment, enrollment)
        set_ratio(row, "idea_part_b_rate", idea_part_b, enrollment)
        set_ratio(row, "special_education_spending_pp", special_ed_spending, special_ed_enrollment)
        set_ratio(row, "special_education_student_teacher_ratio", special_ed_enrollment, special_ed_teachers)
    return rows


def add_policy_features(rows: list[dict[str, str]], events: list[dict[str, str]]) -> list[dict[str, str]]:
    events_by_state: dict[str, list[dict[str, str]]] = defaultdict(list)
    for event in events:
        events_by_state[event.get("state", "")].append(event)

    for row in rows:
        year = parse_int(row.get("year"))
        active_events: list[str] = []
        active_types: set[str] = set()

        for event in events_by_state.get(row.get("state", ""), []):
            event_year = parse_int(event.get("event_year"))
            if year is not None and event_year is not None and year >= event_year:
                policy_type = event.get("policy_type", "")
                active_types.add(policy_type)
                event_name = event.get("event_name") or policy_type
                if event_name:
                    active_events.append(event_name)

        row["funding_reform_active"] = "1" if "funding_reform" in active_types else "0"
        row["teacher_pay_reform_active"] = "1" if "teacher_pay_reform" in active_types else "0"
        row["school_choice_active"] = "1" if "school_choice" in active_types else "0"
        row["active_policy_events"] = "; ".join(sorted(active_events))

    return rows


def add_empty_policy_features(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    for row in rows:
        row["funding_reform_active"] = "0"
        row["teacher_pay_reform_active"] = "0"
        row["school_choice_active"] = "0"
        row["active_policy_events"] = ""
    return rows


def set_ratio(row: dict[str, str], column: str, numerator: float | None, denominator: float | None) -> None:
    if numerator is None or denominator in (None, 0):
        row[column] = ""
        return
    row[column] = f"{numerator / denominator:.6f}"


def parse_number(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def order_columns(fieldnames: list[str]) -> list[str]:
    priority = [
        "district_id",
        "year",
        "state",
        "district_name",
        "county_fips",
        "urbanicity",
        "enrollment",
    ]
    remaining = sorted(column for column in fieldnames if column not in priority)
    return [column for column in priority if column in fieldnames] + remaining
