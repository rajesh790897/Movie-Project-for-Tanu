"""Live movie recommendation engine powered by TMDB data."""

from __future__ import annotations

import math
import os
import re
import threading
from typing import Any

import requests

from ai_service import generate_recommendation_story


TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"
TMDB_SITE_URL = "https://www.themoviedb.org/movie"
REQUEST_TIMEOUT = 15

_session = requests.Session()
_cache_lock = threading.Lock()
_genre_lookup: dict[int, str] | None = None
_popular_titles_cache: list[str] | None = None


def _normalise_title(title: str) -> str:
    """Lower-case and collapse whitespace for matching titles."""
    return re.sub(r"\s+", " ", title.strip().lower())


def _require_tmdb_api_key() -> str:
    """Return the TMDB API key or raise a runtime error with guidance."""
    api_key = os.getenv("TMDB_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "TMDB_API_KEY is not set. Create a TMDB API key and add it as an "
            "environment variable before starting the app."
        )
    return api_key


def _tmdb_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make an authenticated GET request to TMDB."""
    query = dict(params or {})
    query["api_key"] = _require_tmdb_api_key()

    try:
        response = _session.get(
            f"{TMDB_BASE_URL}{path}",
            params=query,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Unable to reach TMDB right now: {exc}") from exc

    return response.json()


def _poster_url(path: str | None, size: str = "w500") -> str:
    """Build a TMDB image URL."""
    if not path:
        return ""
    return f"{TMDB_IMAGE_BASE_URL}/{size}{path}"


def _extract_year(release_date: str | None) -> str:
    """Extract the release year from a date string."""
    if not release_date:
        return ""
    return str(release_date).split("-", 1)[0]


def _fetch_genre_lookup(force_reload: bool = False) -> dict[int, str]:
    """Fetch and cache TMDB movie genres."""
    global _genre_lookup

    with _cache_lock:
        if _genre_lookup is not None and not force_reload:
            return _genre_lookup

        payload = _tmdb_get("/genre/movie/list", {"language": "en-US"})
        _genre_lookup = {
            int(item["id"]): item["name"]
            for item in payload.get("genres", [])
            if "id" in item and "name" in item
        }
        return _genre_lookup


def _find_genre_ids(genre_query: str) -> list[int]:
    """Resolve a free-text genre query to one or more TMDB genre ids."""
    lookup = _fetch_genre_lookup()
    query = genre_query.strip().lower()
    return [genre_id for genre_id, name in lookup.items() if query in name.lower()]


def _extract_director(credits: dict[str, Any] | None) -> str:
    """Extract the director name from a credits payload."""
    if not credits:
        return ""
    for crew_member in credits.get("crew", []):
        if crew_member.get("job") == "Director":
            return str(crew_member.get("name", "")).strip()
    return ""


def _extract_cast(credits: dict[str, Any] | None, limit: int = 5) -> list[str]:
    """Return the top billed cast names."""
    if not credits:
        return []
    names = []
    for person in credits.get("cast", [])[:limit]:
        name = str(person.get("name", "")).strip()
        if name:
            names.append(name)
    return names


def _normalise_movie(movie: dict[str, Any]) -> dict[str, Any]:
    """Convert a TMDB movie payload into the app's response shape."""
    genre_lookup = _fetch_genre_lookup()
    genres = movie.get("genres") or []
    if genres:
        genre_names = [item.get("name", "") for item in genres if item.get("name")]
    else:
        genre_names = [
            genre_lookup[genre_id]
            for genre_id in movie.get("genre_ids", [])
            if genre_id in genre_lookup
        ]

    credits = movie.get("credits") or {}
    movie_id = movie.get("id")
    return {
        "id": movie_id,
        "title": movie.get("title") or movie.get("name") or "Untitled",
        "overview": str(movie.get("overview", "")).strip(),
        "rating": float(movie.get("vote_average", 0.0) or 0.0),
        "rating_count": int(movie.get("vote_count", 0) or 0),
        "popularity": float(movie.get("popularity", 0.0) or 0.0),
        "year": _extract_year(movie.get("release_date")),
        "release_date": movie.get("release_date", ""),
        "genres": genre_names,
        "poster_url": _poster_url(movie.get("poster_path")),
        "backdrop_url": _poster_url(movie.get("backdrop_path"), size="w780"),
        "tmdb_url": f"{TMDB_SITE_URL}/{movie_id}" if movie_id else "",
        "director": _extract_director(credits),
        "cast": _extract_cast(credits),
        "source": "tmdb",
    }


