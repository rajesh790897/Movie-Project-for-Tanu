# Movie Recommendation System

This project is a Flask-based movie recommendation web application with a browser UI and JSON API. It combines three data sources:

1. OMDb for live movie metadata such as title, plot, genre, cast, poster, IMDb rating, and IMDb ID.
2. MySQL for local movie records when a database is available.
3. Gemini for optional AI-assisted candidate suggestions and short recommendation explanations.

If MySQL is not available, the app falls back to the embedded sample movie list in `database.py`. If Gemini is not configured, the app still works and uses rule-based explanation text.

## What This System Does

- Lets a user enter a movie they already like.
- Accepts optional taste filters: preferred genres, directors, actors, and minimum rating.
- Finds recommendation candidates from OMDb, local MySQL data, and built-in sample data.
- Scores candidates using metadata similarity and user preferences.
- Optionally asks Gemini to improve candidate selection and generate short explanations.
- Shows results in a web UI and also exposes them through REST-style endpoints.

## Main Technologies

| Layer | Technology |
|-------|------------|
| Backend framework | Flask |
| Live movie data | OMDb API |
| AI integration | Google Gemini via `google-generativeai` |
| Local database | MySQL via `mysql-connector-python` |
| Data handling | pandas |
| Frontend | Jinja2 templates, CSS, JavaScript |

## Project Structure

```text
movie-recommendation/
├── ai_service.py         # Gemini integration and JSON prompting helpers
├── app.py                # Flask app, web routes, API routes, health checks
├── database.py           # MySQL access, sample movie bootstrap, fallback data
├── env_utils.py          # Local .env loading helpers
├── recommender.py        # Recommendation engine, OMDb calls, ranking logic, caching
├── requirements.txt      # Python dependencies
├── templates/
│   ├── base.html         # Base page layout
│   └── index.html        # Main recommendation page
├── static/
│   ├── css/style.css     # UI styles
│   └── js/main.js        # Frontend interactions
└── README.md
```

## System Architecture

```text
Browser UI / API Client
          |
          v
       app.py
          |
          v
   recommender.py
    |      |      |
    |      |      +--> ai_service.py (optional Gemini summary and reasons)
    |      |
    |      +---------> database.py (MySQL data, or embedded sample movies)
    |
    +----------------> OMDb API (live movie metadata)
```

## How the System Works

### 1. App startup

- `app.py` creates the Flask app.
- `env_utils.py` loads environment variables from a local `.env` file if present.
- The home page tries to preload movie titles and top-rated movies.

### 2. User submits a movie

When the user searches from the home page or calls `/recommend`, the app:

1. Reads the movie title and optional preferences.
2. Validates `top_n` and `min_rating`.
3. Passes the request into `recommend_movies_with_preferences()` in `recommender.py`.

### 3. Seed movie lookup

- The recommender first tries to fetch the seed movie from OMDb using the title.
- If OMDb is unavailable, it falls back to MySQL or the embedded sample data.
- If the seed movie is not found anywhere, the request fails with a clear error.

### 4. Candidate generation

The recommender builds a candidate pool from several places:

- Gemini-suggested titles, if Gemini is configured.
- A curated fallback movie list in `recommender.py`.
- OMDb search results collected from common search terms.
- MySQL rows or embedded sample movies from `database.py`.

### 5. Scoring and ranking

Each candidate gets a score based on:

- IMDb rating.
- IMDb vote count.
- Shared genres with the seed movie.
- Matching preferred genres.
- Matching preferred directors.
- Matching preferred cast.
- Same director as the seed movie.
- Overlapping cast with the seed movie.

If `min_rating` is provided, movies below that threshold are removed before ranking.

### 6. Explanation generation

- If Gemini is configured, the app can ask Gemini for a short summary plus one-sentence reasons for each recommendation.
- If Gemini is not configured or fails, the app falls back to rule-based explanations generated from metadata matches.

### 7. Response output

- The web UI renders posters, metadata, explanations, and links.
- The API returns JSON with the seed movie, detected sources, AI status, and recommendations.

## Data Sources and Fallback Behavior

### OMDb

