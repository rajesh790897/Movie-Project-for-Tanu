"""Live movie recommendation engine powered by OMDb data."""

from __future__ import annotations

import math
import os
import re
import threading
from typing import Any

import requests

from ai_service import gemini_enabled, generate_candidate_titles, generate_recommendation_story
from env_utils import get_env_value


OMDB_BASE_URL = "https://www.omdbapi.com/"
REQUEST_TIMEOUT = 15
IMDB_TITLE_URL = "https://www.imdb.com/title"

# OMDb has no discovery or similar-title endpoints, so this live catalog is
# built from common search terms and then enriched with OMDb details.
TITLE_HINT_SEARCHES = [
    "love",
    "star",
    "dark",
    "life",
    "last",
    "night",
    "man",
    "girl",
]

FALLBACK_CATALOG_TITLES = [
    "The Shawshank Redemption",
    "The Godfather",
    "The Dark Knight",
    "Pulp Fiction",
    "Fight Club",
    "Forrest Gump",
    "The Matrix",
    "Inception",
    "Interstellar",
    "Parasite",
    "Whiplash",
    "Gladiator",
    "Memento",
    "The Prestige",
    "Shutter Island",
    "The Departed",
    "Django Unchained",
    "Blade Runner 2049",
    "Arrival",
    "Dune",
    "Her",
    "La La Land",
    "Mad Max: Fury Road",
    "The Grand Budapest Hotel",
]


_session = requests.Session()
_cache_lock = threading.Lock()
_titles_cache: list[str] | None = None
_movie_cache: dict[str, dict[str, Any]] = {}


def _normalise_title(title: str) -> str:
    """Lower-case and collapse whitespace for matching titles."""
    return re.sub(r"\s+", " ", title.strip().lower())


def _is_omdb_limit_error(error: Exception) -> bool:
    """Detect OMDb quota/auth limit style errors from exception text."""
    message = str(error).lower()
    return any(token in message for token in ["limit", "unauthorized", "invalid api key", "too many"])


def _require_omdb_api_key() -> str:
    """Return the OMDb API key or raise a runtime error with guidance."""
    api_key = get_env_value("OMDB_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OMDB_API_KEY is not set. Add your OMDb API key as an environment "
            "variable before starting the app."
        )
    return api_key


