# Roadmap

## Phase 1: Stable Panel Contract

- Define district-year schema.
- Normalize CCD, F-33, ACS/SAIPE, CRDC, special education, outcomes, crime, and policy inputs.
- Build reproducible joins and validation.
- Keep source files immutable under `data/raw`.

## Phase 2: Source Extractors

- Add NCES CCD extractors by year.
- Add NCES F-33 extractors by fiscal year.
- Add CRDC normalization for discipline and access fields.
- Add ACS/SAIPE district geography crosswalk logic.
- Add county crime normalization and agency-to-county aggregation rules.

## Phase 3: Outcomes and Causal Features

- Add EDFacts assessment inputs.
- Add source-specific graduation, attendance, dropout, and postsecondary outcome extractors.
- Add treatment timing tables for school finance reforms, school choice, and teacher pay reforms.
- Add district fixed-effect and event-study-ready outputs.

## Phase 4: Reports

- America's Most Improved School Districts.
- Districts Delivering the Best Outcomes Per Dollar.
- Where Education Spending Works Best.
- Districts in Decline.
- The Infrastructure Gap Report.
