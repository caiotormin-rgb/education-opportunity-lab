from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

from education_opportunity_lab.pipeline import parse_int, parse_number, read_csv, write_csv


# Outcome columns used for composite scoring, in priority order
OUTCOME_COLUMNS = [
    "math_proficiency_rate",
    "reading_proficiency_rate",
    "graduation_rate",
    "attendance_rate",
]

# Higher weights on graduation (long-run signal) and proficiency (core academic)
OUTCOME_WEIGHTS: dict[str, float] = {
    "math_proficiency_rate": 1.0,
    "reading_proficiency_rate": 1.0,
    "graduation_rate": 1.5,
    "attendance_rate": 0.5,
}

# Spending values below this are treated as data errors (e.g. $10/student)
MIN_SPENDING_PER_STUDENT: float = 2_000.0

# Districts whose last data year lags the panel max by more than this are excluded
DEFAULT_MAX_STALE_YEARS: int = 5

# Recency weight half-life: efficiency halves every this many years of lag
RECENCY_HALF_LIFE_YEARS: int = 3


# ---------------------------------------------------------------------------
# Core statistical helpers
# ---------------------------------------------------------------------------

def compute_linear_trend(pairs: list[tuple[int, float]]) -> float | None:
    """OLS slope for (x, y) pairs; returns None if fewer than 2 points or zero x-variance."""
    n = len(pairs)
    if n < 2:
        return None
    x_mean = sum(p[0] for p in pairs) / n
    y_mean = sum(p[1] for p in pairs) / n
    ss_xx = sum((p[0] - x_mean) ** 2 for p in pairs)
    if ss_xx == 0.0:
        return None
    ss_xy = sum((p[0] - x_mean) * (p[1] - y_mean) for p in pairs)
    return ss_xy / ss_xx


def _panel_max_year(rows: list[dict[str, str]]) -> int | None:
    """Return the most recent year present anywhere in the panel."""
    years = [parse_int(r.get("year")) for r in rows]
    valid = [y for y in years if y is not None]
    return max(valid) if valid else None


def _recency_weight(data_year: int, reference_year: int, half_life: int = RECENCY_HALF_LIFE_YEARS) -> float:
    """Exponential decay weight relative to the panel's most recent year.

    Returns 1.0 for current data, halving every `half_life` years of lag.
    """
    lag = max(0, reference_year - data_year)
    return 0.5 ** (lag / half_life)


def compute_outcome_composite(
    row: dict[str, str],
    outcome_cols: list[str] | None = None,
    weights: dict[str, float] | None = None,
) -> float | None:
    """Weighted mean of available outcome metrics; returns None if no metrics are present."""
    cols = outcome_cols if outcome_cols is not None else OUTCOME_COLUMNS
    wts = weights if weights is not None else OUTCOME_WEIGHTS
    total_weight = 0.0
    weighted_sum = 0.0
    for col in cols:
        val = parse_number(row.get(col))
        if val is None:
            continue
        w = wts.get(col, 1.0)
        weighted_sum += val * w
        total_weight += w
    return weighted_sum / total_weight if total_weight > 0 else None


