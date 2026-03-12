"""Flask app exposing both a web UI and REST API endpoints."""

import os

from flask import Flask, flash, jsonify, render_template, request

from ai_service import gemini_enabled
from env_utils import get_env_value, load_local_env

from recommender import (
    recommend_movies_with_preferences,
    recommend_by_genre,
    recommend_top_rated,
    list_all_titles,
    reload_cache,
)

app = Flask(__name__)
load_local_env()
app.secret_key = get_env_value("FLASK_SECRET_KEY", "dev-secret-key")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _error(message: str, status: int = 400):
    """Return a standardised JSON error response."""
    return jsonify({"error": message}), status


def _split_csv(value: str) -> list[str]:
    """Convert comma-separated query value into a clean list."""
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_preferences(source) -> dict:
    """Build a preference dictionary from request args or form data."""
    preferred_genres = _split_csv(source.get("preferred_genres", ""))
    preferred_directors = _split_csv(source.get("preferred_directors", ""))
    preferred_cast = _split_csv(source.get("preferred_cast", ""))

    min_rating_raw = source.get("min_rating", "").strip()
    min_rating = None
    if min_rating_raw:
        min_rating = float(min_rating_raw)

    return {
        "preferred_genres": preferred_genres,
        "preferred_directors": preferred_directors,
        "preferred_cast": preferred_cast,
        "min_rating": min_rating,
    }


