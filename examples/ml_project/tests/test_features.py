import pandas as pd

from src.features import add_features


def test_add_features():
    df = pd.DataFrame({"tenure": [24], "contract": ["two_year"], "monthly_charges": [50], "total_charges": [1200]})
    assert add_features(df)["tenure_years"].iloc[0] == 2
