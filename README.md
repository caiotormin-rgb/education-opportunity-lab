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
  fetch_urban_district_data.py   Pulls real data from the Urban Institute API
  validate_panel.py        CLI entry point for schema validation
src/education_opportunity_lab/
  pipeline.py              Join and feature engineering logic
  schema.py                Schema validation helpers
  urban_api.py             Urban Institute Education Data Portal client
  cli.py                   Installed CLI entry points
tests/
  test_pipeline.py         Unit tests for joins, derived fields, and policy flags
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

## Fetching Real Data (Urban Institute API)

The first real-data loader pulls district-level CCD directory and F-33 finance data from the [Urban Institute Education Data Portal](https://educationdata.urban.org/).

```bash
# Fetch district data for 2020–2022
python3 scripts/fetch_urban_district_data.py --years 2020:2022 --output-dir data/interim/urban

# Build the panel from the fetched data
python3 scripts/build_panel.py --input-dir data/interim/urban --output data/processed/district_year_panel_urban.csv

# Validate
python3 scripts/validate_panel.py data/processed/district_year_panel_urban.csv
```

---

## Data Sources

| Source | Description | Join Key |
| ------ | ----------- | -------- |
| **CCD** (backbone) | District directory, enrollment, staffing | `district_id, year` |
| **F-33** | District finance — revenue, expenditure | `district_id, year` |
| **ACS / SAIPE** | Demographics, income, poverty | `district_id, year` |
| **CRDC** | Discipline, equity, access indicators | `district_id, year` |
| **Special Education** | IDEA enrollment, spending, placement rates | `district_id, year` |
| **Outcomes** | Proficiency, graduation, attendance, dropout | `district_id, year` |
| **Crime** | County violent and property crime rates | `county_fips, year` |
| **Policy Events** | Finance reform, teacher pay, school choice flags | `state, year` |

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

## Roadmap

| Phase | Status | Goal |
| ----- | ------ | ---- |
| 1 | Complete | Stable district-year schema, join pipeline, validation, sample data |
| 2 | In progress | Source extractors for CCD, F-33, CRDC, ACS/SAIPE, crime |
| 3 | Planned | EDFacts outcomes, graduation/attendance extractors, event-study outputs |
| 4 | Planned | Annual reports — Most Improved, Best Outcomes Per Dollar, Infrastructure Gap |

See [docs/roadmap.md](docs/roadmap.md) for details.

---

## License

This project is open source. Data sources are public federal and state datasets. See individual source documentation for terms of use.
