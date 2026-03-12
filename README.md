# Movie Recommendation System

A Flask movie recommendation website that now uses live movie data from TMDB instead of a local database. It can also call Gemini 1.5 Flash to generate short, better-written recommendation explanations.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Web app | Flask |
| Live movie catalog | TMDB API |
| AI explanation layer | Gemini 1.5 Flash |
| Frontend | Jinja2, CSS, JavaScript |

## Project Structure

```text
movie-recommendation/
├── ai_service.py     # Gemini integration
├── app.py            # Flask website + API routes
├── recommender.py    # TMDB live-data recommendation engine
├── templates/        # Jinja2 templates
├── static/           # CSS and JavaScript assets
├── requirements.txt  # Python dependencies
└── README.md
```

## API Keys

You need:

1. `TMDB_API_KEY` for live movie data. This is required.
2. `GEMINI_API_KEY` for Gemini 1.5 Flash explanations. This is optional.

### Windows PowerShell example

```powershell
$env:TMDB_API_KEY="your_tmdb_key_here"
$env:GEMINI_API_KEY="your_gemini_key_here"
```

If you skip `GEMINI_API_KEY`, the app still works and falls back to rule-based explanation text.

## Installation

```powershell
cd movie-recommendation
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Running the App

```powershell
python app.py
```

Open:

- Website: `http://localhost:5000`
- API index: `http://localhost:5000/api`

## Web UI Features

- Live movie search suggestions from TMDB popular and trending titles
- Recommendation cards with posters, overview, genres, year, and rating
- Preference filters for genre, director, cast, and minimum rating
- Gemini-generated summary and per-movie reasons when configured
- Responsive UI for desktop and mobile

## API Reference

### `GET /recommend`

Returns online recommendations for a movie title.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `movie` | string | Yes | - | Seed movie title |
| `top_n` | int | No | 5 | Number of recommendations |
| `preferred_genres` | string | No | - | Comma-separated genre preferences |
| `preferred_directors` | string | No | - | Comma-separated director preferences |
| `preferred_cast` | string | No | - | Comma-separated cast preferences |
| `min_rating` | float | No | - | Minimum TMDB rating |

Example:

```text
GET /recommend?movie=Inception&top_n=5&preferred_genres=Sci-Fi,Thriller&min_rating=7.5
```

Response shape:

```json
{
  "input_movie": "Inception",
  "source": "tmdb",
  "seed_movie": {
    "title": "Inception",
    "year": "2010"
  },
  "ai_summary": "These picks stay close to Inception's cerebral sci-fi tone.",
  "ai_enabled": true,
  "ai_model": "gemini-1.5-flash",
  "recommendations": [
    {
      "title": "Interstellar",
      "rating": 8.4,
      "genres": ["Adventure", "Drama", "Science Fiction"],
      "ai_reason": "It matches your taste for cerebral science fiction with emotional scale."
    }
  ]
}
```

### `GET /recommend/genre`

Returns live top movies for a genre from TMDB.

### `GET /recommend/top-rated`

Returns live top-rated movies from TMDB.

### `GET /movies`

Returns cached popular and trending movie titles for autocomplete.

### `POST /cache/reload`

Clears cached TMDB metadata and title suggestions.

### `GET /health`

Returns service health plus whether Gemini is configured.

## How It Works

```text
TMDB API
   |
   v
recommender.py
   |- search movie by title
   |- fetch recommendations, similar titles, and genre-based candidates
   |- rank results using TMDB metadata + user preferences
   |- optionally ask Gemini 1.5 Flash for summary and reasons
   |
   v
app.py
   |- renders website
   |- exposes JSON API routes
```

## Notes

- `database.py` is now legacy and is no longer used by the app runtime.
- `POST /seed/movies` is retained only as a compatibility endpoint and does nothing.
- For production on Windows, use a proper WSGI server such as Waitress instead of Flask debug mode.
