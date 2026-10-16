import streamlit as st

from src.data import load_movies
from src.recommender import recommend

st.title("🎬 Film Öneri")
movies = load_movies()
liked = st.multiselect("Beğendiğin filmler", movies["title"].tolist())
if st.button("Öner"):
    try:
        st.dataframe(recommend(movies, liked))
    except:
        st.error("Öneri oluşturulamadı")
