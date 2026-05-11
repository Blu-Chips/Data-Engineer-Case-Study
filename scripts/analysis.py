from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline_utils import OUTPUT_DIR, build_pipeline_frames, nps_score, write_csv


def portfolio_metrics(analytics: pd.DataFrame) -> pd.DataFrame:
    grouped = analytics.groupby("reporting_date", dropna=False)
    metrics = grouped.agg(
        total_accounts=("LOAN_ID", "nunique"),
        portfolio_balance=("BALANCE", "sum"),
        arrears_balance=("ARREARS", "sum"),
        delinquent_accounts=("is_delinquent", "sum"),
        par30_accounts=("is_par30", "sum"),
        par90_accounts=("is_par90", "sum"),
        total_paid=("TOTAL_PAID", "sum"),
        total_exposure=("LOAN_PRICE", "sum"),
        avg_collection_rate=("collection_rate", "mean"),
        avg_nps_score=("nps_score", "mean"),
    ).reset_index()
    metrics["delinquency_rate"] = metrics["delinquent_accounts"] / metrics["total_accounts"]
    metrics["par30_rate"] = metrics["par30_accounts"] / metrics["total_accounts"]
    metrics["par90_rate"] = metrics["par90_accounts"] / metrics["total_accounts"]
    metrics["arrears_rate"] = metrics["arrears_balance"] / metrics["portfolio_balance"].replace({0: np.nan})
    metrics["loss_proxy_rate"] = metrics["par90_accounts"] / metrics["total_accounts"]
    return metrics.sort_values("reporting_date")


def segment_risk(analytics: pd.DataFrame) -> pd.DataFrame:
    latest = analytics.loc[analytics["reporting_date"] == analytics["reporting_date"].max()].copy()
    portfolio_delinquency = latest["is_delinquent"].mean()
    by_age = (
        latest.groupby("age_band")
        .agg(accounts=("LOAN_ID", "nunique"), delinquency_rate=("is_delinquent", "mean"), par30_rate=("is_par30", "mean"))
        .reset_index()
    )
    by_age["segment_type"] = "age_band"
    by_age = by_age.rename(columns={"age_band": "segment"})

    by_income = (
        latest.groupby("avg_monthly_income_band")
        .agg(accounts=("LOAN_ID", "nunique"), delinquency_rate=("is_delinquent", "mean"), par30_rate=("is_par30", "mean"))
        .reset_index()
    )
    by_income["segment_type"] = "income_band"
    by_income = by_income.rename(columns={"avg_monthly_income_band": "segment"})

    result = pd.concat([by_age, by_income], ignore_index=True)
    result["portfolio_delinquency_rate"] = portfolio_delinquency
    result["delinquency_vs_portfolio_pp"] = (result["delinquency_rate"] - portfolio_delinquency) * 100
    return result.sort_values(["segment_type", "delinquency_vs_portfolio_pp"], ascending=[True, False])


def nps_risk_analysis(analytics: pd.DataFrame) -> pd.DataFrame:
    latest = analytics.loc[analytics["reporting_date"] == analytics["reporting_date"].max()].copy()
    scored = latest.loc[latest["nps_score"].notna()].copy()
    if scored.empty:
        return pd.DataFrame()
    grouped = scored.groupby("risk_category")
    result = grouped.agg(
        responses=("LOAN_ID", "nunique"),
        avg_nps_score=("nps_score", "mean"),
        delinquency_rate=("is_delinquent", "mean"),
        avg_days_past_due=("days_past_due", "mean"),
    ).reset_index()
    result["nps"] = grouped["nps_score"].apply(nps_score).values
    return result.sort_values("avg_days_past_due")


def main() -> None:
    frames = build_pipeline_frames()
    metrics = portfolio_metrics(frames.analytics)

    write_csv(metrics, OUTPUT_DIR / "portfolio_metrics.csv")
    print(f"Portfolio metrics written to {OUTPUT_DIR / 'portfolio_metrics.csv'}")


if __name__ == "__main__":
    main()