def _omdb_get(params: dict[str, Any]) -> dict[str, Any]:
    """Make an authenticated GET request to OMDb."""
    query = dict(params)
    query["apikey"] = _require_omdb_api_key()

    try:
        response = _session.get(OMDB_BASE_URL, params=query, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Unable to reach OMDb right now: {exc}") from exc

    if payload.get("Response") == "False":
        raise ValueError(str(payload.get("Error", "OMDb returned no results.")))

    return payload


def _parse_rating(value: str | None) -> float:
    """Parse an IMDb rating string into a float."""
    if not value or value == "N/A":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _parse_votes(value: str | None) -> int:
    """Parse an IMDb votes string into an integer."""
    if not value or value == "N/A":
        return 0
    try:
        return int(value.replace(",", ""))
    except ValueError:
        return 0


def _parse_list(value: str | None) -> list[str]:
    """Split a comma-separated OMDb field into a clean list."""
    if not value or value == "N/A":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _movie_url(imdb_id: str | None) -> str:
    """Build an IMDb movie URL from an IMDb ID."""
    if not imdb_id:
        return ""
    return f"{IMDB_TITLE_URL}/{imdb_id}/"


def _normalise_movie(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert an OMDb payload into the app's response shape."""
    imdb_id = str(payload.get("imdbID", "")).strip()
    ratings = payload.get("Ratings") or []
    rotten_tomatoes = next(
        (item.get("Value", "") for item in ratings if item.get("Source") == "Rotten Tomatoes"),
        "",
    )
    return {
        "id": imdb_id,
        "title": str(payload.get("Title", "Untitled")).strip(),
        "overview": str(payload.get("Plot", "")).strip() if payload.get("Plot") != "N/A" else "",
        "rating": _parse_rating(payload.get("imdbRating")),
        "rating_count": _parse_votes(payload.get("imdbVotes")),
        "popularity": float(math.log1p(_parse_votes(payload.get("imdbVotes"))) if payload.get("imdbVotes") else 0.0),
        "year": str(payload.get("Year", "")).split("-", 1)[0],
        "release_date": str(payload.get("Released", "")) if payload.get("Released") != "N/A" else "",
        "genres": _parse_list(payload.get("Genre")),
        "poster_url": "" if payload.get("Poster") in (None, "N/A") else str(payload.get("Poster")),
        "backdrop_url": "",
        "external_url": _movie_url(imdb_id),
        "external_label": "IMDb",
        "director": ", ".join(_parse_list(payload.get("Director"))),
        "cast": _parse_list(payload.get("Actors")),
        "runtime": str(payload.get("Runtime", "")) if payload.get("Runtime") != "N/A" else "",
        "language": str(payload.get("Language", "")) if payload.get("Language") != "N/A" else "",
        "awards": str(payload.get("Awards", "")) if payload.get("Awards") != "N/A" else "",
        "rotten_tomatoes": rotten_tomatoes,
        "source": "omdb",
    }


def _normalise_db_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a database row dict into the app's response shape."""
    genres = [g.strip() for g in str(row.get("genre", "")).split() if g.strip()]
    cast = _parse_list(str(row.get("cast", "")))
    rating = float(row.get("rating") or 0.0)
    title = str(row.get("title", "")).strip()
    return {
        "id": f"db_{str(row.get('id', '')).strip() or _normalise_title(title)}",
        "title": title,
        "overview": str(row.get("overview", "")).strip(),
        "rating": rating,
        "rating_count": 0,
        "popularity": rating,
        "year": "",
        "release_date": "",
        "genres": genres,
        "poster_url": "",
        "backdrop_url": "",
        "external_url": "",
        "external_label": "",
        "director": str(row.get("director", "")).strip(),
        "cast": cast,
        "runtime": "",
        "language": "",
        "awards": "",
        "rotten_tomatoes": "",
        "source": "mysql",
    }


def _minimal_movie_from_title(title: str, source: str = "gemini") -> dict[str, Any]:
    """Create a metadata-light movie record when only a title is available."""
    clean_title = str(title).strip() or "Untitled"
    return {
        "id": f"{source}_{_normalise_title(clean_title).replace(' ', '_')}",
        "title": clean_title,
        "overview": "",
        "rating": 0.0,
        "rating_count": 0,
        "popularity": 0.0,
        "year": "",
        "release_date": "",
        "genres": [],
        "poster_url": "",
        "backdrop_url": "",
        "external_url": "",
        "external_label": "",
        "director": "",
        "cast": [],
        "runtime": "",
        "language": "",
        "awards": "",
        "rotten_tomatoes": "",
        "source": source,
    }


def _get_db_candidates() -> list[dict[str, Any]]:
    """Return candidate movies from MySQL, falling back to embedded sample data."""
    movies: list[dict[str, Any]] = []

    # Try live MySQL first.
    try:
        from database import fetch_movies  # noqa: PLC0415
        df = fetch_movies()
        if not df.empty:
            for _, row in df.iterrows():
                movies.append(_normalise_db_row(dict(row)))
            return movies
    except Exception:
        pass

    # Fall back to the embedded SAMPLE_MOVIES list.
    try:
        from database import SAMPLE_MOVIES  # noqa: PLC0415
        for i, item in enumerate(SAMPLE_MOVIES):
            # tuple layout: (title, genre, overview, director, cast, rating)
            movies.append(_normalise_db_row({
                "id": f"sample_{i}",
                "title": item[0],
                "genre": item[1],
                "overview": item[2],
                "director": item[3],
                "cast": item[4],
                "rating": item[5],
            }))
    except Exception:
        pass

    return movies


def _get_movie_by_title(title: str) -> dict[str, Any]:
    """Fetch full OMDb details by title with caching."""
    key = _normalise_title(title)
    with _cache_lock:
        if key in _movie_cache:
            return _movie_cache[key]

    payload = _omdb_get({"t": title, "type": "movie", "plot": "full"})
    movie = _normalise_movie(payload)

    with _cache_lock:
        _movie_cache[key] = movie
        if movie.get("id"):
            _movie_cache[str(movie["id"]).lower()] = movie
    return movie


def _get_movie_by_id(imdb_id: str) -> dict[str, Any]:
    """Fetch full OMDb details by IMDb ID with caching."""
    key = imdb_id.strip().lower()
    with _cache_lock:
        if key in _movie_cache:
            return _movie_cache[key]

    payload = _omdb_get({"i": imdb_id, "type": "movie", "plot": "full"})
    movie = _normalise_movie(payload)

    with _cache_lock:
        _movie_cache[key] = movie
        _movie_cache[_normalise_title(movie["title"])] = movie
    return movie


def _search_movies(search_term: str, pages: int = 1) -> list[dict[str, Any]]:
    """Search OMDb titles and return summary search results."""
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for page in range(1, pages + 1):
        try:
            payload = _omdb_get({"s": search_term, "type": "movie", "page": page})
        except (ValueError, RuntimeError):
            # If OMDb fails (for example invalid/expired key), fall back to
            # local candidate sources instead of failing the full request.
            break
        for item in payload.get("Search", []):
            imdb_id = str(item.get("imdbID", "")).strip().lower()
            if imdb_id and imdb_id not in seen_ids:
                seen_ids.add(imdb_id)
                results.append(item)
    return results


def _fallback_summary(seed_movie: dict[str, Any], recommendations: list[dict[str, Any]]) -> str:
    """Return a concise non-AI summary when Gemini is unavailable."""
    if not recommendations:
        return ""
    top_genres = recommendations[0].get("genres") or seed_movie.get("genres") or ["similar themes"]
    return (
        f"These picks are built from live OMDb movie data and lean toward "
        f"{', '.join(top_genres[:2])}, close to the mood of {seed_movie.get('title', 'your seed movie')}."
    )


def _score_candidate(
    movie: dict[str, Any],
    seed_movie: dict[str, Any],
    preferences: dict[str, Any],
) -> tuple[float, list[str]]:
    """Rank candidates using OMDb metadata plus user preferences."""
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

    movie_genres = {genre.lower() for genre in movie.get("genres", [])}
    seed_genres = {genre.lower() for genre in seed_movie.get("genres", [])}
    shared_genres = movie_genres & seed_genres
    cast_names = {name.lower() for name in movie.get("cast", [])}
    seed_cast = {name.lower() for name in seed_movie.get("cast", [])}
    director = str(movie.get("director", "")).lower()
    seed_director = str(seed_movie.get("director", "")).lower()

    score = movie.get("rating", 0.0) * 1.7
    score += min(math.log1p(movie.get("rating_count", 0)), 5.0)
    score += len(shared_genres) * 1.2

    reasons: list[str] = []
    if shared_genres:
        reasons.append(f"shares {', '.join(sorted(shared_genres)[:2])} with your seed movie")

    matched_preferred_genres = preferred_genres & movie_genres
    if matched_preferred_genres:
        score += 1.8
        reasons.append(f"matches your genre taste for {', '.join(sorted(matched_preferred_genres)[:2])}")

    if preferred_directors and director and any(name in director for name in preferred_directors):
        score += 1.4
        reasons.append("fits your preferred director profile")

    matched_cast = [name for name in preferred_cast if name in cast_names]
    if matched_cast:
        score += 1.4
        reasons.append(f"includes cast you like: {', '.join(matched_cast[:2])}")

    if seed_director and director and seed_director == director:
        score += 0.9
        reasons.append("comes from the same director as your seed movie")

    if cast_names & seed_cast:
        score += 0.8
        reasons.append("shares cast with your seed movie")

    return score, reasons


def _catalog_movies() -> list[dict[str, Any]]:
    """Build a live catalog from OMDb search results plus fallback titles."""
    candidate_titles: list[str] = []
    for term in TITLE_HINT_SEARCHES:
        for item in _search_movies(term, pages=1):
            title = str(item.get("Title", "")).strip()
            if title:
                candidate_titles.append(title)
    candidate_titles.extend(FALLBACK_CATALOG_TITLES)

    movies: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for title in candidate_titles:
        key = _normalise_title(title)
        if key in seen_titles:
            continue
        seen_titles.add(key)
        try:
            movies.append(_get_movie_by_title(title))
        except (ValueError, RuntimeError):
            continue

    # Include DB / sample-data movies not already covered by OMDb results.
    for movie in _get_db_candidates():
        key = _normalise_title(movie.get("title", ""))
        if key and key not in seen_titles:
            seen_titles.add(key)
            movies.append(movie)

    return movies


def _candidate_pool(seed_movie: dict[str, Any], preferences: dict[str, Any], top_n: int) -> tuple[list[dict[str, Any]], str, bool, str]:
    """Build a deduplicated candidate pool from Gemini and a live OMDb catalog."""
    ai_titles_result = generate_candidate_titles(seed_movie, preferences, top_n=top_n)
    ordered_titles = ai_titles_result.get("titles", []) + FALLBACK_CATALOG_TITLES

    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = {str(seed_movie.get("id", "")).lower()}
    seen_titles: set[str] = {_normalise_title(seed_movie.get("title", ""))}

    for title in ordered_titles:
        title_key = _normalise_title(title)
        if not title_key or title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        try:
            movie = _get_movie_by_title(title)
        except (ValueError, RuntimeError):
            # When OMDb is unavailable or rate-limited, preserve Gemini title
            # candidates using a metadata-light fallback record.
            if bool(ai_titles_result.get("enabled")):
                movie = _minimal_movie_from_title(title, source="gemini")
            else:
                continue
        movie_id = str(movie.get("id", "")).lower()
        if movie_id and movie_id in seen_ids:
            continue
        seen_ids.add(movie_id)
        candidates.append(movie)

    for movie in _catalog_movies():
        movie_id = str(movie.get("id", "")).lower()
        title_key = _normalise_title(movie.get("title", ""))
        if movie_id in seen_ids or title_key in seen_titles:
            continue
        seen_ids.add(movie_id)
        seen_titles.add(title_key)
        candidates.append(movie)

    return (
        candidates,
        str(ai_titles_result.get("summary", "")).strip(),
        bool(ai_titles_result.get("enabled")),
        str(ai_titles_result.get("model", "")).strip(),
    )


def _attach_ai_reasons(
    seed_movie: dict[str, Any],
    preferences: dict[str, Any],
    recommendations: list[dict[str, Any]],
    candidate_summary: str,
) -> tuple[str, bool, str]:
    """Attach Gemini reasons to recommendations when available."""
    ai_result = generate_recommendation_story(seed_movie, preferences, recommendations)
    reasons_by_title = ai_result.get("reasons", {})
    for movie in recommendations:
        title = movie.get("title", "")
        movie["ai_reason"] = reasons_by_title.get(title, movie.get("match_reason", ""))

    if ai_result.get("enabled"):
        return str(ai_result.get("summary", "")).strip(), True, str(ai_result.get("model", "")).strip()

    for movie in recommendations:
        if not movie.get("ai_reason"):
            movie["ai_reason"] = movie.get("match_reason", "")

    return candidate_summary or _fallback_summary(seed_movie, recommendations), False, ""


def reload_cache():
    """Clear live OMDb metadata caches."""
    global _titles_cache
    with _cache_lock:
        _titles_cache = None
        _movie_cache.clear()


def recommend_movies_with_preferences(
    movie_title: str,
    preferences: dict[str, Any],
    top_n: int = 5,
) -> dict[str, Any]:
    """Return recommendations from OMDb + MySQL + Gemini ranked by metadata and preferences."""
    # Try OMDb first for rich metadata; fall back to DB when OMDb key is absent.
    try:
        seed_movie = _get_movie_by_title(movie_title)
    except (RuntimeError, ValueError) as omdb_error:
        db_movies = _get_db_candidates()
        title_key = _normalise_title(movie_title)
        seed_movie = next(
            (m for m in db_movies if _normalise_title(m.get("title", "")) == title_key),
            None,
        )
        # If OMDb quota/auth fails and DB has no seed match, allow Gemini-first
        # recommendation generation from the user-provided title.
        if seed_movie is None and _is_omdb_limit_error(omdb_error) and gemini_enabled():
            seed_movie = _minimal_movie_from_title(movie_title, source="input")

        if seed_movie is None:
            raise ValueError(
                f"Movie '{movie_title}' not found. "
                "OMDb is unavailable and it is not in the local database."
            )
    min_rating = preferences.get("min_rating")

    candidates, candidate_summary, candidate_ai_used, candidate_ai_model = _candidate_pool(
        seed_movie,
        preferences,
        top_n,
    )

    ranked: list[tuple[float, dict[str, Any]]] = []
    for movie in candidates:
        if min_rating is not None and movie["rating"] < float(min_rating):
            continue

        score, reasons = _score_candidate(movie, seed_movie, preferences)
        movie["match_reason"] = "; ".join(reasons) if reasons else "A strong live-data match from OMDb."
        movie["score"] = round(score, 3)
        ranked.append((score, movie))

    ranked.sort(
        key=lambda item: (
            item[0],
            item[1].get("rating", 0.0),
            item[1].get("rating_count", 0),
        ),
        reverse=True,
    )
    recommendations = [movie for _, movie in ranked[:top_n]]
    ai_summary, reasons_ai_used, reasons_ai_model = _attach_ai_reasons(
        seed_movie,
        preferences,
        recommendations,
        candidate_summary,
    )

    # Track all sources that provided candidates (not just final top-N)
    active_sources: set[str] = {"omdb"}  # OMDb is always queried for catalog
    for movie in candidates:
        src = movie.get("source", "")
        if src:
            active_sources.add(src)
    if candidate_ai_used or reasons_ai_used:
        active_sources.add("gemini")

    return {
        "seed_movie": seed_movie,
        "recommendations": recommendations,
        "ai_summary": ai_summary,
        "ai_enabled": candidate_ai_used or reasons_ai_used,
        "ai_model": reasons_ai_model or candidate_ai_model,
        "source": "+".join(sorted(active_sources)),
        "data_sources": sorted(active_sources),
    }


def recommend_by_genre(genre: str, top_n: int = 5) -> list[dict[str, Any]]:
    """Return live catalog movies filtered by genre using OMDb metadata."""
    query = genre.strip().lower()
    results = [
        movie for movie in _catalog_movies()
        if any(query in item.lower() for item in movie.get("genres", []))
    ]
    if not results:
        raise ValueError(f"No movies found online for genre '{genre}'.")

    results.sort(key=lambda movie: (movie.get("rating", 0.0), movie.get("rating_count", 0)), reverse=True)
    return results[:top_n]


def recommend_top_rated(limit: int = 10) -> list[dict[str, Any]]:
    """Return highly rated live catalog movies from OMDb."""
    results = _catalog_movies()
    results.sort(key=lambda movie: (movie.get("rating", 0.0), movie.get("rating_count", 0)), reverse=True)
    return results[:limit]


def list_all_titles(limit: int = 80) -> list[str]:
    """Return a cached list of live OMDb title suggestions."""
    global _titles_cache

    with _cache_lock:
        if _titles_cache is not None and len(_titles_cache) >= limit:
            return _titles_cache[:limit]

    titles: list[str] = []
    seen_titles: set[str] = set()
    for term in TITLE_HINT_SEARCHES:
        for item in _search_movies(term, pages=1):
            title = str(item.get("Title", "")).strip()
            key = _normalise_title(title)
            if title and key not in seen_titles:
                seen_titles.add(key)
                titles.append(title)

    titles.extend([title for title in FALLBACK_CATALOG_TITLES if _normalise_title(title) not in seen_titles])

    # Include DB / sample titles not already listed.
    for movie in _get_db_candidates():
        db_title = movie.get("title", "")
        key = _normalise_title(db_title)
        if db_title and key not in seen_titles:
            seen_titles.add(key)
            titles.append(db_title)

    with _cache_lock:
        _titles_cache = titles

    return titles[:limit]

