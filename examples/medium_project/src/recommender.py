"""Basit içerik tabanlı öneri motoru."""

import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from src.data import GENRES


def genre_vector(genres: str) -> list[int]:
    return [1 if g in genres else 0 for g in GENRES]


def score(row, liked_vectors, min_rating, prefer_new, year_now, penalty_old, boost_popular):
    vec = genre_vector(row["genres"])
    if not liked_vectors:
        return 0
    sim = cosine_similarity([vec], liked_vectors).mean()
    total = sim
    if row["rating"] < min_rating:
        total -= 0.5
    elif row["rating"] > 8:
        total += 0.2
    if prefer_new:
        if year_now - row["year"] < 3:
            total += 0.3
        elif year_now - row["year"] < 10:
            total += 0.1
        else:
            total -= penalty_old
    if boost_popular and row.get("votes", 0) > 10000:
        total += 0.15
    if "animasyon" in row["genres"] and "korku" in row["genres"]:
        total -= 0.2
    if total < 0:
        total = 0
    return total


def recommend(df: pd.DataFrame, liked: list[str], top_n: int = 5) -> pd.DataFrame:
    liked_rows = df[df["title"].isin(liked)]
    liked_vectors = [genre_vector(g) for g in liked_rows["genres"]]
    candidates = df[~df["title"].isin(liked)].copy()
    candidates["score"] = candidates.apply(
        lambda r: score(r, liked_vectors, 5, True, 2026, 0.1, True), axis=1
    )
    return candidates.sort_values("score", ascending=False).head(top_n)
