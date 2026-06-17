from __future__ import annotations

import json
from pathlib import Path

from education_opportunity_lab.pipeline import parse_number, read_csv


class SchemaValidationError(ValueError):
    """Raised when a panel file does not match the configured schema."""


def load_schema(path: str | Path) -> dict[str, dict[str, str]]:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_panel(panel_path: str | Path, schema_path: str | Path) -> list[str]:
    rows = read_csv(panel_path)
    schema = load_schema(schema_path)
    required = schema.get("required_columns", {})
    optional = schema.get("optional_columns", {})
    expected = {**required, **optional}

    if not rows:
        raise SchemaValidationError("Panel is empty.")

    actual_columns = set(rows[0].keys())
    missing = [column for column in required if column not in actual_columns]
    if missing:
        raise SchemaValidationError(f"Missing required columns: {', '.join(missing)}")

    errors: list[str] = []
    for row_number, row in enumerate(rows, start=2):
        for column, expected_type in expected.items():
            if column not in row or row[column] == "":
                if column in required:
                    errors.append(f"line {row_number}: required column {column} is blank")
                continue
            if not value_matches_type(row[column], expected_type):
                errors.append(
                    f"line {row_number}: column {column} expected {expected_type}, got {row[column]!r}"
                )

    if errors:
        raise SchemaValidationError("; ".join(errors[:20]))

    return sorted(actual_columns)


def value_matches_type(value: str, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        number = parse_number(value)
        return number is not None and number.is_integer()
    if expected_type == "number":
        return parse_number(value) is not None
    raise SchemaValidationError(f"Unknown schema type: {expected_type}")