def _group_by_district(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        did = row.get("district_id", "")
        if did:
            groups[did].append(row)
    return groups


def _latest(district_rows: list[dict[str, str]]) -> dict[str, str]:
    return max(district_rows, key=lambda r: parse_int(r.get("year")) or 0)


def _earliest(district_rows: list[dict[str, str]]) -> dict[str, str]:
    return min(district_rows, key=lambda r: parse_int(r.get("year")) or 9999)


def _fmt(v: float, places: int = 6) -> str:
    return f"{v:.{places}f}"


# ---------------------------------------------------------------------------
# Report 1: Most Improved
# ---------------------------------------------------------------------------

def most_improved_districts(
    rows: list[dict[str, str]],
    min_years: int = 3,
    top_n: int = 100,
    ascending: bool = False,
    max_stale_years: int = DEFAULT_MAX_STALE_YEARS,
) -> list[dict[str, str]]:
    """Rank districts by OLS outcome-composite trend slope.

    ascending=False → most improved first (default).
    ascending=True  → most declined first (used by districts_in_decline).
    Districts whose most recent outcome data lags the panel max year by more than
    max_stale_years are excluded so outdated trends don't dominate the ranking.
    """
    panel_max = _panel_max_year(rows)
    groups = _group_by_district(rows)
    scored: list[dict[str, str]] = []

    for district_id, district_rows in groups.items():
        pairs: list[tuple[int, float]] = []
        for row in district_rows:
            year = parse_int(row.get("year"))
            composite = compute_outcome_composite(row)
            if year is not None and composite is not None:
                pairs.append((year, composite))

        if len(pairs) < min_years:
            continue

        pairs.sort(key=lambda p: p[0])

        if panel_max is not None and (panel_max - pairs[-1][0]) > max_stale_years:
            continue

        slope = compute_linear_trend(pairs)
        if slope is None:
            continue

        latest = _latest(district_rows)
        scored.append({
            "district_id": district_id,
            "district_name": latest.get("district_name", ""),
            "state": latest.get("state", ""),
            "urbanicity": latest.get("urbanicity", ""),
            "enrollment": latest.get("enrollment", ""),
            "initial_outcome": _fmt(pairs[0][1], 4),
            "final_outcome": _fmt(pairs[-1][1], 4),
            "improvement_rate_per_year": _fmt(slope),
            "years_of_data": str(len(pairs)),
            "first_year": str(pairs[0][0]),
            "last_year": str(pairs[-1][0]),
        })

    scored.sort(
        key=lambda r: float(r["improvement_rate_per_year"]),
        reverse=not ascending,
    )
    return scored[:top_n]


# ---------------------------------------------------------------------------
# Report 2: Best Outcomes Per Dollar
# ---------------------------------------------------------------------------

def best_outcomes_per_dollar(
    rows: list[dict[str, str]],
    top_n: int = 100,
    min_spending: float = MIN_SPENDING_PER_STUDENT,
    max_stale_years: int = DEFAULT_MAX_STALE_YEARS,
) -> list[dict[str, str]]:
    """Rank districts by recency-adjusted outcome composite per $10k of spending.

    Two guards against distortion:
    - min_spending: rows with spending_per_student below this are treated as data
      errors and excluded (catches $10/student anomalies).
    - Recency weight: efficiency is multiplied by an exponential decay factor so
      districts with stale data cannot outscore districts with current data.
      Districts lagging the panel max by more than max_stale_years are dropped.
    """
    panel_max = _panel_max_year(rows)
    groups = _group_by_district(rows)
    scored: list[dict[str, str]] = []

    for district_id, district_rows in groups.items():
        qualified = [
            r for r in district_rows
            if compute_outcome_composite(r) is not None
            and (parse_number(r.get("spending_per_student")) or 0) >= min_spending
        ]
        if not qualified:
            continue

        row = max(qualified, key=lambda r: parse_int(r.get("year")) or 0)
        data_year = parse_int(row.get("year"))

        if panel_max is not None and data_year is not None and (panel_max - data_year) > max_stale_years:
            continue

        outcome = compute_outcome_composite(row)
        spending = parse_number(row.get("spending_per_student"))
        if outcome is None or spending is None or spending < min_spending:
            continue

        raw_efficiency = outcome / (spending / 10_000)
        weight = _recency_weight(data_year, panel_max) if (data_year is not None and panel_max is not None) else 1.0
        weighted_efficiency = raw_efficiency * weight

        scored.append({
            "district_id": district_id,
            "district_name": row.get("district_name", ""),
            "state": row.get("state", ""),
            "urbanicity": row.get("urbanicity", ""),
            "enrollment": row.get("enrollment", ""),
            "year": row.get("year", ""),
            "spending_per_student": f"{spending:.0f}",
            "outcome_composite": _fmt(outcome, 4),
            "raw_efficiency_score": _fmt(raw_efficiency),
            "recency_weight": _fmt(weight, 4),
            "efficiency_score": _fmt(weighted_efficiency),
            "poverty_rate": row.get("poverty_rate", ""),
            "median_income": row.get("median_income", ""),
        })

    scored.sort(key=lambda r: float(r["efficiency_score"]), reverse=True)
    return scored[:top_n]


# ---------------------------------------------------------------------------
# Report 3: Spending Effectiveness
# ---------------------------------------------------------------------------

def spending_effectiveness(
    rows: list[dict[str, str]],
    min_years: int = 3,
    top_n: int = 100,
    min_spending: float = MIN_SPENDING_PER_STUDENT,
    max_stale_years: int = DEFAULT_MAX_STALE_YEARS,
) -> list[dict[str, str]]:
    """Rank districts by outcome growth per unit of spending growth (spending elasticity).

    Spending rows below min_spending are excluded to avoid data errors inflating
    the trend. Districts whose most recent data lags the panel max by more than
    max_stale_years are excluded so stale elasticity estimates don't dominate.
    """
    panel_max = _panel_max_year(rows)
    groups = _group_by_district(rows)
    results: list[dict[str, str]] = []

    for district_id, district_rows in groups.items():
        spending_pairs: list[tuple[int, float]] = []
        outcome_pairs: list[tuple[int, float]] = []

        for row in district_rows:
            year = parse_int(row.get("year"))
            spending = parse_number(row.get("spending_per_student"))
            outcome = compute_outcome_composite(row)
            if year is not None and spending is not None and spending >= min_spending:
                spending_pairs.append((year, spending))
            if year is not None and outcome is not None:
                outcome_pairs.append((year, outcome))

        if len(spending_pairs) < min_years or len(outcome_pairs) < min_years:
            continue

        spending_pairs.sort(key=lambda p: p[0])
        outcome_pairs.sort(key=lambda p: p[0])

        last_spending_year = spending_pairs[-1][0]
        last_outcome_year = outcome_pairs[-1][0]
        last_year = max(last_spending_year, last_outcome_year)
        if panel_max is not None and (panel_max - last_year) > max_stale_years:
            continue

        spending_slope = compute_linear_trend(spending_pairs)
        outcome_slope = compute_linear_trend(outcome_pairs)
        if spending_slope is None or outcome_slope is None:
            continue
        if abs(spending_slope) < 1.0:
            # Less than $1/year growth in spending — ratio is meaningless
            continue

        # Outcome improvement per $10k/year of additional spending
        elasticity = outcome_slope / (spending_slope / 10_000)

        latest = _latest(district_rows)
        results.append({
            "district_id": district_id,
            "district_name": latest.get("district_name", ""),
            "state": latest.get("state", ""),
            "urbanicity": latest.get("urbanicity", ""),
            "enrollment": latest.get("enrollment", ""),
            "last_year": str(last_year),
            "spending_slope_per_year": f"{spending_slope:.2f}",
            "outcome_slope_per_year": _fmt(outcome_slope),
            "spending_elasticity": _fmt(elasticity),
            "poverty_rate": latest.get("poverty_rate", ""),
            "median_income": latest.get("median_income", ""),
        })

    results.sort(key=lambda r: float(r["spending_elasticity"]), reverse=True)
    return results[:top_n]


# ---------------------------------------------------------------------------
# Report 4: Districts in Decline
# ---------------------------------------------------------------------------

def districts_in_decline(
    rows: list[dict[str, str]],
    min_years: int = 3,
    top_n: int = 100,
    max_stale_years: int = DEFAULT_MAX_STALE_YEARS,
) -> list[dict[str, str]]:
    """Rank districts with the most negative outcome trend (steepest decline first)."""
    all_scored = most_improved_districts(
        rows, min_years=min_years, top_n=len(rows), ascending=True, max_stale_years=max_stale_years
    )
    declining = [r for r in all_scored if float(r["improvement_rate_per_year"]) < 0]
    return declining[:top_n]


# ---------------------------------------------------------------------------
# Report 5: Infrastructure Gap
# ---------------------------------------------------------------------------

def infrastructure_gap(
    rows: list[dict[str, str]],
    top_n: int = 100,
    min_spending: float = MIN_SPENDING_PER_STUDENT,
    max_stale_years: int = DEFAULT_MAX_STALE_YEARS,
) -> list[dict[str, str]]:
    """Rank districts by capital investment share (lowest first = biggest infrastructure gap).

    Rows with spending_per_student below min_spending are excluded as likely data
    errors. Districts whose most recent spending data lags the panel max by more
    than max_stale_years are excluded so stale snapshots don't dominate.
    """
    panel_max = _panel_max_year(rows)
    groups = _group_by_district(rows)
    result: list[dict[str, str]] = []

    for district_id, district_rows in groups.items():
        q = [
            r for r in district_rows
            if (parse_number(r.get("capital_outlay_pp")) is not None
                and (parse_number(r.get("spending_per_student")) or 0) >= min_spending)
        ]
        if not q:
            continue

        row = max(q, key=lambda r: parse_int(r.get("year")) or 0)
        data_year = parse_int(row.get("year"))

        if panel_max is not None and data_year is not None and (panel_max - data_year) > max_stale_years:
            continue

        capital_pp = parse_number(row.get("capital_outlay_pp"))
        spending_pp = parse_number(row.get("spending_per_student"))
        if capital_pp is None or spending_pp is None or spending_pp < min_spending:
            continue

        capital_share = capital_pp / spending_pp
        outcome = compute_outcome_composite(row)

        result.append({
            "district_id": district_id,
            "district_name": row.get("district_name", ""),
            "state": row.get("state", ""),
            "urbanicity": row.get("urbanicity", ""),
            "enrollment": row.get("enrollment", ""),
            "year": row.get("year", ""),
            "capital_outlay_pp": f"{capital_pp:.0f}",
            "spending_per_student": f"{spending_pp:.0f}",
            "capital_share": _fmt(capital_share, 4),
            "outcome_composite": _fmt(outcome, 4) if outcome is not None else "",
            "poverty_rate": row.get("poverty_rate", ""),
            "median_income": row.get("median_income", ""),
        })

    # Sort ascending: lowest capital share = biggest gap
    result.sort(key=lambda r: float(r["capital_share"]))
    return result[:top_n]


# ---------------------------------------------------------------------------
# Shared CLI helpers
# ---------------------------------------------------------------------------

def _base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--panel", required=True, help="District-year panel CSV path.")
    parser.add_argument("--output", required=True, help="Output ranked CSV path.")
    parser.add_argument("--top-n", type=int, default=100, help="Number of districts to include (default: 100).")
    return parser


def _write_report(rows: list[dict[str, str]], output: str, label: str) -> int:
    write_csv(rows, output)
    print(f"Wrote {len(rows)} districts to {output}  [{label}]")
    return 0


# ---------------------------------------------------------------------------
# CLI entry points (one per report)
# ---------------------------------------------------------------------------

def _add_stale_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-stale-years",
        type=int,
        default=DEFAULT_MAX_STALE_YEARS,
        help=(
            "Exclude districts whose most recent data lags the panel max year by "
            "more than this many years (default: %(default)s)."
        ),
    )