def _search_movie(movie_title: str) -> dict[str, Any]:
    """Search TMDB and return the best candidate for a movie title."""
    payload = _tmdb_get("/search/movie", {"query": movie_title, "include_adult": "false"})
    results = payload.get("results", [])
    if not results:
        raise ValueError(f"Movie '{movie_title}' was not found on TMDB.")

    desired_key = _normalise_title(movie_title)
    for candidate in results:
        if _normalise_title(str(candidate.get("title", ""))) == desired_key:
            return candidate

    return results[0]


def _movie_details(movie_id: int) -> dict[str, Any]:
    """Fetch a movie with credits included."""
    return _tmdb_get(
        f"/movie/{movie_id}",
        {"append_to_response": "credits", "language": "en-US"},
    )


def _combine_candidates(seed_movie: dict[str, Any], top_n: int) -> list[dict[str, Any]]:
    """Fetch recommendation candidates from several TMDB endpoints."""
    movie_id = int(seed_movie["id"])
    combined: list[dict[str, Any]] = []

    for path in (f"/movie/{movie_id}/recommendations", f"/movie/{movie_id}/similar"):
        payload = _tmdb_get(path, {"language": "en-US", "page": 1})
        combined.extend(payload.get("results", []))

    genre_ids = seed_movie.get("genre_ids") or [item["id"] for item in seed_movie.get("genres", [])]
    if genre_ids:
        discover_payload = _tmdb_get(
            "/discover/movie",
            {
                "language": "en-US",
                "sort_by": "popularity.desc",
                "include_adult": "false",
                "vote_count.gte": 100,
                "with_genres": ",".join(str(genre_id) for genre_id in genre_ids[:3]),
                "page": 1,
            },
        )
        combined.extend(discover_payload.get("results", []))

    seen_ids: set[int] = {movie_id}
    unique_candidates: list[dict[str, Any]] = []
    for movie in combined:
        candidate_id = movie.get("id")
        if not candidate_id or candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)
        unique_candidates.append(movie)

    return unique_candidates[: max(top_n * 4, 18)]


def _score_candidate(
    movie: dict[str, Any],
    seed_movie: dict[str, Any],
    preferences: dict[str, Any],
) -> tuple[float, list[str]]:
    """Rank candidates using TMDB metadata plus user preferences."""
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

    score = movie.get("rating", 0.0) * 1.7
    score += min(math.log1p(movie.get("popularity", 0.0) or 0.0), 5.0)
    score += len(shared_genres) * 1.2

    director = str(movie.get("director", "")).strip().lower()
    cast_names = {name.lower() for name in movie.get("cast", [])}

    reasons: list[str] = []
    if shared_genres:
        reasons.append(f"shares {', '.join(sorted(shared_genres)[:2])} energy")

    matched_preferred_genres = preferred_genres & movie_genres
    if matched_preferred_genres:
        score += 2.0
        reasons.append(f"matches your genre taste for {', '.join(sorted(matched_preferred_genres)[:2])}")

    if preferred_directors and director and any(name in director for name in preferred_directors):
        score += 1.8
        reasons.append("aligns with your director preference")

    matched_cast = [name for name in preferred_cast if name in cast_names]
    if matched_cast:
        score += 1.5
        reasons.append(f"includes cast you like: {', '.join(matched_cast[:2])}")

    if seed_movie.get("director") and director == seed_movie.get("director", "").lower():
        score += 0.9
        reasons.append("comes from the same director as your seed movie")

    shared_cast = cast_names & {name.lower() for name in seed_movie.get("cast", [])}
    if shared_cast:
        score += 0.8
        reasons.append("shares cast with your seed movie")

    return score, reasons


def _fallback_ai_summary(seed_movie: dict[str, Any], recommendations: list[dict[str, Any]]) -> str:
    """Return a concise non-AI summary when Gemini is unavailable."""
    if not recommendations:
        return ""
    top_genres = recommendations[0].get("genres") or seed_movie.get("genres") or ["similar storytelling"]
    genre_label = ", ".join(top_genres[:2])
    return (
        f"These picks are based on live TMDB data and lean toward {genre_label}, "
        f"close to the feel of {seed_movie.get('title', 'your selected movie')}."
    )


