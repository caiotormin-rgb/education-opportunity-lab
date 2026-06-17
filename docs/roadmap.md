# Roadmap

## Phase 1: Stable Panel Contract — Complete

- Define district-year schema.
- Normalize CCD, F-33, ACS/SAIPE, CRDC, special education, outcomes, crime, and policy inputs.
- Build reproducible joins and validation.
- Keep source files immutable under `data/raw`.

## Phase 2: Source Extractors — Complete

- NCES CCD extractors by year (`eol-fetch-urban`).
- NCES F-33 extractors by fiscal year (`eol-fetch-urban`).
- CRDC normalization for discipline, access, and chronic absenteeism (`eol-fetch-crdc`).
- Census SAIPE + ACS district demographics crosswalk (`eol-fetch-census`).
- FBI UCR county crime normalization and agency-to-county aggregation (`eol-normalize-crime`).

### Source details

| Source | CLI | Output |
| ------ | --- | ------ |
| Urban Institute CCD + F-33 + Special Ed | `eol-fetch-urban` | `ccd.csv`, `f33.csv`, `special_education.csv` |
| Census SAIPE + ACS 5-year | `eol-fetch-census` | `acs.csv` |
| Urban Institute CRDC | `eol-fetch-crdc` | `crdc.csv` (biennial: 2012, 2014, 2016, 2018, 2021) |
| FBI UCR (downloaded files) | `eol-normalize-crime` | `crime.csv` |

## Phase 3: Outcomes and Causal Features — Complete

- ✅ EDFacts assessment inputs (math/reading proficiency via Urban Institute).
- ✅ Graduation rate extractors (`eol-fetch-edfacts`).
- ✅ Dropout rate extractors from EDFacts (`eol-fetch-edfacts`).
- ✅ Attendance rate proxy from chronic absenteeism (`eol-fetch-edfacts`).
- ✅ District fixed-effect and event-study-ready outputs (`eol-build-event-study`).
- ✅ Treatment timing framework (relative-time columns, within-district demeaning).

Note: college enrollment rate requires NSC (National Student Clearinghouse) data, which requires institutional access. The column is reserved in the schema but left blank by extractors.

### Event-study usage

```bash
eol-build-event-study \
  --panel data/processed/district_year_panel.csv \
  --events samples/policy_events.csv \
  --policy-type funding_reform \
  --window -5:5 \
  --demean \
  --output data/processed/event_study_funding_reform.csv
```

## Phase 4: Reports — Complete

Five analytical reports rank districts on distinct dimensions. Each accepts `--panel`, `--output`, and `--top-n` flags.

| CLI | Report | Ranking signal |
| --- | ------ | -------------- |
| `eol-report-most-improved` | Most Improved School Districts | OLS trend slope on outcome composite |
| `eol-report-best-per-dollar` | Best Outcomes Per Dollar | Outcome composite ÷ spending per $10k |
| `eol-report-spending-effectiveness` | Where Spending Works Best | Outcome growth per unit of spending growth |
| `eol-report-in-decline` | Districts in Decline | Steepest negative outcome trend |
| `eol-report-infrastructure-gap` | Infrastructure Gap | Lowest capital investment share of total spending |

### Example usage

```bash
# Most improved districts over the panel period (requires ≥3 years of outcome data)
eol-report-most-improved \
  --panel data/processed/district_year_panel.csv \
  --output data/processed/report_most_improved.csv \
  --min-years 3

# Districts with lowest capital investment share
eol-report-infrastructure-gap \
  --panel data/processed/district_year_panel.csv \
  --output data/processed/report_infrastructure_gap.csv \
  --top-n 200
```

### Outcome composite

The composite used across reports is a weighted mean of available outcome metrics:

| Metric | Weight |
| ------ | ------ |
| `math_proficiency_rate` | 1.0 |
| `reading_proficiency_rate` | 1.0 |
| `graduation_rate` | 1.5 |
| `attendance_rate` | 0.5 |

Missing metrics are excluded from the weighted mean rather than treated as zero.
