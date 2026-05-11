from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "SourceData"
CREDIT_DIR = PROJECT_ROOT / "Credit Data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
PIPELINE_DIR = PROJECT_ROOT / "pipeline_design"
SLIDES_DIR = PROJECT_ROOT / "slides"

NPS_SCORE_COLUMN = (
    "Using a scale from 0 (not likely) to 10 (very likely), how likely are you "
    "to recommend ABC Phones to friends or family?"
)

INCOME_BANDS = [
    (0, 5000, "Below 5,000"),
    (5000, 10000, "5,000-9,999"),
    (10000, 20000, "10,000-19,999"),
    (20000, 30000, "20,000-29,999"),
    (30000, 50000, "30,000-49,999"),
    (50000, 100000, "50,000-99,999"),
    (100000, 150000, "100,000-149,999"),
    (150000, np.inf, "150,000+"),
]


@dataclass
class PipelineFrames:
    credit_raw: pd.DataFrame
    sales_raw: pd.DataFrame
    nps_raw: pd.DataFrame
    credit_clean: pd.DataFrame
    sales_clean: pd.DataFrame
    nps_clean: pd.DataFrame
    analytics: pd.DataFrame
    duplicate_audit: pd.DataFrame
    ingestion_metadata: pd.DataFrame


def ensure_directories() -> None:
    for path in (OUTPUT_DIR, PIPELINE_DIR, SLIDES_DIR):
        path.mkdir(parents=True, exist_ok=True)


def file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def hash_identifier(value: object) -> str | pd.NA:
    if pd.isna(value):
        return pd.NA
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return f"loan_{digest[:16]}"


def parse_snapshot_date(path: Path) -> pd.Timestamp:
    match = re.search(r"(\d{2})-(\d{2})-(\d{4})", path.stem)
    if not match:
        return pd.NaT
    day, month, year = match.groups()
    return pd.Timestamp(year=int(year), month=int(month), day=int(day))


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result.columns = [str(column).strip() for column in result.columns]
    result = result.loc[:, ~result.columns.str.match(r"^Unnamed")]
    return result