def _attach_ai_reasons(
    seed_movie: dict[str, Any],
    preferences: dict[str, Any],
    recommendations: list[dict[str, Any]],
) -> tuple[str, bool, str]:
    """Attach Gemini reasons to recommendations when available."""
    ai_result = generate_recommendation_story(seed_movie, preferences, recommendations)
    reasons_by_title = ai_result.get("reasons", {})
    for movie in recommendations:
        title = movie.get("title", "")
        movie["ai_reason"] = reasons_by_title.get(title, movie.get("match_reason", ""))

    if ai_result.get("enabled"):
        return ai_result.get("summary", ""), True, ai_result.get("model", "")

    for movie in recommendations:
        if not movie.get("ai_reason"):
            movie["ai_reason"] = movie.get("match_reason", "")

    return _fallback_ai_summary(seed_movie, recommendations), False, ""


def reload_cache():
    """Clear live metadata caches."""
    global _genre_lookup, _popular_titles_cache
    with _cache_lock:
        _genre_lookup = None
        _popular_titles_cache = None


def recommend_movies_with_preferences(
    movie_title: str,
    preferences: dict[str, Any],
    top_n: int = 5,
) -> dict[str, Any]:
    """Return live recommendations from TMDB ranked by metadata and preferences."""
    seed_candidate = _search_movie(movie_title)
    seed_details = _movie_details(int(seed_candidate["id"]))
    seed_movie = _normalise_movie(seed_details)
    min_rating = preferences.get("min_rating")

    ranked: list[tuple[float, dict[str, Any]]] = []
    for candidate in _combine_candidates(seed_candidate, top_n=top_n):
        movie = _normalise_movie(_movie_details(int(candidate["id"])))

        if min_rating is not None and movie["rating"] < float(min_rating):
            continue

        score, reasons = _score_candidate(movie, seed_movie, preferences)
        movie["match_reason"] = "; ".join(reasons) if reasons else "A strong live-data match from TMDB."
        movie["score"] = round(score, 3)
        ranked.append((score, movie))

    ranked.sort(
        key=lambda item: (
            item[0],
            item[1].get("rating", 0.0),
            item[1].get("popularity", 0.0),
        ),
        reverse=True,
    )
    recommendations = [movie for _, movie in ranked[:top_n]]
    summary, ai_enabled, ai_model = _attach_ai_reasons(seed_movie, preferences, recommendations)

    return {
        "seed_movie": seed_movie,
        "recommendations": recommendations,
        "ai_summary": summary,
        "ai_enabled": ai_enabled,
        "ai_model": ai_model,
        "source": "tmdb",
    }


def recommend_by_genre(genre: str, top_n: int = 5) -> list[dict[str, Any]]:
    """Return top live movies for a requested genre using TMDB discover."""
    genre_ids = _find_genre_ids(genre)
    if not genre_ids:
        raise ValueError(f"No TMDB genre matched '{genre}'.")

    payload = _tmdb_get(
        "/discover/movie",
        {
            "language": "en-US",
            "include_adult": "false",
            "sort_by": "vote_average.desc",
            "vote_count.gte": 500,
            "with_genres": ",".join(str(genre_id) for genre_id in genre_ids[:2]),
            "page": 1,
        },
    )
    results = payload.get("results", [])
    if not results:
        raise ValueError(f"No movies found online for genre '{genre}'.")

    return [_normalise_movie(movie) for movie in results[:top_n]]


def recommend_top_rated(limit: int = 10) -> list[dict[str, Any]]:
    """Return live top-rated movies from TMDB."""
    results: list[dict[str, Any]] = []
    page = 1
    while len(results) < limit:
        payload = _tmdb_get("/movie/top_rated", {"language": "en-US", "page": page})
        page_results = payload.get("results", [])
        if not page_results:
            break
        results.extend(page_results)
        page += 1

    return [_normalise_movie(movie) for movie in results[:limit]]


def list_all_titles(limit: int = 80) -> list[str]:
    """Return a cached list of live popular movie titles for autocomplete hints."""
    global _popular_titles_cache

    with _cache_lock:
        if _popular_titles_cache is not None and len(_popular_titles_cache) >= limit:
            return _popular_titles_cache[:limit]

    titles: list[str] = []
    seen_titles: set[str] = set()
    for path in ("/movie/popular", "/trending/movie/week"):
        payload = _tmdb_get(path, {"language": "en-US", "page": 1})
        for movie in payload.get("results", []):
            title = str(movie.get("title", "")).strip()
            normalised = _normalise_title(title)
            if title and normalised not in seen_titles:
                seen_titles.add(normalised)
                titles.append(title)

    with _cache_lock:
        _popular_titles_cache = titles

    return titles[:limit]
