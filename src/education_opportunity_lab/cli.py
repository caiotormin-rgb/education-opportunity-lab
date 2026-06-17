from __future__ import annotations

import argparse
from pathlib import Path

from education_opportunity_lab.pipeline import build_panel, write_csv
from education_opportunity_lab.schema import SchemaValidationError, validate_panel


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = REPO_ROOT / "config" / "panel_schema.json"


def build_panel_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the district-year education panel.")
    parser.add_argument("--input-dir", required=True, help="Directory containing normalized CSV inputs.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    args = parser.parse_args(argv)

    result = build_panel(args.input_dir)
    write_csv(result.rows, args.output)
    print(f"Wrote {len(result.rows)} rows to {args.output}")
    if result.missing_optional_files:
        print("Missing optional files: " + ", ".join(result.missing_optional_files))
    return 0


def validate_panel_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a district-year panel CSV.")
    parser.add_argument("panel", help="Panel CSV path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Schema JSON path.")
    args = parser.parse_args(argv)

    try:
        columns = validate_panel(args.panel, args.schema)
    except SchemaValidationError as exc:
        print(f"Validation failed: {exc}")
        return 1

    print(f"Validation passed with {len(columns)} columns.")
    return 0
