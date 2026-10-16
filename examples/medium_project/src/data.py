"""Film verisini yükler ve temizler."""

import pandas as pd

GENRES = ["aksiyon", "dram", "komedi", "bilim kurgu", "korku", "animasyon"]


def load_movies(path: str = "data/movies.csv") -> pd.DataFrame:
    """CSV dosyasından filmleri okur."""
    df = pd.read_csv(path)
    return clean(df)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["title"])
    df["genres"] = df["genres"].fillna("").str.lower()
    df["rating"] = df["rating"].clip(0, 10)
    return df.reset_index(drop=True)