- Required for the live catalog experience.
- Used for seed movie lookup, search suggestions, posters, ratings, cast, and plot.
- Controlled by `OMDB_API_KEY`.

### MySQL

- Optional.
- Used to pull records from the `movies` table when available.
- Also supports seeding sample movies into MySQL.
- If MySQL is unavailable, the app still runs by using the embedded `SAMPLE_MOVIES` list.

### Gemini

- Optional.
- Used to suggest additional candidate titles.
- Used to generate short natural-language summaries and reasons.
- Controlled by `GEMINI_API_KEY` and optionally `GEMINI_MODEL`.

## Required and Optional Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OMDB_API_KEY` | Yes for live OMDb features | Authenticates OMDb API requests |
| `GEMINI_API_KEY` | No | Enables Gemini suggestions and explanations |
| `GEMINI_MODEL` | No | Overrides the default Gemini model |
| `FLASK_SECRET_KEY` | No | Flask session secret; defaults to a development value |

## MySQL Configuration

Database settings are defined in `database.py` in the `DB_CONFIG` dictionary:

```python
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "movies_db",
}
```

Expected table columns in the `movies` table:

- `id`
- `title`
- `genre`
- `overview`
- `director`
- `cast`
- `rating`

Example MySQL table definition:

```sql
CREATE DATABASE IF NOT EXISTS movies_db;

USE movies_db;

CREATE TABLE IF NOT EXISTS movies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    genre VARCHAR(255),
    overview TEXT,
    director VARCHAR(255),
    `cast` TEXT,
    rating DECIMAL(3,1)
);
```

## How to Run on Windows

### Prerequisites

Install these first:

1. Python 3.10 or newer.
2. MySQL Server, only if you want local database support.
3. An OMDb API key.
4. A Gemini API key, only if you want AI explanations.

### Step 1: Open PowerShell in the project folder

```powershell
cd "c:\Users\HP\OneDrive - MSFT\Documents\Repo\Tanu\movie-recommendation"
```

### Step 2: Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, run this once in the current shell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate again:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install dependencies

```powershell
pip install -r requirements.txt
```

### Step 4: Configure environment variables

You can either set them in PowerShell for the current terminal or create a local `.env` file in the project root.

#### Option A: Set variables in PowerShell

```powershell
$env:OMDB_API_KEY="your_omdb_api_key"
$env:GEMINI_API_KEY="your_gemini_api_key"
$env:GEMINI_MODEL="gemini-1.5-flash"
$env:FLASK_SECRET_KEY="change-this-in-real-use"
```

If you do not want Gemini, skip `GEMINI_API_KEY`.

#### Option B: Create a `.env` file

```env
OMDB_API_KEY=your_omdb_api_key
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-1.5-flash
FLASK_SECRET_KEY=change-this-in-real-use
```

The app automatically loads `.env` values through `env_utils.py`.

### Step 5: Configure MySQL if you want database support

1. Start your MySQL server.
2. Create the `movies_db` database and `movies` table.
3. Update `DB_CONFIG` in `database.py` if your username, password, port, or host is different.
4. Optionally call the seed endpoint to insert sample movies into MySQL.

### Step 6: Run the Flask app

```powershell
python app.py
```

### Step 7: Open the app in the browser

- Website: `http://127.0.0.1:5000/`
- API index: `http://127.0.0.1:5000/api`
- Health check: `http://127.0.0.1:5000/health`

## How to Use the System

### From the web interface

1. Open the home page.
2. Enter a movie title you already like.
3. Optionally set top picks, minimum rating, genres, directors, and cast preferences.
4. Click `Get Recommendations`.
5. Review the ranked recommendation list.

### From the API

Example request:

```text
GET /recommend?movie=Inception&top_n=5&preferred_genres=Sci-Fi,Thriller&preferred_directors=Christopher%20Nolan&min_rating=8
```

Example with PowerShell:

```powershell
Invoke-RestMethod "http://127.0.0.1:5000/recommend?movie=Inception&top_n=5&preferred_genres=Sci-Fi,Thriller&min_rating=8"
```

## API Endpoints

### `GET /`

Renders the web UI.

### `GET /api`

Returns API overview, configured data sources, and endpoint references.

### `GET /preferences/questions`
### `GET /api/preferences/questions`