def standardize_nulls(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result = result.replace(r"^\s*$", np.nan, regex=True)
    result = result.replace({"nan": np.nan, "None": np.nan, "NULL": np.nan, "N/A": np.nan})
    return result


def clean_numeric(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype("string")
        .str.replace(",", "", regex=False)
        .str.replace("KES", "", regex=False)
        .str.replace("KSh", "", regex=False)
        .str.replace(r"[^\d.\-]", "", regex=True)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def clean_text_columns(df: pd.DataFrame, uppercase_columns: Iterable[str] = ()) -> pd.DataFrame:
    result = df.copy()
    uppercase = set(uppercase_columns)
    for column in result.select_dtypes(include=["object", "string"]).columns:
        values = result[column].astype("string").str.strip()
        if column in uppercase:
            values = values.str.upper()
        result[column] = values.replace({"": pd.NA})
    return result


def read_credit_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    metadata = []
    files = sorted(CREDIT_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No credit CSV files found in {CREDIT_DIR}")

    for path in files:
        frame = pd.read_csv(path)
        frame = normalize_columns(frame)
        frame["source_file"] = path.name
        frame["reporting_date"] = parse_snapshot_date(path)
        if "DATE" in frame.columns:
            frame["source_date"] = pd.to_datetime(frame["DATE"], errors="coerce")
            frame["reporting_date"] = frame["source_date"].fillna(frame["reporting_date"])
        rows.append(frame)
        metadata.append(
            {
                "dataset": "credit",
                "file_name": path.name,
                "row_count": len(frame),
                "file_hash": file_hash(path),
                "ingested_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )

    return pd.concat(rows, ignore_index=True), pd.DataFrame(metadata)


def read_sales_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    path = SOURCE_DIR / "Sales and Customer Data.xlsx"
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_excel(path, sheet_name="Combined")
    frame = normalize_columns(frame)
    frame["source_file"] = path.name
    metadata = pd.DataFrame(
        [
            {
                "dataset": "sales_customer",
                "file_name": path.name,
                "row_count": len(frame),
                "file_hash": file_hash(path),
                "ingested_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        ]
    )
    return frame, metadata


def read_nps_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    preferred = SOURCE_DIR / "NPS Data_v1.xlsx"
    fallback = SOURCE_DIR / "NPS Data (1).xlsx"
    path = preferred if preferred.exists() else fallback
    if not path.exists():
        raise FileNotFoundError(path)
    sheet_name = "RawData" if path.name == preferred.name else 0
    frame = pd.read_excel(path, sheet_name=sheet_name)
    frame = normalize_columns(frame)
    frame["source_file"] = path.name
    metadata = pd.DataFrame(
        [
            {
                "dataset": "nps",
                "file_name": path.name,
                "row_count": len(frame),
                "file_hash": file_hash(path),
                "ingested_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        ]
    )
    return frame, metadata


def clean_credit_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = standardize_nulls(normalize_columns(df))
    required = {"LOAN_ID", "reporting_date", "BALANCE", "ARREARS", "DAYS_PAST_DUE", "ACCOUNT_STATUS_L1"}
    missing = sorted(required.difference(result.columns))
    if missing:
        raise ValueError(f"Credit data missing required columns: {missing}")

    result["LOAN_ID"] = result["LOAN_ID"].astype("string").str.strip()
    result["reporting_date"] = pd.to_datetime(result["reporting_date"], errors="coerce").dt.date

    numeric_columns = [
        "CUSTOMER_AGE",
        "TOTAL_PAID",
        "TOTAL_DUE_TODAY",
        "BALANCE",
        "DAYS_PAST_DUE",
        "CLOSING_BALANCE",
        "ADVANCE",
        "BALANCE_DUE_TO_DATE",
        "ARREARS",
        "PAYMENT",
        "EXPECTED_PAYMENT",
        "FIRST_PAYMENT",
        "FIRST_EXPECTED_PAYMENT",
        "PAYMENT_AMOUNT",
        "ADJUSTMENT_AMOUNT",
        "PREPAYMENT_AMOUNT",
        "DEPOSIT",
        "WEEKLY_RATE",
        "DISCOUNT",
        "OVERPAYMENT_AMOUNT",
        "INITIAL_PAY",
        "TOTAL_PAID_WITH_ADJUSTMENTS_15D",
    ]
    for column in set(numeric_columns).intersection(result.columns):
        result[column] = clean_numeric(result[column])

    date_columns = ["RETURN_DATE", "SALE_DATE", "CREDIT_EXPIRY", "NEXT_INVOICE_DATE", "MAX_PAYMENT_DATE"]
    for column in set(date_columns).intersection(result.columns):
        result[column] = pd.to_datetime(result[column], errors="coerce").dt.date

    text_columns = ["BALANCE_DUE_STATUS", "ACCOUNT_STATUS_L1", "ACCOUNT_STATUS_L2", "CREDIT_CHECK_DONE"]
    result = clean_text_columns(result, uppercase_columns=["CREDIT_CHECK_DONE"])

    sort_columns = ["LOAN_ID", "reporting_date", "BALANCE"]
    result = result.sort_values(sort_columns, ascending=[True, True, False])
    duplicate_mask = result.duplicated(["LOAN_ID", "reporting_date"], keep="first")
    audit = result.loc[duplicate_mask].copy()
    audit["dataset"] = "credit"
    audit["removal_reason"] = "duplicate LOAN_ID/reporting_date; retained highest BALANCE"
    result = result.loc[~duplicate_mask].reset_index(drop=True)

    demo_mask = result["ACCOUNT_STATUS_L1"].astype("string").str.lower().eq("demo")
    demo_audit = result.loc[demo_mask].copy()
    if not demo_audit.empty:
        demo_audit["dataset"] = "credit"
        demo_audit["removal_reason"] = "excluded non-production Demo account from portfolio analytics"
        audit = pd.concat([audit, demo_audit], ignore_index=True, sort=False)
        result = result.loc[~demo_mask].reset_index(drop=True)

    return result, audit


def clean_sales_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = standardize_nulls(normalize_columns(df))
    required = {"SALE_ID", "DoB", "Income Level", "Citizenship"}
    missing = sorted(required.difference(result.columns))
    if missing:
        raise ValueError(f"Sales/customer data missing required columns: {missing}")

    result["SALE_ID"] = result["SALE_ID"].astype("string").str.strip()
    result["SALE_DATE"] = pd.to_datetime(result.get("SALE_DATE"), errors="coerce").dt.date
    result["DoB"] = pd.to_datetime(result.get("DoB"), errors="coerce").dt.date
    for column in ["CASH_PRICE", "LOAN_PRICE", "Income Level"]:
        if column in result.columns:
            result[column] = clean_numeric(result[column])

    result = clean_text_columns(result, uppercase_columns=["Citizenship", "Gender", "SALE_TYPE"])
    result["non_null_count"] = result.notna().sum(axis=1)
    result = result.sort_values(["SALE_ID", "non_null_count"], ascending=[True, False])
    duplicate_mask = result.duplicated(["SALE_ID"], keep="first")
    audit = result.loc[duplicate_mask].copy()
    audit["dataset"] = "sales_customer"
    audit["removal_reason"] = "duplicate SALE_ID; retained row with fewest NULL values"
    result = result.loc[~duplicate_mask].drop(columns=["non_null_count"]).reset_index(drop=True)
    return result, audit


def clean_nps_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = standardize_nulls(normalize_columns(df))
    loan_col = "Loan Id"
    if loan_col not in result.columns:
        raise ValueError("NPS data missing required column: Loan Id")
    if NPS_SCORE_COLUMN not in result.columns:
        raise ValueError("NPS data missing score column")

    result = result.rename(columns={loan_col: "LOAN_ID", NPS_SCORE_COLUMN: "nps_score"})
    result["LOAN_ID"] = result["LOAN_ID"].astype("string").str.strip()
    result["nps_score"] = clean_numeric(result["nps_score"])
    result["nps_submitted_at"] = pd.to_datetime(result.get("Submitted at"), errors="coerce")
    result = clean_text_columns(result)

    result["nps_group"] = np.select(
        [
            (result["nps_score"] >= 9).fillna(False).to_numpy(dtype=bool),
            result["nps_score"].between(7, 8).fillna(False).to_numpy(dtype=bool),
            result["nps_score"].between(0, 6).fillna(False).to_numpy(dtype=bool),
        ],
        ["Promoter", "Passive", "Detractor"],
        default="Unknown",
    )

    result = result.sort_values(["LOAN_ID", "nps_submitted_at"], ascending=[True, False], na_position="last")
    duplicate_mask = result.duplicated(["LOAN_ID"], keep="first")
    audit = result.loc[duplicate_mask].copy()
    audit["dataset"] = "nps"
    audit["removal_reason"] = "duplicate LOAN_ID; retained most recent submitted timestamp"
    result = result.loc[~duplicate_mask].reset_index(drop=True)
    return result, audit


def calculate_age(dob: pd.Series, reporting_date: pd.Series) -> pd.Series:
    dob_dt = pd.to_datetime(dob, errors="coerce")
    report_dt = pd.to_datetime(reporting_date, errors="coerce")
    age = (report_dt - dob_dt).dt.days / 365.25
    return np.floor(age).astype("Int64")


def categorize_age(age: object) -> str:
    if pd.isna(age):
        return "Unknown"
    age = int(age)
    if age < 18:
        return "Under 18"
    if age <= 25:
        return "18-25"
    if age <= 35:
        return "26-35"
    if age <= 45:
        return "36-45"
    if age <= 55:
        return "46-55"
    return "55+"


def categorize_income(value: object) -> str:
    if pd.isna(value):
        return "Unknown"
    income = float(value)
    for lower, upper, label in INCOME_BANDS:
        if lower <= income < upper:
            return label
    return "Unknown"


def risk_category(row: pd.Series) -> str:
    dpd = 0 if pd.isna(row.get("days_past_due")) else float(row.get("days_past_due"))
    arrears = 0 if pd.isna(row.get("ARREARS")) else float(row.get("ARREARS"))
    status = str(row.get("ACCOUNT_STATUS_L1") or "").lower()
    if "write off" in status or "default" in status or dpd > 90 or arrears > 50000:
        return "Critical"
    if (30 < dpd <= 90) or arrears > 20000:
        return "High"
    if (0 < dpd <= 30) or arrears > 5000:
        return "Medium"
    if dpd == 0 and arrears <= 5000:
        return "Low"
    return "Unknown"


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["Age"] = calculate_age(result.get("DoB"), result.get("reporting_date"))
    result["age_band"] = result["Age"].apply(categorize_age)
    result["avg_monthly_income_band"] = result.get("Income Level").apply(categorize_income)
    result["days_past_due"] = result.get("DAYS_PAST_DUE").fillna(0).clip(lower=0).astype(int)
    result["risk_category"] = result.apply(risk_category, axis=1)
    result["is_delinquent"] = result["days_past_due"] > 0
    result["is_par30"] = result["days_past_due"] > 30
    result["is_par90"] = result["days_past_due"] > 90
    result["collection_rate"] = np.where(
        result["TOTAL_PAID"].fillna(0) + result["BALANCE"].fillna(0) > 0,
        result["TOTAL_PAID"].fillna(0) / (result["TOTAL_PAID"].fillna(0) + result["BALANCE"].fillna(0)),
        np.nan,
    )
    return result


def build_pipeline_frames() -> PipelineFrames:
    ensure_directories()
    credit_raw, credit_meta = read_credit_data()
    sales_raw, sales_meta = read_sales_data()
    nps_raw, nps_meta = read_nps_data()

    credit_clean, credit_audit = clean_credit_data(credit_raw)
    sales_clean, sales_audit = clean_sales_data(sales_raw)
    nps_clean, nps_audit = clean_nps_data(nps_raw)

    analytics = credit_clean.merge(
        sales_clean,
        left_on="LOAN_ID",
        right_on="SALE_ID",
        how="left",
        suffixes=("", "_customer"),
    )
    analytics = analytics.merge(
        nps_clean[
            [
                "LOAN_ID",
                "nps_score",
                "nps_group",
                "nps_submitted_at",
                "What is the main reason for your score?",
                "What is one thing we could do to improve your experience with us?",
                "Have you ever experienced a delay in your payment reflecting in your ABC account?",
                "Have you ever had your phone lock despite making a payment on time?",
            ]
        ],
        on="LOAN_ID",
        how="left",
    )
    analytics = engineer_features(analytics)

    duplicate_audit = pd.concat([credit_audit, sales_audit, nps_audit], ignore_index=True, sort=False)
    ingestion_metadata = pd.concat([credit_meta, sales_meta, nps_meta], ignore_index=True)

    return PipelineFrames(
        credit_raw=credit_raw,
        sales_raw=sales_raw,
        nps_raw=nps_raw,
        credit_clean=credit_clean,
        sales_clean=sales_clean,
        nps_clean=nps_clean,
        analytics=analytics,
        duplicate_audit=duplicate_audit,
        ingestion_metadata=ingestion_metadata,
    )


def nps_value_counts(series: pd.Series) -> dict[str, int]:
    counts = series.value_counts(dropna=False).to_dict()
    return {str(key): int(value) for key, value in counts.items()}


def nps_score(group: pd.Series) -> float:
    valid = pd.to_numeric(group, errors="coerce").dropna()
    if valid.empty:
        return np.nan
    promoters = (valid >= 9).mean()
    detractors = (valid <= 6).mean()
    return round((promoters - detractors) * 100, 2)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
