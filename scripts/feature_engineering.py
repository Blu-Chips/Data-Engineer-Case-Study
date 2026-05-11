from __future__ import annotations

import pandas as pd

from pipeline_utils import OUTPUT_DIR, build_pipeline_frames, hash_identifier, write_csv


def main() -> None:
    frames = build_pipeline_frames()
    features = frames.analytics.assign(loan_key=frames.analytics["LOAN_ID"].apply(hash_identifier))[
        [
            "loan_key",
            "reporting_date",
            "Age",
            "age_band",
            "avg_monthly_income_band",
            "DAYS_PAST_DUE",
            "days_past_due",
            "ARREARS",
            "ACCOUNT_STATUS_L1",
            "ACCOUNT_STATUS_L2",
            "risk_category",
            "collection_rate",
            "nps_score",
            "nps_group",
        ]
    ].copy()
    distributions = []
    for column in ["age_band", "avg_monthly_income_band", "risk_category"]:
        summary = (
            frames.analytics.groupby(["reporting_date", column], dropna=False)
            .size()
            .reset_index(name="accounts")
            .rename(columns={column: "feature_value"})
        )
        summary.insert(1, "feature", column)
        distributions.append(summary)

    distribution_summary = pd.concat(distributions, ignore_index=True)
    print("Feature engineering completed.")
    print(distribution_summary.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