Returns the optional preference fields supported by the recommender.

### `GET /recommend`
### `GET /api/recommend`

Returns recommendation results.

Query parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `movie` | string | Yes | Seed movie title |
| `top_n` | integer | No | Number of recommendations |
| `preferred_genres` | string | No | Comma-separated genres |
| `preferred_directors` | string | No | Comma-separated directors |
| `preferred_cast` | string | No | Comma-separated actor names |
| `min_rating` | float | No | Minimum rating from 0 to 10 |

Example response shape:

```json
{
  "input_movie": "Inception",
  "preferences_used": {
    "preferred_genres": ["Sci-Fi", "Thriller"],
    "preferred_directors": [],
    "preferred_cast": [],
    "min_rating": 8.0
  },
  "source": "gemini+mysql+omdb",
  "data_sources": ["gemini", "mysql", "omdb"],
  "seed_movie": {
    "title": "Inception",
    "year": "2010"
  },
  "ai_summary": "These recommendations stay close to cerebral science fiction and strong tension.",
  "ai_enabled": true,
  "ai_model": "gemini-1.5-flash",
  "recommendations": [
    {
      "title": "Interstellar",
      "rating": 8.7,
      "genres": ["Adventure", "Drama", "Sci-Fi"],
      "ai_reason": "It carries similar large-scale sci-fi ideas with emotional weight."
    }
  ]
}
```

### `GET /recommend/genre`
### `GET /api/recommend/genre`

Returns the top-ranked movies for a genre.

Example:

```text
GET /recommend/genre?genre=Action&top_n=5
```

### `GET /recommend/top-rated`
### `GET /api/recommend/top-rated`

Returns top-rated movies from the current catalog.

Example:

```text
GET /recommend/top-rated?limit=10
```

### `GET /movies`
### `GET /api/movies`

Returns cached movie titles used for autocomplete.

### `POST /cache/reload`
### `POST /api/cache/reload`

Clears the in-memory title cache and movie metadata cache.

PowerShell example:

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:5000/cache/reload"
```

### `POST /seed/movies`
### `POST /api/seed/movies`

Attempts to insert the embedded sample movies into MySQL.

If MySQL is not available, the endpoint returns a fallback message instead of crashing.

PowerShell example:

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:5000/seed/movies"
```

### `GET /health`

Returns a simple health payload showing whether MySQL, OMDb, and Gemini are available.

## Windows Notes

- Use PowerShell or Command Prompt, but the commands in this README are written for PowerShell.
- If activation fails because scripts are disabled, use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.
- If port 5000 is already in use, stop the conflicting process or change the port in `app.py`.
- For production on Windows, do not use Flask debug mode as-is.

## Troubleshooting

### `OMDB_API_KEY is not set`

Cause:
The OMDb API key is missing from both the environment and `.env` file.

Fix:
Set `OMDB_API_KEY` and restart the app.

### MySQL connection error

Cause:
MySQL is not running, credentials are wrong, or the database/table does not exist.

Fix:

1. Start MySQL.
2. Verify `DB_CONFIG` in `database.py`.
3. Create the `movies_db` database and `movies` table.

The app can still run without MySQL because it falls back to embedded sample data.

### Gemini is not being used

Cause:
`GEMINI_API_KEY` is not set, the Gemini package is not installed, or the API request failed.

Fix:

1. Confirm `google-generativeai` is installed.
2. Set `GEMINI_API_KEY`.
3. Restart the app.

The recommender still works without Gemini.

### PowerShell blocks virtual environment activation

Fix:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Current Limitations

- OMDb does not provide a true similarity endpoint, so recommendations are based on metadata matching, curated fallback titles, cached search results, and optional Gemini suggestions.
- The in-memory cache is reset when the app restarts.
- `app.py` runs Flask in debug mode by default for local development.
- MySQL configuration is hardcoded in `database.py` instead of environment variables.

## Suggested Next Improvements

1. Move MySQL configuration into environment variables.
2. Add automated tests for ranking, API responses, and fallback behavior.
3. Run the app with Waitress or another production WSGI server for Windows deployment.
4. Add pagination or larger catalog discovery beyond the current OMDb search strategy.
