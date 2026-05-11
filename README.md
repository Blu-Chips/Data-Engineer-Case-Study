# Annex Technologies Data Engineer Case Study

## ABC Phones Credit Portfolio Analysis

This submission contains a concise batch ETL and BI analysis for the ABC Phones credit portfolio case study.

## Submission Structure

```text
Annex_DE_JamesM/
├── README.md
├── pipeline_design/
│   └── architecture.png
├── scripts/
│   ├── data_profiling.py
│   ├── data_cleaning.py
│   ├── feature_engineering.py
│   ├── quality_checks.py
│   └── analysis.py
├── slides/
│   └── Annex_DE_Presentation.pdf
└── outputs/
    ├── cleaned_summary.csv
    ├── data_quality_report.md
    ├── quality_checks_log.csv
    └── portfolio_metrics.csv
```

## How To Run

```powershell
pip install -r requirements.txt
python scripts/data_profiling.py
python scripts/data_cleaning.py
python scripts/feature_engineering.py
python scripts/quality_checks.py
python scripts/analysis.py
```

The scripts use repository-relative paths.

## Incremental Ingestion Process

The case-study implementation runs as an idempotent full refresh: every run scans the source folders, combines all available credit snapshots, deduplicates by loan and reporting date, rebuilds the cleaned summary, and recalculates portfolio metrics.

For new data:

1. Drop the new credit snapshot into `Credit Data/`.
2. Replace or refresh the sales/customer and NPS workbooks in `SourceData/` if new versions are available.
3. Rerun the five scripts in the order above.
4. Review `outputs/quality_checks_log.csv`; publish outputs only if there are no critical failures.

Production incremental approach: persist file hashes and processed reporting dates, process only new or changed files, then upsert by `loan_key + reporting_date`. Late-arriving files are handled by reprocessing the affected reporting date partition. Duplicate rows are resolved by the same deterministic rules used in this submission.

## Key Assumptions

- Credit snapshots are the analytical grain: one row per loan and reporting date.
- `LOAN_ID` joins to `SALE_ID`.
- NPS duplicates keep the latest response per loan.
- Missing demographics are not imputed; they are reported as `Unknown` bands.
- Employment duration is not available, so `Income Level` is used as the income-band source.
- Publishable outputs use hashed `loan_key` values and exclude raw survey comments, exact DOB, and raw income values.

## Data Quality Checks

Implemented checks:

- Freshness
- Uniqueness
- Referential integrity
- Range checks
- Null thresholds
- Record count reconciliation

Latest run: 0 critical failures. The remaining warnings are high missingness in `DoB` and `Income Level`.

## Portfolio Findings

Latest snapshot: `2025-12-30`.

- Accounts analyzed: `20,740`
- Delinquency rate: `45.3%`
- PAR30 rate: `38.0%`
- PAR90 / loss proxy: `32.5%`
- Arrears balance share: `45.5%`
- Critical-risk customers have the weakest NPS signal: average score `5.2/10`, NPS index `-22.7`

## Recommendation

Launch an early-arrears care journey before accounts cross PAR30, combining payment-reflection checks, proactive reminders, and fast support routing.
