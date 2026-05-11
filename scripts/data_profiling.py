from __future__ import annotations

import pandas as pd

from pipeline_utils import OUTPUT_DIR, build_pipeline_frames, write_csv


def column_profile(df: pd.DataFrame, dataset: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "dataset": dataset,
            "column": df.columns,
            "dtype": [str(df[column].dtype) for column in df.columns],
            "row_count": len(df),
            "null_count": [int(df[column].isna().sum()) for column in df.columns],
            "null_pct": [round(float(df[column].isna().mean() * 100), 2) for column in df.columns],
            "distinct_count": [int(df[column].nunique(dropna=True)) for column in df.columns],
        }
    )


def relationship_summary(frames) -> dict[str, object]:
    credit_loans = set(frames.credit_clean["LOAN_ID"].dropna())
    sales_ids = set(frames.sales_clean["SALE_ID"].dropna())
    nps_loans = set(frames.nps_clean["LOAN_ID"].dropna())
    return {
        "credit_loan_ids": len(credit_loans),
        "sales_sale_ids": len(sales_ids),
        "nps_loan_ids": len(nps_loans),
        "credit_to_sales_match_rate": round(len(credit_loans & sales_ids) / max(len(credit_loans), 1) * 100, 2),
        "credit_to_nps_match_rate": round(len(credit_loans & nps_loans) / max(len(credit_loans), 1) * 100, 2),
        "sales_not_in_credit": len(sales_ids - credit_loans),
        "credit_not_in_sales": len(credit_loans - sales_ids),
        "nps_not_in_credit": len(nps_loans - credit_loans),
    }


def duplicate_summary(frames) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "dataset": "credit",
                "key": "LOAN_ID + reporting_date",
                "raw_rows": len(frames.credit_raw),
                "clean_rows": len(frames.credit_clean),
                "duplicates_removed": len(frames.credit_raw) - len(frames.credit_clean),
            },
            {
                "dataset": "sales_customer",
                "key": "SALE_ID",
                "raw_rows": len(frames.sales_raw),
                "clean_rows": len(frames.sales_clean),
                "duplicates_removed": len(frames.sales_raw) - len(frames.sales_clean),
            },
            {
                "dataset": "nps",
                "key": "LOAN_ID",
                "raw_rows": len(frames.nps_raw),
                "clean_rows": len(frames.nps_clean),
                "duplicates_removed": len(frames.nps_raw) - len(frames.nps_clean),
            },
        ]
    )


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    values = df.astype(str)
    headers = list(values.columns)
    rows = values.values.tolist()
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def write_markdown_report(frames, profile: pd.DataFrame, relationships: dict[str, object]) -> None:
    important_nulls = profile.loc[
        profile["column"].isin(["DoB", "Income Level", "ARREARS", "nps_score"])
        & (profile["null_pct"] > 0),
        ["dataset", "column", "null_pct", "null_count"],
    ].sort_values(["dataset", "null_pct"], ascending=[True, False])

    latest = frames.analytics.loc[frames.analytics["reporting_date"] == frames.analytics["reporting_date"].max()]
    risk_dist = latest["risk_category"].value_counts().rename_axis("risk_category").reset_index(name="accounts")

    lines = [
        "# Data Quality Report",
        "",
        "## Source Inventory",
        "",
        f"- Credit snapshots: {frames.credit_raw['source_file'].nunique()} files, {len(frames.credit_raw):,} raw rows.",
        f"- Sales/customer: {len(frames.sales_raw):,} raw rows from the Combined sheet.",
        f"- NPS: {len(frames.nps_raw):,} raw survey rows.",
        "",
        "## Relationship Analysis",
        "",
        f"- Credit to sales/customer match rate: {relationships['credit_to_sales_match_rate']}%.",
        f"- Credit to NPS match rate: {relationships['credit_to_nps_match_rate']}%.",
        f"- Credit loan IDs not found in sales/customer: {relationships['credit_not_in_sales']:,}.",
        f"- Sales IDs not present in credit snapshots: {relationships['sales_not_in_credit']:,}.",
        f"- NPS loan IDs not present in credit snapshots: {relationships['nps_not_in_credit']:,}.",
        "",
        "## Key Data Issues Found",
        "",
        "- Sales/customer demographics are incomplete for older credit accounts; missing `DoB` and `Income Level` flow into `Unknown` analytical bands.",
        "- NPS has repeated loan IDs; the pipeline keeps the most recent submission per loan.",
        "- Credit snapshots use date strings and occasionally include extra unnamed columns; the pipeline removes unnamed columns and derives `reporting_date` per snapshot.",
        "- Income duration is not available in the source, so `Income Level` is treated as the monthly income proxy for banding.",
        "",
        "## Important Null Percentages",
        "",
        markdown_table(important_nulls) if not important_nulls.empty else "No important nulls above 0%.",
        "",
        "## Latest Snapshot Risk Distribution",
        "",
        markdown_table(risk_dist),
        "",
        "## Cleaning Assumptions",
        "",
        "- Credit data is the grain driver: one row per `LOAN_ID` and `reporting_date`.",
        "- Duplicate credit rows retain the highest balance because that is the most conservative exposure view.",
        "- Duplicate sales rows retain the most complete customer record.",
        "- Duplicate NPS rows retain the most recent survey timestamp.",
        "- Missing date, income, or NPS values are not imputed; they are surfaced through `Unknown` bands or null survey metrics.",
    ]
    (OUTPUT_DIR / "data_quality_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    frames = build_pipeline_frames()
    profiles = pd.concat(
        [
            column_profile(frames.credit_clean, "credit"),
            column_profile(frames.sales_clean, "sales_customer"),
            column_profile(frames.nps_clean, "nps"),
            column_profile(frames.analytics, "analytics"),
        ],
        ignore_index=True,
    )
    relationships = relationship_summary(frames)
    duplicates = duplicate_summary(frames)

    write_markdown_report(frames, profiles, relationships)

    print("Profiling outputs written:")
    print(f"- {OUTPUT_DIR / 'data_quality_report.md'}")


if __name__ == "__main__":
    main()
