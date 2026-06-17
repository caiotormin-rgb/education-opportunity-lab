# Data Dictionary

The panel grain is one row per `district_id` and `year`.

## Backbone Fields

| Field | Type | Description |
| --- | --- | --- |
| `district_id` | string | NCES district identifier. Preserved as text to avoid losing leading zeroes. |
| `year` | integer | School or fiscal year, using the ending calendar year convention. |
| `state` | string | Two-letter state abbreviation. Blank only where the source record omits it. |
| `district_name` | string | District name from CCD. Blank only where the source record omits it. |
| `county_fips` | string | Primary county FIPS used for contextual joins. |
| `urbanicity` | string | Locale or urbanicity category. |
| `enrollment` | number | Student enrollment. Blank for valid agencies where CCD does not report enrollment. |
| `school_count` | number | Number of schools in the district. |
| `teacher_count` | number | Teacher FTE count. |

## Finance Fields

| Field | Type | Description |
| --- | --- | --- |
| `total_revenue` | number | Total district revenue. |
| `local_revenue` | number | Local revenue. |
| `state_revenue` | number | State revenue. |
| `federal_revenue` | number | Federal revenue. |
| `property_tax_revenue` | number | Local property tax revenue. |
| `total_current_expenditure` | number | Current operating expenditure. |
| `instruction_spending` | number | Instructional expenditure. |
| `administration_spending` | number | Administrative expenditure. |
| `capital_outlay` | number | Capital outlay expenditure. |
| `spending_per_student` | number | `total_current_expenditure / enrollment`. |
| `instruction_spending_pp` | number | `instruction_spending / enrollment`. |
| `admin_spending_pp` | number | `administration_spending / enrollment`. |
| `capital_outlay_pp` | number | `capital_outlay / enrollment`. |
| `federal_funding_share` | number | `federal_revenue / total_revenue`. |
| `local_property_tax_share` | number | `property_tax_revenue / total_revenue`. |

## Demographic Controls

| Field | Type | Description |
| --- | --- | --- |
| `median_income` | number | Median household income. |
| `poverty_rate` | number | Poverty rate. |
| `adult_ba_plus_rate` | number | Adults with bachelor's degree or higher. |
| `single_parent_household_rate` | number | Share of households headed by a single parent. |
| `unemployment_rate` | number | Unemployment rate. |
| `housing_cost_burden_rate` | number | Share of households with high housing cost burden. |
| `foreign_born_rate` | number | Foreign-born population share. |
| `english_language_learners` | number | English learner count from CCD directory when available. |
| `migrant_students` | number | Migrant student count from CCD directory when available. |

## Equity and Access Fields

| Field | Type | Description |
| --- | --- | --- |
| `suspension_rate` | number | Student suspension rate. |
| `chronic_absenteeism_rate` | number | Chronic absenteeism rate. |
| `ap_participation_rate` | number | AP participation rate. |
| `gifted_participation_rate` | number | Gifted program participation rate. |

## Special Education Fields

| Field | Type | Description |
| --- | --- | --- |
| `special_education_enrollment` | number | Students receiving special education services. |
| `idea_part_b_enrollment` | number | IDEA Part B eligible or served students, depending on source convention. |
| `special_education_teachers` | number | Special education teacher FTE count. |
| `special_education_expenditure` | number | Special education expenditure when available. |
| `special_education_instruction_expenditure` | number | Special education instruction expenditure. |
| `special_education_pupil_support_expenditure` | number | Special education pupil support services expenditure. |
| `special_education_staff_support_expenditure` | number | Special education staff support services expenditure. |
| `special_education_transport_expenditure` | number | Special education transportation support services expenditure. |
| `special_education_teacher_salaries` | number | Special education teacher salaries. |
| `special_education_rate` | number | `special_education_enrollment / enrollment`. |
| `idea_part_b_rate` | number | `idea_part_b_enrollment / enrollment`. |
| `special_education_spending_pp` | number | `special_education_expenditure / special_education_enrollment`. |
| `special_education_student_teacher_ratio` | number | `special_education_enrollment / special_education_teachers`. |
| `inclusion_80pct_rate` | number | Share of special education students spending at least 80 percent of the day in general education settings. |
| `separate_setting_rate` | number | Share of special education students served in separate school or restrictive settings. |

## Outcome Fields

| Field | Type | Description |
| --- | --- | --- |
| `math_proficiency_rate` | number | District math proficiency rate. |
| `reading_proficiency_rate` | number | District reading proficiency rate. |
| `graduation_rate` | number | Cohort graduation rate. |
| `attendance_rate` | number | Average attendance rate. |
| `dropout_rate` | number | Dropout rate. |
| `college_enrollment_rate` | number | Postsecondary enrollment rate after high school. |

## Federal Program Fields

| Field | Type | Description |
| --- | --- | --- |
| `idea_part_b_revenue` | number | Federal IDEA revenue passed through the state. |
| `esser_revenue` | number | Available ESSER-style federal relief revenue field from F-33. |

## Public Safety Context

| Field | Type | Description |
| --- | --- | --- |
| `violent_crime_rate` | number | County violent crime rate. |
| `property_crime_rate` | number | County property crime rate. |

## Policy Event Features

| Field | Type | Description |
| --- | --- | --- |
| `funding_reform_active` | integer | `1` after a matching state funding reform event year, otherwise `0`. |
| `teacher_pay_reform_active` | integer | `1` after a matching state teacher pay reform event year, otherwise `0`. |
| `school_choice_active` | integer | `1` after a matching state school choice event year, otherwise `0`. |
| `active_policy_events` | string | Semicolon-separated active policy event names for the district-year. |
