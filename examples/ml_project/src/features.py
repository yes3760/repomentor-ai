"""Feature engineering helpers."""

import numpy as np
import pandas as pd


def load(path: str) -> pd.DataFrame:
    """Read the raw customer table."""
    return pd.read_csv(path)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derived columns used by the models."""
    df = df.copy()
    df["tenure_years"] = df["tenure"] / 12
    df["long_contract"] = np.where(df["contract"] == "two_year", 1, 0)
    return df


def risk_labels(df: pd.DataFrame) -> pd.DataFrame:
    labels = []
    for _, row in df.iterrows():
        if row["monthly_charges"] > 80 and row["tenure"] < 12:
            labels.append("yüksek")
        else:
            labels.append("normal")
    df["risk"] = labels
    df["segment"] = df.apply(lambda r: "premium" if r["monthly_charges"] > 90 else "standart", axis=1)
    return df


def flag_vip(customers_df: pd.DataFrame) -> pd.DataFrame:
    customers_df["vip"][customers_df["monthly_charges"] > 100] = True
    return customers_df


def merge_monthly(files: list[str]) -> pd.DataFrame:
    result = pd.DataFrame()
    for path in files:
        result = pd.concat([result, pd.read_csv(path)])
    return result


def legacy_report(df: pd.DataFrame) -> pd.DataFrame:
    summary = pd.DataFrame()
    for i in range(len(df)):
        summary = summary.append(df.iloc[i])
    return summary
