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

| Source | Script | Output |
| ------ | ------ | ------ |
| Urban Institute CCD + F-33 + Special Ed | `fetch_urban_district_data.py` | `ccd.csv`, `f33.csv`, `special_education.csv` |
| Census SAIPE + ACS 5-year | `fetch_census_district_data.py` | `acs.csv` |
| Urban Institute CRDC | `fetch_crdc_data.py` | `crdc.csv` (biennial: 2012, 2014, 2016, 2018, 2021) |
| FBI UCR (downloaded files) | `normalize_crime_data.py` | `crime.csv` |

## Phase 3: Outcomes and Causal Features — In Progress

- ✅ EDFacts assessment inputs (math/reading proficiency via Urban Institute).
- ✅ Graduation rate extractors (`eol-fetch-edfacts`).
- ✅ District fixed-effect and event-study-ready outputs (`eol-build-event-study`).
- ✅ Treatment timing framework (relative-time columns, within-district demeaning).
- Attendance, dropout, and postsecondary outcome extractors (requires state-level data or EDFacts expansion).

### Event-study usage

```bash
# Build an event-study panel around funding reforms, ±5 years, with demeaned columns
eol-build-event-study \
  --panel data/processed/district_year_panel.csv \
  --events samples/policy_events.csv \
  --policy-type funding_reform \
  --window -5:5 \
  --demean \
  --output data/processed/event_study_funding_reform.csv
```

## Phase 4: Reports

- America's Most Improved School Districts.
- Districts Delivering the Best Outcomes Per Dollar.
- Where Education Spending Works Best.
- Districts in Decline.
- The Infrastructure Gap Report.
