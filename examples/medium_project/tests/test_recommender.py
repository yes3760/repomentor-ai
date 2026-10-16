import pandas as pd

from src.recommender import genre_vector, recommend


def test_genre_vector():
    assert genre_vector("aksiyon dram")[:2] == [1, 1]


def test_recommend_excludes_liked():
    df = pd.DataFrame({
        "title": ["A", "B", "C"],
        "genres": ["aksiyon", "aksiyon", "dram"],
        "rating": [7, 8, 6],
        "year": [2020, 2024, 2010],
    })
    result = recommend(df, ["A"], top_n=2)
    assert "A" not in result["title"].tolist()
