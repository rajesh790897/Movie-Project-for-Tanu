"""
recommender.py
--------------
Core recommendation engine.

Pipeline
--------
1. Load movies from MySQL via database.py
2. Build a 'content' feature by combining genre, overview, director, cast
3. Vectorise content with TF-IDF
4. Pre-compute the cosine-similarity matrix (cached in memory)
5. Expose recommend_movies() for title-based recommendations
6. Expose recommend_by_genre() and recommend_top_rated() as optional extras
"""

import re
import threading
from typing import Any

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from database import fetch_movies, fetch_movies_by_genre, fetch_top_rated_movies


# ---------------------------------------------------------------------------
# Module-level cache (populated once on first use, thread-safe)
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()

_movies_df: pd.DataFrame = None          # full movie dataframe
_cosine_sim: "np.ndarray" = None         # cosine-similarity matrix
_title_to_index: dict = None             # normalised title → df row index


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_title(title: str) -> str:
    """Lower-case and strip extra whitespace from a title for robust lookup."""
    return re.sub(r"\s+", " ", title.strip().lower())


def _build_content_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Combine genre, overview, director, and cast into a single
    'content' string column used for TF-IDF vectorisation.

    Missing values are replaced with an empty string so they don't
    disrupt concatenation.
    """
    text_cols = ["genre", "overview", "director", "cast"]
    for col in text_cols:
        df[col] = df[col].fillna("").astype(str)

    # Repeat genre and director twice to give them slightly more weight
    df["content"] = (
        df["genre"] + " " + df["genre"] + " "
        + df["overview"] + " "
        + df["director"] + " " + df["director"] + " "
        + df["cast"]
    )
    return df


def _compute_similarity(df: pd.DataFrame):
    """
    Vectorise the 'content' column with TF-IDF and return the
    cosine-similarity matrix.

    TfidfVectorizer settings
    ------------------------
    - max_features=10_000   : caps vocabulary for large datasets
    - stop_words='english'  : removes common filler words
    - ngram_range=(1, 2)    : unigrams + bigrams for richer matching
    """
    tfidf = TfidfVectorizer(
        max_features=10_000,
        stop_words="english",
        ngram_range=(1, 2),
    )
    tfidf_matrix = tfidf.fit_transform(df["content"])
    # cosine_similarity returns a dense matrix; for very large sets
    # consider using linear_kernel instead (same result, less memory)
    sim_matrix = cosine_similarity(tfidf_matrix, tfidf_matrix)
    return sim_matrix


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def _load_cache(force_reload: bool = False):
    """
    Thread-safe initialisation / reload of the in-memory cache.

    Parameters
    ----------
    force_reload : bool
        Pass True to discard the existing cache and rebuild from the DB.
    """
    global _movies_df, _cosine_sim, _title_to_index

    with _cache_lock:
        if _movies_df is not None and not force_reload:
            return  # already loaded

        df = fetch_movies()
        if df.empty:
            raise RuntimeError(
                "The movies table is empty. Please seed the database first."
            )

        df = _build_content_column(df)
        sim = _compute_similarity(df)

        # Build a normalised-title → positional-index mapping
        index_map = {
            _normalise_title(title): idx
            for idx, title in enumerate(df["title"])
        }

        _movies_df = df.reset_index(drop=True)
        _cosine_sim = sim
        _title_to_index = index_map


def reload_cache():
    """
    Public API to force a cache refresh (e.g. after the DB is updated).
    """
    _load_cache(force_reload=True)


# ---------------------------------------------------------------------------
# Public recommendation functions
# ---------------------------------------------------------------------------

def recommend_movies(movie_title: str, top_n: int = 5) -> list[str]:
    """
    Return the top-N most similar movies to *movie_title*.

    Parameters
    ----------
    movie_title : str
        Title of the seed movie (case-insensitive).
    top_n : int
        Number of recommendations to return (default 5).

    Returns
    -------
    list[str]
        Ordered list of recommended movie titles (most similar first).

    Raises
    ------
    ValueError
        If the movie title is not found in the database.
    """
    _load_cache()

    key = _normalise_title(movie_title)
    if key not in _title_to_index:
        raise ValueError(
            f"Movie '{movie_title}' not found. "
            "Check the spelling or use /movies to browse available titles."
        )

    idx = _title_to_index[key]

    # Pair every movie with its similarity score to the seed
    similarity_scores = list(enumerate(_cosine_sim[idx]))

    # Sort descending by score, skip the seed movie itself (same index)
    similarity_scores = sorted(
        [(i, score) for i, score in similarity_scores if i != idx],
        key=lambda x: x[1],
        reverse=True,
    )

    # Take top N
    top_indices = [i for i, _ in similarity_scores[:top_n]]
    return _movies_df["title"].iloc[top_indices].tolist()


def recommend_movies_with_preferences(
    movie_title: str,
    preferences: dict[str, Any],
    top_n: int = 5,
) -> list[str]:
    """
    Return recommendations using content similarity and user preferences.

    Supported preference keys
    -------------------------
    preferred_genres    : list[str]
    preferred_directors : list[str]
    preferred_cast      : list[str]
    min_rating          : float
    """
    _load_cache()

    key = _normalise_title(movie_title)
    if key not in _title_to_index:
        raise ValueError(
            f"Movie '{movie_title}' not found. "
            "Check the spelling or use /movies to browse available titles."
        )

    idx = _title_to_index[key]
    similarity_scores = list(enumerate(_cosine_sim[idx]))

    preferred_genres = {
        str(item).strip().lower()
        for item in preferences.get("preferred_genres", [])
        if str(item).strip()
    }
    preferred_directors = {
        str(item).strip().lower()
        for item in preferences.get("preferred_directors", [])
        if str(item).strip()
    }
    preferred_cast = {
        str(item).strip().lower()
        for item in preferences.get("preferred_cast", [])
        if str(item).strip()
    }
    min_rating = preferences.get("min_rating")

    ranked = []
    for movie_idx, base_score in similarity_scores:
        if movie_idx == idx:
            continue

        row = _movies_df.iloc[movie_idx]
        row_genre = str(row.get("genre", "")).lower()
        row_director = str(row.get("director", "")).lower()
        row_cast = str(row.get("cast", "")).lower()
        row_rating = float(row.get("rating", 0.0) or 0.0)

        if min_rating is not None and row_rating < float(min_rating):
            continue

        adjusted_score = float(base_score)

        if preferred_genres and any(item in row_genre for item in preferred_genres):
            adjusted_score += 0.20
        if preferred_directors and any(
            item in row_director for item in preferred_directors
        ):
            adjusted_score += 0.15
        if preferred_cast and any(item in row_cast for item in preferred_cast):
            adjusted_score += 0.15

        # A small rating bump helps break ties toward higher-rated movies.
        adjusted_score += min(row_rating / 50.0, 0.2)

        ranked.append((movie_idx, adjusted_score, row_rating))

    ranked.sort(key=lambda x: (x[1], x[2]), reverse=True)
    top_indices = [movie_idx for movie_idx, _, _ in ranked[:top_n]]
    return _movies_df["title"].iloc[top_indices].tolist()


def recommend_by_genre(genre: str, top_n: int = 5) -> list[dict]:
    """
    Return the top-N highest-rated movies in a given genre.

    Parameters
    ----------
    genre : str
        Genre to filter on (partial, case-insensitive match).
    top_n : int
        Number of results to return.

    Returns
    -------
    list[dict]
        Each dict contains 'title' and 'rating'.

    Raises
    ------
    ValueError
        If no movies are found for the specified genre.
    """
    df = fetch_movies_by_genre(genre)
    if df.empty:
        raise ValueError(f"No movies found for genre '{genre}'.")

    df_sorted = df.sort_values("rating", ascending=False).head(top_n)
    return df_sorted[["title", "rating"]].to_dict(orient="records")


def recommend_top_rated(limit: int = 10) -> list[dict]:
    """
    Return the top-rated movies from the database.

    Parameters
    ----------
    limit : int
        How many movies to return (default 10).

    Returns
    -------
    list[dict]
        Each dict contains 'title' and 'rating'.
    """
    df = fetch_top_rated_movies(limit=limit)
    return df[["title", "rating"]].to_dict(orient="records")


def list_all_titles() -> list[str]:
    """
    Return a sorted list of all movie titles in the database.
    Useful for debugging or powering an autocomplete endpoint.
    """
    _load_cache()
    return sorted(_movies_df["title"].tolist())