def _has_any_preferences(preferences: dict) -> bool:
    """Check if at least one preference is provided by the user."""
    return any(
        [
            preferences["preferred_genres"],
            preferences["preferred_directors"],
            preferences["preferred_cast"],
            preferences["min_rating"] is not None,
        ]
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET", "POST"])
def home():
    """Render the website home page and process recommendation requests."""
    titles: list[str] = []
    top_rated_movies: list[dict] = []
    recommendations: list[dict] = []
    selected_movie: dict | None = None
    ai_summary = ""
    ai_used = False
    ai_model = ""
    request_state = {
        "movie": "",
        "top_n": 6,
        "preferred_genres": "",
        "preferred_directors": "",
        "preferred_cast": "",
        "min_rating": "",
    }
    service_error = None

    try:
        titles = list_all_titles()
        top_rated_movies = recommend_top_rated(limit=8)
    except RuntimeError as e:
        service_error = str(e)

    if request.method == "POST" and not service_error:
        request_state = {
            "movie": request.form.get("movie", "").strip(),
            "top_n": request.form.get("top_n", "6").strip(),
            "preferred_genres": request.form.get("preferred_genres", "").strip(),
            "preferred_directors": request.form.get("preferred_directors", "").strip(),
            "preferred_cast": request.form.get("preferred_cast", "").strip(),
            "min_rating": request.form.get("min_rating", "").strip(),
        }

        if not request_state["movie"]:
            flash("Pick a movie title before requesting recommendations.", "error")
        else:
            try:
                top_n = int(request_state["top_n"] or "6")
                if top_n < 1 or top_n > 20:
                    raise ValueError
            except ValueError:
                flash("'Top picks' must be a number from 1 to 20.", "error")
                top_n = 6

            try:
                min_rating_raw = request_state["min_rating"]
                if min_rating_raw:
                    min_rating_value = float(min_rating_raw)
                    if min_rating_value < 0 or min_rating_value > 10:
                        raise ValueError

                preferences = _parse_preferences(request.form)

                result_bundle = recommend_movies_with_preferences(
                    request_state["movie"],
                    preferences=preferences,
                    top_n=top_n,
                )
                recommendations = result_bundle["recommendations"]
                selected_movie = result_bundle["seed_movie"]
                ai_summary = result_bundle["ai_summary"]
                ai_used = result_bundle["ai_enabled"]
                ai_model = result_bundle["ai_model"]
            except ValueError as e:
                flash(str(e), "error")
            except RuntimeError as e:
                flash(str(e), "error")

    return render_template(
        "index.html",
        titles=titles,
        top_rated_movies=top_rated_movies,
        recommendations=recommendations,
        selected_movie=selected_movie,
        ai_summary=ai_summary,
        ai_used=ai_used,
        ai_model=ai_model,
        gemini_ready=gemini_enabled(),
        request_state=request_state,
        service_error=service_error,
    )


@app.route("/api", methods=["GET"])
def api_home():
    """API index route."""
    omdb_ready = bool(os.getenv("OMDB_API_KEY", "").strip())
    try:
        from database import SAMPLE_MOVIES as _  # noqa: F401, PLC0415
        mysql_ready = True
    except Exception:
        mysql_ready = False
    return jsonify({
        "message": "Movie Recommendation API – 3 data sources: MySQL, OMDb, Gemini.",
        "data_sources": {
            "mysql": {"enabled": mysql_ready, "description": "Local DB (MySQL) or 30-movie sample fallback"},
            "omdb": {"enabled": omdb_ready, "description": "Live OMDb movie metadata"},
            "gemini": {"enabled": gemini_enabled(), "description": "AI candidate suggestions & explanations"},
        },
        "required_environment_variables": ["OMDB_API_KEY"],
        "optional_environment_variables": ["GEMINI_API_KEY", "GEMINI_MODEL"],
        "notes": [
            "MySQL source uses live DB when available, otherwise falls back to 30 embedded sample movies.",
            "OMDb provides rich live metadata (poster, IMDb rating, cast, etc.).",
            "Gemini improves candidate selection and generates recommendation explanations.",
        ],
        "endpoints": {
            "health": "/health",
            "preferences_questions": "/preferences/questions",
            "recommend": (
                "/recommend?movie=Inception&top_n=5"
                "&preferred_genres=Sci-Fi,Thriller&min_rating=8"
            ),
            "recommend_genre": "/recommend/genre?genre=Action&top_n=5",
            "top_rated": "/recommend/top-rated?limit=10",
            "movies": "/movies",
            "cache_reload": "POST /cache/reload",
        },
    }), 200


@app.route("/preferences/questions", methods=["GET"])
@app.route("/api/preferences/questions", methods=["GET"])
def preference_questions():
    """Return preference fields expected before recommendations."""
    return jsonify({
        "message": "Preferences are optional, but they improve ranking and Gemini explanations.",
        "fields": [
            "preferred_genres (comma separated)",
            "preferred_directors (comma separated)",
            "preferred_cast (comma separated)",
            "min_rating (0 to 10)",
        ],
        "example": (
            "/recommend?movie=Inception&top_n=5"
            "&preferred_genres=Sci-Fi,Thriller&preferred_directors=Christopher Nolan"
            "&min_rating=8"
        ),
    }), 200

@app.route("/recommend", methods=["GET"])
@app.route("/api/recommend", methods=["GET"])
def recommend():
    """
    GET /recommend?movie=Inception&top_n=5

    Returns preference-aware recommendations for the given movie title.

    Query Parameters
    ----------------
    movie  : str  (required) – Movie title to get recommendations for.
    top_n                : int  (optional, default 5) – Number of recommendations.
    preferred_genres     : str  (optional, comma-separated)
    preferred_directors  : str  (optional, comma-separated)
    preferred_cast       : str  (optional, comma-separated)
    min_rating           : float (optional, 0 to 10)
    """
    movie_title = request.args.get("movie", "").strip()
    if not movie_title:
        return _error("Query parameter 'movie' is required.", 400)

    # Validate top_n
    try:
        top_n = int(request.args.get("top_n", 5))
        if top_n < 1:
            raise ValueError
    except ValueError:
        return _error("'top_n' must be a positive integer.", 400)

    preferred_genres = _split_csv(request.args.get("preferred_genres", ""))
    preferred_directors = _split_csv(request.args.get("preferred_directors", ""))
    preferred_cast = _split_csv(request.args.get("preferred_cast", ""))

    min_rating_raw = request.args.get("min_rating", "").strip()
    min_rating = None
    if min_rating_raw:
        try:
            min_rating = float(min_rating_raw)
            if min_rating < 0 or min_rating > 10:
                return _error("'min_rating' must be between 0 and 10.", 400)
        except ValueError:
            return _error("'min_rating' must be a valid number.", 400)

    preferences = {
        "preferred_genres": preferred_genres,
        "preferred_directors": preferred_directors,
        "preferred_cast": preferred_cast,
        "min_rating": min_rating,
    }

    try:
        result_bundle = recommend_movies_with_preferences(
            movie_title,
            preferences=preferences,
            top_n=top_n,
        )
    except ValueError as e:
        return _error(str(e), 404)
    except RuntimeError as e:
        return _error(str(e), 500)

    return jsonify({
        "input_movie": movie_title,
        "preferences_used": preferences,
        "source": result_bundle["source"],
        "data_sources": result_bundle.get("data_sources", []),
        "seed_movie": result_bundle["seed_movie"],
        "ai_summary": result_bundle["ai_summary"],
        "ai_enabled": result_bundle["ai_enabled"],
        "ai_model": result_bundle["ai_model"],
        "recommendations": result_bundle["recommendations"],
    }), 200


@app.route("/recommend/genre", methods=["GET"])
@app.route("/api/recommend/genre", methods=["GET"])
def recommend_genre():
    """
    GET /recommend/genre?genre=Action&top_n=5

    Returns top-rated movies that match the requested genre.

    Query Parameters
    ----------------
    genre  : str  (required) – Genre to filter on (partial match).
    top_n  : int  (optional, default 5) – Number of results.
    """
    genre = request.args.get("genre", "").strip()
    if not genre:
        return _error("Query parameter 'genre' is required.", 400)

    try:
        top_n = int(request.args.get("top_n", 5))
        if top_n < 1:
            raise ValueError
    except ValueError:
        return _error("'top_n' must be a positive integer.", 400)

    try:
        results = recommend_by_genre(genre, top_n=top_n)
    except ValueError as e:
        return _error(str(e), 404)
    except RuntimeError as e:
        return _error(str(e), 500)

    return jsonify({
        "genre": genre,
        "recommendations": results,
    }), 200


@app.route("/recommend/top-rated", methods=["GET"])
@app.route("/api/recommend/top-rated", methods=["GET"])
def top_rated():
    """
    GET /recommend/top-rated?limit=10

    Returns the globally top-rated movies.

    Query Parameters
    ----------------
    limit : int (optional, default 10) – How many movies to return.
    """
    try:
        limit = int(request.args.get("limit", 10))
        if limit < 1:
            raise ValueError
    except ValueError:
        return _error("'limit' must be a positive integer.", 400)

    try:
        results = recommend_top_rated(limit=limit)
    except RuntimeError as e:
        return _error(str(e), 500)

    return jsonify({
        "top_rated_movies": results,
    }), 200


@app.route("/movies", methods=["GET"])
@app.route("/api/movies", methods=["GET"])
def list_movies():
    """
    GET /movies

    Returns a cached set of live OMDb movie titles for autocomplete.
    """
    try:
        titles = list_all_titles()
    except RuntimeError as e:
        return _error(str(e), 500)

    return jsonify({
        "total": len(titles),
        "movies": titles,
    }), 200


@app.route("/cache/reload", methods=["POST"])
@app.route("/api/cache/reload", methods=["POST"])
def cache_reload():
    """
    POST /cache/reload

    Clears cached OMDb metadata and title suggestions.
    """
    try:
        reload_cache()
    except RuntimeError as e:
        return _error(str(e), 500)

    return jsonify({"message": "Cache reloaded successfully."}), 200


@app.route("/seed/movies", methods=["POST"])
@app.route("/api/seed/movies", methods=["POST"])
def seed_db_movies():
    """
    POST /seed/movies

    Insert sample movies into MySQL so the MySQL source has data.
    Falls back gracefully when MySQL is not configured.
    """
    try:
        from database import seed_movies  # noqa: PLC0415
        inserted = seed_movies()
        return jsonify({
            "message": f"Seeded {inserted} movies into MySQL.",
            "source": "mysql",
        }), 200
    except RuntimeError as e:
        return jsonify({
            "message": "MySQL is not available; using embedded sample data instead.",
            "detail": str(e),
        }), 200


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """Simple liveness probe."""
    omdb_ready = bool(os.getenv("OMDB_API_KEY", "").strip())
    try:
        from database import SAMPLE_MOVIES as _  # noqa: F401, PLC0415
        mysql_ready = True
    except Exception:
        mysql_ready = False
    return jsonify({
        "status": "ok",
        "data_sources": {
            "mysql": mysql_ready,
            "omdb": omdb_ready,
            "gemini": gemini_enabled(),
        },
    }), 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # debug=False in production; use a proper WSGI server (gunicorn/waitress)
    app.run(host="0.0.0.0", port=5000, debug=True)
