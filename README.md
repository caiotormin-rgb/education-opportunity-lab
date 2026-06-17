# Education Opportunity Lab

A reproducible pipeline that assembles a longitudinal, district-year panel dataset for studying education finance, demographics, student outcomes, equity, public safety context, and state policy events across U.S. school districts.

**Unit of analysis:** one row per `district_id × year`

The [NCES district identifier](https://nces.ed.gov/ccd/) is the primary key. The Common Core of Data (CCD) acts as the backbone; all other sources are left-joined onto the district-year grain so no CCD district is dropped.

---

## Why This Exists

Education research is hampered by data fragmentation. Finance lives in F-33, demographics in ACS/SAIPE, discipline and access in CRDC, achievement in EDFacts, and policy shocks in scattered state-level records. This project normalizes each source to a shared district-year contract and joins them into a single analysis-ready panel — reproducibly, from raw public files.

Research questions the panel is designed to answer:

- Which districts beat demographic expectations over time?
- Where does additional spending appear most effective?
- Does instructional spending outperform administrative spending as a predictor of outcomes?
- Do infrastructure investments precede measurable gains?
- Do above-market teacher salaries correlate with better outcomes after controlling for context?

---

## Repository Layout

```text
config/
  panel_schema.json        Required and optional output field definitions
  sources.json             Data source manifest and join contracts
data/
  raw/                     Downloaded source files (not committed)
  interim/                 Normalized extracts (not committed)
  processed/               Built district-year panel (not committed)
docs/
  data_dictionary.md       Field-level definitions for all ~80 columns
  roadmap.md               Phased implementation plan
samples/
  *.csv                    Tiny normalized inputs for local development and tests
scripts/
  build_panel.py           CLI entry point for panel construction
  validate_panel.py        CLI entry point for schema validation
  fetch_urban_district_data.py   CCD, F-33, special education via Urban Institute API
  fetch_census_district_data.py  SAIPE + ACS demographics via Census Bureau API
  fetch_crdc_data.py       CRDC discipline and access via Urban Institute API
  normalize_crime_data.py  FBI UCR agency files → county-year crime rates
  fetch_edfacts_data.py             EDFacts proficiency, graduation, dropout, attendance
  build_event_study.py              Event-study panel builder with relative-time columns
  report_most_improved.py           Most Improved School Districts
  report_best_outcomes_per_dollar.py Best Outcomes Per Dollar
  report_spending_effectiveness.py  Where Spending Works Best
  report_districts_in_decline.py    Districts in Decline
  report_infrastructure_gap.py      Infrastructure Gap Report
src/education_opportunity_lab/
  pipeline.py              Join and feature engineering logic
  schema.py                Schema validation helpers
  urban_api.py             Urban Institute Education Data Portal client
  census_api.py            Census Bureau SAIPE and ACS 5-year client
  crdc_api.py              CRDC discipline, access, and absenteeism client
  crime_normalizer.py      FBI UCR file-based county crime normalizer
  edfacts_api.py           EDFacts assessment, graduation, dropout, and attendance client
  event_study.py           Relative-time, demeaning, and event-study panel helpers
  reports.py               Analytical report functions (OLS trend, efficiency, gap scoring)
  cli.py                   Installed CLI entry points
tests/
  test_pipeline.py         Join, derived-field, and policy flag tests
  test_sources.py          Per-source normalizer and rate computation tests
  test_reports.py          Analytical scoring and report output tests
```

---

## Quick Start

**Requirements:** Python 3.10+

```bash
# Install the package in editable mode
pip install -e .

# Build the panel from sample data
python3 scripts/build_panel.py --input-dir samples --output data/processed/district_year_panel.csv

# Validate the output against the schema
python3 scripts/validate_panel.py data/processed/district_year_panel.csv

# Run tests
python3 -m unittest discover -s tests
```

Or use the installed CLI commands:

```bash
eol-build-panel --input-dir samples --output data/processed/district_year_panel.csv
eol-validate-panel data/processed/district_year_panel.csv
```

---

## Notebooks

The `notebooks/` directory contains exploratory analyses. They require extra dependencies not needed by the pipeline itself.

**Set up a conda environment:**

```bash
conda create -n eol python=3.11 -y
conda activate eol
conda install -y jupyter pandas numpy matplotlib ipykernel
pip install -e .
python -m ipykernel install --user --name eol --display-name "Education Opportunity Lab"
```

Or install the optional notebook extras directly into any Python environment:

```bash
pip install -e ".[notebooks]"
```

Then open JupyterLab/Notebook and select the **"Education Opportunity Lab"** kernel.

---

## Fetching Real Data

Each source has a dedicated extractor. Run them independently; their outputs drop into a shared interim directory for `build_panel`.

### CCD, F-33, Special Education — Urban Institute API

```bash
eol-fetch-urban --years 2015:2022 --output-dir data/interim/urban
```

### Demographics — Census SAIPE + ACS 5-year

No API key required. Fetches poverty rate, median income, education attainment, employment, housing burden, single-parent rate, and foreign-born share for every school district.

```bash
eol-fetch-census --years 2015:2022 --output-dir data/interim/census
```

### CRDC Discipline and Access — Urban Institute API

CRDC is biennial (2012, 2014, 2016, 2018, 2021). Produces suspension rates, AP/gifted participation, and chronic absenteeism rates at the district level.

```bash
eol-fetch-crdc --output-dir data/interim/crdc
```

### County Crime — FBI UCR Files

Download the UCR Agencies and Offenses CSV files from [FBI Crime Data Explorer](https://cde.fbi.gov/downloads), then normalize them to county-year crime rates.

```bash
eol-normalize-crime \
  --agencies data/raw/ucr_agencies_2022.csv \
  --offenses data/raw/ucr_offenses_2022.csv \
  --output data/interim/crime/crime.csv
```

### Outcomes — Urban Institute EDFacts API

Fetches math/reading proficiency midpoints and graduation rates from the EDFacts reporting system.

```bash
eol-fetch-edfacts --years 2012:2022 --output-dir data/interim/edfacts
```

### Build the Panel

Merge all normalized sources into a single district-year panel:

```bash
# Combine interim directories (copy or symlink the CSVs into one directory)
eol-build-panel --input-dir data/interim/combined --output data/processed/district_year_panel.csv
eol-validate-panel data/processed/district_year_panel.csv
```

### Build an Event-Study Panel (Phase 3)

Filters the panel to a treatment window around a state policy event, adds relative-time columns, and optionally adds within-district demeaned versions of all numeric columns.

```bash
eol-build-event-study \
  --panel data/processed/district_year_panel.csv \
  --events samples/policy_events.csv \
  --policy-type funding_reform \
  --window -5:5 \
  --demean \
  --output data/processed/event_study_funding_reform.csv
```

---

## Data Sources

| Source | Extractor | Description | Join Key |
| ------ | --------- | ----------- | -------- |
| **CCD** (backbone) | `eol-fetch-urban` | District directory, enrollment, staffing | `district_id, year` |
| **F-33** | `eol-fetch-urban` | District finance — revenue, expenditure | `district_id, year` |
| **SAIPE + ACS** | `eol-fetch-census` | Demographics, income, poverty, attainment | `district_id, year` |
| **CRDC** | `eol-fetch-crdc` | Discipline, equity, access (biennial) | `district_id, year` |
| **Special Education** | `eol-fetch-urban` | IDEA enrollment, spending, placement | `district_id, year` |
| **EDFacts** | `eol-fetch-edfacts` | Proficiency, graduation rates | `district_id, year` |
| **Crime** | `eol-normalize-crime` | County violent and property crime rates | `county_fips, year` |
| **Policy Events** | Manual / `samples/` | Finance reform, teacher pay, school choice | `state, year` |

See [docs/data_dictionary.md](docs/data_dictionary.md) for field-level documentation across all ~80 columns.

---

## Normalized Input Contracts

The pipeline reads normalized CSVs from an input directory. Missing optional files are silently skipped — only `ccd.csv` is required.

| File | Required |
| ---- | -------- |
| `ccd.csv` | Yes |
| `f33.csv` | No |
| `acs.csv` | No |
| `crdc.csv` | No |
| `special_education.csv` | No |
| `outcomes.csv` | No |
| `crime.csv` | No |
| `policy_events.csv` | No |

---

## Panel Coverage

The current schema covers ~80 fields across six domains:

- **Backbone** — district identity, enrollment, staffing, urbanicity
- **Finance** — revenue by source, expenditure by function, per-pupil ratios, funding shares
- **Demographics** — income, poverty, education attainment, employment, housing, language
- **Equity & Access** — suspension, absenteeism, AP and gifted participation
- **Special Education** — enrollment, staffing, spending, placement rates (inclusion vs. separate setting)
- **Outcomes** — math/reading proficiency, graduation, attendance, dropout, college enrollment
- **Context** — county crime rates, federal program revenue (IDEA, ESSER), policy event flags

---

## Phase 4 Reports

Five analytical reports produce ranked district lists from any built panel:

```bash
# America's Most Improved School Districts
eol-report-most-improved \
  --panel data/processed/district_year_panel.csv \
  --output data/processed/report_most_improved.csv

# Districts Delivering the Best Outcomes Per Dollar
eol-report-best-per-dollar \
  --panel data/processed/district_year_panel.csv \
  --output data/processed/report_best_per_dollar.csv

# Where Education Spending Works Best
eol-report-spending-effectiveness \
  --panel data/processed/district_year_panel.csv \
  --output data/processed/report_spending_effectiveness.csv

# Districts in Decline
eol-report-in-decline \
  --panel data/processed/district_year_panel.csv \
  --output data/processed/report_in_decline.csv

# The Infrastructure Gap Report
eol-report-infrastructure-gap \
  --panel data/processed/district_year_panel.csv \
  --output data/processed/report_infrastructure_gap.csv
```

Each report accepts `--top-n` (default 100) and `--min-years` where applicable.

---

## Roadmap

| Phase | Status | Goal |
| ----- | ------ | ---- |
| 1 | Complete | Stable district-year schema, join pipeline, validation, sample data |
| 2 | Complete | Source extractors for CCD, F-33, CRDC, ACS/SAIPE, crime |
| 3 | Complete | EDFacts outcomes, dropout/attendance, event-study panel builder |
| 4 | Complete | Analytical reports — Most Improved, Best Per Dollar, Spending Effectiveness, Decline, Infrastructure Gap |

See [docs/roadmap.md](docs/roadmap.md) for details.

---

## License

This project is open source. Data sources are public federal and state datasets. See individual source documentation for terms of use.
