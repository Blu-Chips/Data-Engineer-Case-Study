# Data Quality Report

## Source Inventory

- Credit snapshots: 5 files, 71,456 raw rows.
- Sales/customer: 20,747 raw rows from the Combined sheet.
- NPS: 4,129 raw survey rows.

## Relationship Analysis

- Credit to sales/customer match rate: 100.0%.
- Credit to NPS match rate: 17.03%.
- Credit loan IDs not found in sales/customer: 0.
- Sales IDs not present in credit snapshots: 7.
- NPS loan IDs not present in credit snapshots: 0.

## Key Data Issues Found

- Sales/customer demographics are incomplete for older credit accounts; missing `DoB` and `Income Level` flow into `Unknown` analytical bands.
- NPS has repeated loan IDs; the pipeline keeps the most recent submission per loan.
- Credit snapshots use date strings and occasionally include extra unnamed columns; the pipeline removes unnamed columns and derives `reporting_date` per snapshot.
- Income duration is not available in the source, so `Income Level` is treated as the monthly income proxy for banding.

## Important Null Percentages

| dataset | column | null_pct | null_count |
| --- | --- | --- | --- |
| analytics | nps_score | 85.13 | 60825 |
| analytics | Income Level | 63.38 | 45286 |
| analytics | DoB | 61.14 | 43681 |
| nps | nps_score | 3.77 | 133 |
| sales_customer | Income Level | 48.86 | 10138 |
| sales_customer | DoB | 46.14 | 9572 |

## Latest Snapshot Risk Distribution

| risk_category | accounts |
| --- | --- |
| Low | 11045 |
| Critical | 7376 |
| Medium | 1370 |
| High | 949 |

## Cleaning Assumptions

- Credit data is the grain driver: one row per `LOAN_ID` and `reporting_date`.
- Duplicate credit rows retain the highest balance because that is the most conservative exposure view.
- Duplicate sales rows retain the most complete customer record.
- Duplicate NPS rows retain the most recent survey timestamp.
- Missing date, income, or NPS values are not imputed; they are surfaced through `Unknown` bands or null survey metrics.