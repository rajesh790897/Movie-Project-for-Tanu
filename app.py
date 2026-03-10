"""
app.py
------
Flask REST API for the Movie Recommendation System.

Endpoints
---------
GET /recommend?movie=<title>&top_n=<int>
    Content-based recommendations for a given movie title.

GET /recommend/genre?genre=<genre>&top_n=<int>
    Top-rated movies filtered by genre.

GET /recommend/top-rated?limit=<int>
    Globally top-rated movies.

GET /movies
    List all available movie titles.

POST /cache/reload
    Force-refresh the in-memory similarity cache.
"""

from flask import Flask, request, jsonify

from recommender import (
    recommend_movies_with_preferences,
    recommend_by_genre,
    recommend_top_rated,
    list_all_titles,
    reload_cache,
)
from database import seed_movies

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _error(message: str, status: int = 400):
    """Return a standardised JSON error response."""
    return jsonify({"error": message}), status


def _split_csv(value: str) -> list[str]:
    """Convert comma-separated query value into a clean list."""
    return [item.strip() for item in value.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    """API index route to avoid 404 on the base URL."""
    return jsonify({
        "message": "Movie Recommendation API is running.",
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
            "seed_movies": "POST /seed/movies",
            "cache_reload": "POST /cache/reload",
        },
    }), 200


@app.route("/preferences/questions", methods=["GET"])
def preference_questions():
    """Return preference fields expected before recommendations."""
    return jsonify({
        "message": "Provide at least one preference before requesting recommendations.",
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

    if not any([preferred_genres, preferred_directors, preferred_cast, min_rating_raw]):
        return jsonify({
            "error": "Please provide user preferences before requesting recommendations.",
            "required": "At least one preference is required.",
            "fields": [
                "preferred_genres",
                "preferred_directors",
                "preferred_cast",
                "min_rating",
            ],
            "questions_endpoint": "/preferences/questions",
        }), 400

    preferences = {
        "preferred_genres": preferred_genres,
        "preferred_directors": preferred_directors,
        "preferred_cast": preferred_cast,
        "min_rating": min_rating,
    }

    try:
        recommendations = recommend_movies_with_preferences(
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
        "recommendations": recommendations,
    }), 200


@app.route("/recommend/genre", methods=["GET"])
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
def list_movies():
    """
    GET /movies

    Returns an alphabetically sorted list of all movie titles in the DB.
    Useful for populating a search/autocomplete UI.
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
def cache_reload():
    """
    POST /cache/reload

    Forces a full reload of the similarity matrix from the database.
    Call this endpoint after inserting new movies into the DB without
    restarting the server.
    """
    try:
        reload_cache()
    except RuntimeError as e:
        return _error(str(e), 500)

    return jsonify({"message": "Cache reloaded successfully."}), 200


@app.route("/seed/movies", methods=["POST"])
def seed_db_movies():
    """
    POST /seed/movies

    Inserts 30 sample movies if missing and refreshes in-memory cache.
    """
    try:
        inserted_count = seed_movies()
        reload_cache()
    except RuntimeError as e:
        return _error(str(e), 500)

    return jsonify({
        "message": "Movie seed completed.",
        "inserted_count": inserted_count,
    }), 200


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """Simple liveness probe."""
    return jsonify({"status": "ok"}), 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # debug=False in production; use a proper WSGI server (gunicorn/waitress)
    app.run(host="0.0.0.0", port=5000, debug=True)
