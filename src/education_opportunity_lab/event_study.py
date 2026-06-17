from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from education_opportunity_lab.pipeline import parse_int, parse_number, read_csv, write_csv


def _normalize_policy_type(policy_type: str) -> str:
    return policy_type.strip().replace(" ", "_").replace("-", "_")


def add_relative_time(
    rows: list[dict[str, str]],
    events: list[dict[str, str]],
    policy_type: str,
) -> list[dict[str, str]]:
    """Add years_since_{policy_type} and post_{policy_type} columns to each row.

    Uses the earliest matching event year per state. Rows with no matching state
    event receive empty strings for both columns.
    """
    norm_type = _normalize_policy_type(policy_type)
    rel_col = f"years_since_{norm_type}"
    post_col = f"post_{norm_type}"

    # Earliest event year per state for this policy type
    state_event_year: dict[str, int] = {}
    for event in events:
        if event.get("policy_type", "").strip() != policy_type.strip():
            continue
        state = event.get("state", "")
        event_year = parse_int(event.get("event_year"))
        if state and event_year is not None:
            if state not in state_event_year or event_year < state_event_year[state]:
                state_event_year[state] = event_year

    for row in rows:
        state = row.get("state", "")
        year = parse_int(row.get("year"))
        event_year = state_event_year.get(state)

        if event_year is None or year is None:
            row[rel_col] = ""
            row[post_col] = ""
        else:
            rel = year - event_year
            row[rel_col] = str(rel)
            row[post_col] = "1" if rel >= 0 else "0"

    return rows


def demean_within_district(
    rows: list[dict[str, str]],
    numeric_columns: list[str],
) -> list[dict[str, str]]:
    """Add {col}_demeaned columns by subtracting each district's mean from numeric columns."""
    district_sums: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    district_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for row in rows:
        district_id = row.get("district_id", "")
        for col in numeric_columns:
            val = parse_number(row.get(col))
            if val is not None:
                district_sums[district_id][col] += val
                district_counts[district_id][col] += 1

    district_means: dict[str, dict[str, float]] = {
        district_id: {
            col: district_sums[district_id][col] / district_counts[district_id][col]
            for col in numeric_columns
            if district_counts[district_id][col] > 0
        }
        for district_id in district_sums
    }

    for row in rows:
        district_id = row.get("district_id", "")
        means = district_means.get(district_id, {})
        for col in numeric_columns:
            demeaned_col = f"{col}_demeaned"
            val = parse_number(row.get(col))
            mean = means.get(col)
            if val is not None and mean is not None:
                row[demeaned_col] = f"{val - mean:.6f}"
            else:
                row[demeaned_col] = ""

    return rows


def build_event_study_panel(
    panel_rows: list[dict[str, str]],
    events: list[dict[str, str]],
    policy_type: str,
    window: tuple[int, int] = (-5, 5),
) -> list[dict[str, str]]:
    """Filter panel to event window, add relative-time columns, return enriched rows.

    Only rows where years_since_{policy_type} is within [window[0], window[1]] are kept.
    Rows with no matching event are excluded.
    """
    enriched = add_relative_time(list(panel_rows), events, policy_type)
    norm_type = _normalize_policy_type(policy_type)
    rel_col = f"years_since_{norm_type}"

    lo, hi = window
    result: list[dict[str, str]] = []
    for row in enriched:
        rel_raw = row.get(rel_col, "")
        if not rel_raw:
            continue
        rel = parse_int(rel_raw)
        if rel is None:
            continue
        if lo <= rel <= hi:
            result.append(row)

    return result


def _parse_window(value: str) -> tuple[int, int]:
    if ":" in value:
        lo, hi = value.split(":", 1)
        return int(lo), int(hi)
    raise ValueError(f"Window must be in lo:hi format, got: {value!r}")


def _detect_numeric_columns(rows: list[dict[str, str]], exclude: set[str]) -> list[str]:
    if not rows:
        return []
    cols = list(rows[0].keys())
    numeric: list[str] = []
    for col in cols:
        if col in exclude:
            continue
        for row in rows[:50]:
            val = row.get(col, "")
            if val and parse_number(val) is not None:
                numeric.append(col)
                break
    return numeric


def build_event_study_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an event-study panel from a district-year panel and policy events."
    )
    parser.add_argument("--panel", required=True, help="Panel CSV path.")
    parser.add_argument("--events", required=True, help="Policy events CSV path.")
    parser.add_argument("--output", required=True, help="Output event-study CSV path.")
    parser.add_argument("--policy-type", required=True, help="Policy type to build the event study around.")
    parser.add_argument("--window", default="-5:5", help="Relative-time window in lo:hi format (default: -5:5).")
    parser.add_argument("--demean", action="store_true", help="Add within-district demeaned columns.")
    parser.add_argument(
        "--demean-columns",
        default="",
        help="Comma-separated columns to demean (default: all detected numeric columns).",
    )
    args = parser.parse_args(argv)

    panel_rows = read_csv(args.panel)
    events = read_csv(args.events)
    window = _parse_window(args.window)

    result = build_event_study_panel(panel_rows, events, args.policy_type, window)

    if args.demean and result:
        non_numeric = {
            "district_id", "year", "state", "district_name", "county_fips",
            "urbanicity", "active_policy_events",
        }
        if args.demean_columns:
            cols_to_demean = [c.strip() for c in args.demean_columns.split(",") if c.strip()]
        else:
            cols_to_demean = _detect_numeric_columns(result, non_numeric)
        result = demean_within_district(result, cols_to_demean)

    write_csv(result, args.output)
    norm_type = _normalize_policy_type(args.policy_type)
    print(f"Wrote {len(result)} rows to {args.output}")
    print(f"Relative-time column: years_since_{norm_type}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build_event_study_main())