def _add_spending_floor_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--min-spending",
        type=float,
        default=MIN_SPENDING_PER_STUDENT,
        help=(
            "Minimum plausible spending_per_student; rows below this are treated "
            "as data errors and excluded (default: %(default)s)."
        ),
    )


def most_improved_main(argv: list[str] | None = None) -> int:
    parser = _base_parser("Rank school districts by outcome improvement trend.")
    parser.add_argument("--min-years", type=int, default=3, help="Minimum years of outcome data required.")
    _add_stale_arg(parser)
    args = parser.parse_args(argv)
    rows = read_csv(args.panel)
    result = most_improved_districts(
        rows, min_years=args.min_years, top_n=args.top_n, max_stale_years=args.max_stale_years
    )
    return _write_report(result, args.output, "Most Improved")


def best_outcomes_per_dollar_main(argv: list[str] | None = None) -> int:
    parser = _base_parser("Rank districts by outcome composite per $10k of per-pupil spending.")
    _add_spending_floor_arg(parser)
    _add_stale_arg(parser)
    args = parser.parse_args(argv)
    rows = read_csv(args.panel)
    result = best_outcomes_per_dollar(
        rows, top_n=args.top_n, min_spending=args.min_spending, max_stale_years=args.max_stale_years
    )
    return _write_report(result, args.output, "Best Outcomes Per Dollar")


