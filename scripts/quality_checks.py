from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from pipeline_utils import OUTPUT_DIR, build_pipeline_frames, write_csv


def result(check_name: str, status: str, severity: str, details: str, failed_rows: int = 0) -> dict[str, object]:
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "check_name": check_name,
        "status": status,
        "severity": severity,
        "failed_rows": int(failed_rows),
        "details": details,
    }


def run_all_quality_checks(analytics: pd.DataFrame, expected_rows: int, sales_ids: set[str]) -> pd.DataFrame:
    checks: list[dict[str, object]] = []

    duplicate_count = int(analytics.duplicated(["LOAN_ID", "reporting_date"]).sum())
    checks.append(
        result(
            "uniqueness_loan_reporting_date",
            "PASS" if duplicate_count == 0 else "FAIL",
            "critical",
            "Each loan should appear once per reporting snapshot.",
            duplicate_count,
        )
    )

    for column in ["LOAN_ID", "reporting_date", "BALANCE"]:
        null_count = int(analytics[column].isna().sum())
        checks.append(
            result(
                f"critical_null_{column}",
                "PASS" if null_count == 0 else "FAIL",
                "critical",
                f"`{column}` must be fully populated.",
                null_count,
            )
        )

    age_failures = int(analytics.loc[analytics["Age"].notna() & ~analytics["Age"].between(18, 120)].shape[0])
    checks.append(
        result(
            "age_range_18_120",
            "PASS" if age_failures == 0 else "WARN",
            "warning",
            "Non-null ages should be between 18 and 120.",
            age_failures,
        )
    )

    income_failures = int(analytics.loc[analytics["Income Level"].notna() & (analytics["Income Level"] < 0)].shape[0])
    checks.append(
        result(
            "income_non_negative",
            "PASS" if income_failures == 0 else "WARN",
            "warning",
            "Income values should be non-negative.",
            income_failures,
        )
    )

    for column in ["DoB", "Income Level", "ARREARS"]:
        null_pct = float(analytics[column].isna().mean() * 100)
        checks.append(
            result(
                f"important_null_threshold_{column}",
                "PASS" if null_pct <= 20 else "WARN",
                "warning",
                f"`{column}` null percentage is {null_pct:.2f}%; threshold is 20%.",
                int(analytics[column].isna().sum()),
            )
        )

    row_delta = int(len(analytics) - expected_rows)
    checks.append(
        result(
            "record_count_reconciliation",
            "PASS" if row_delta == 0 else "FAIL",
            "critical",
            f"Analytics rows ({len(analytics):,}) should match cleaned credit rows ({expected_rows:,}).",
            abs(row_delta),
        )
    )

    credit_loans = set(analytics["LOAN_ID"].dropna())
    match_rate = len(credit_loans & sales_ids) / max(len(credit_loans), 1) * 100
    checks.append(
        result(
            "referential_integrity_credit_to_sales",
            "PASS" if match_rate >= 95 else "WARN",
            "warning",
            f"Credit-to-sales match rate is {match_rate:.2f}%; case-study target is 95%.",
            int(len(credit_loans - sales_ids)),
        )
    )

    freshness_dates = pd.to_datetime(analytics["reporting_date"], errors="coerce")
    stale = freshness_dates.max() < pd.Timestamp("2025-12-30")
    checks.append(
        result(
            "freshness_latest_snapshot",
            "PASS" if not stale else "FAIL",
            "critical",
            f"Latest reporting date is {freshness_dates.max().date()}; expected at least 2025-12-30.",
            int(stale),
        )
    )

    return pd.DataFrame(checks)


def main() -> None:
    frames = build_pipeline_frames()
    checks = run_all_quality_checks(
        analytics=frames.analytics,
        expected_rows=len(frames.credit_clean),
        sales_ids=set(frames.sales_clean["SALE_ID"].dropna()),
    )
    write_csv(checks, OUTPUT_DIR / "quality_checks_log.csv")
    failures = checks.loc[checks["status"] == "FAIL"]
    warnings = checks.loc[checks["status"] == "WARN"]
    print(f"Quality checks written to {OUTPUT_DIR / 'quality_checks_log.csv'}")
    print(f"Critical failures: {len(failures)}")
    print(f"Warnings: {len(warnings)}")


if __name__ == "__main__":
    main()
