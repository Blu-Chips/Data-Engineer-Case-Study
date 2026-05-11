from __future__ import annotations

from pipeline_utils import OUTPUT_DIR, build_pipeline_frames, hash_identifier, write_csv


PUBLISHABLE_FACT_COLUMNS = [
    "LOAN_ID",
    "reporting_date",
    "CUSTOMER_AGE",
    "TOTAL_PAID",
    "TOTAL_DUE_TODAY",
    "BALANCE",
    "DAYS_PAST_DUE",
    "CLOSING_BALANCE",
    "ADVANCE",
    "BALANCE_DUE_TO_DATE",
    "ARREARS",
    "BALANCE_DUE_STATUS",
    "PAYMENT",
    "EXPECTED_PAYMENT",
    "ACCOUNT_STATUS_L1",
    "ACCOUNT_STATUS_L2",
    "SALE_DATE",
    "CREDIT_CHECK_DONE",
    "DEPOSIT",
    "WEEKLY_RATE",
    "MAX_PAYMENT_DATE",
    "INITIAL_PAY",
    "TOTAL_PAID_WITH_ADJUSTMENTS_15D",
    "RETURNED",
    "SALE_TYPE",
    "CASH_PRICE",
    "LOAN_PRICE",
    "LOAN_TERM",
    "Citizenship",
    "Gender",
    "Provider",
    "Product",
    "Category",
    "nps_score",
    "nps_group",
    "Age",
    "age_band",
    "avg_monthly_income_band",
    "days_past_due",
    "risk_category",
    "is_delinquent",
    "is_par30",
    "is_par90",
    "collection_rate",
]


def publishable_fact(df):
    available = [column for column in PUBLISHABLE_FACT_COLUMNS if column in df.columns]
    result = df[available].copy()
    result.insert(0, "loan_key", result["LOAN_ID"].apply(hash_identifier))
    return result.drop(columns=["LOAN_ID"])


def publishable_audit(df):
    keep = [
        "dataset",
        "removal_reason",
        "LOAN_ID",
        "SALE_ID",
        "reporting_date",
        "source_file",
        "BALANCE",
        "ARREARS",
        "DAYS_PAST_DUE",
        "ACCOUNT_STATUS_L1",
    ]
    available = [column for column in keep if column in df.columns]
    result = df[available].copy()
    if "LOAN_ID" in result.columns:
        result.insert(2, "loan_key", result["LOAN_ID"].apply(hash_identifier))
        result = result.drop(columns=["LOAN_ID"])
    if "SALE_ID" in result.columns:
        result = result.drop(columns=["SALE_ID"])
    return result


def main() -> None:
    frames = build_pipeline_frames()

    analytics = publishable_fact(frames.analytics)
    latest_date = analytics["reporting_date"].max()
    latest_snapshot = analytics.loc[analytics["reporting_date"] == latest_date].copy()

    write_csv(latest_snapshot, OUTPUT_DIR / "cleaned_summary.csv")

    print("Cleaned analytics outputs written:")
    print(f"- {OUTPUT_DIR / 'cleaned_summary.csv'} ({len(latest_snapshot):,} rows)")


if __name__ == "__main__":
    main()