def spending_effectiveness_main(argv: list[str] | None = None) -> int:
    parser = _base_parser("Rank districts by outcome improvement per unit of spending growth.")
    parser.add_argument("--min-years", type=int, default=3, help="Minimum years of data required.")
    _add_spending_floor_arg(parser)
    _add_stale_arg(parser)
    args = parser.parse_args(argv)
    rows = read_csv(args.panel)
    result = spending_effectiveness(
        rows,
        min_years=args.min_years,
        top_n=args.top_n,
        min_spending=args.min_spending,
        max_stale_years=args.max_stale_years,
    )
    return _write_report(result, args.output, "Spending Effectiveness")


def districts_in_decline_main(argv: list[str] | None = None) -> int:
    parser = _base_parser("Rank districts with the steepest decline in outcomes.")
    parser.add_argument("--min-years", type=int, default=3, help="Minimum years of outcome data required.")
    _add_stale_arg(parser)
    args = parser.parse_args(argv)
    rows = read_csv(args.panel)
    result = districts_in_decline(rows, min_years=args.min_years, top_n=args.top_n, max_stale_years=args.max_stale_years)
    return _write_report(result, args.output, "Districts in Decline")


def infrastructure_gap_main(argv: list[str] | None = None) -> int:
    parser = _base_parser("Rank districts with the lowest capital investment share.")
    _add_spending_floor_arg(parser)
    _add_stale_arg(parser)
    args = parser.parse_args(argv)
    rows = read_csv(args.panel)
    result = infrastructure_gap(
        rows, top_n=args.top_n, min_spending=args.min_spending, max_stale_years=args.max_stale_years
    )
    return _write_report(result, args.output, "Infrastructure Gap")
