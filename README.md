# Movie Recommendation System

A content-based movie recommendation engine backed by a **MySQL** database, exposed via a **Flask** REST API.

---

## Tech Stack

| Layer        | Technology                              |
|--------------|-----------------------------------------|
| Database     | MySQL 8+                                |
| Driver       | mysql-connector-python                  |
| Data         | pandas                                  |
| ML / NLP     | scikit-learn (TF-IDF + cosine similarity) |
| API          | Flask                                   |

---

## Project Structure

```
movie-recommendation/
│
├── app.py            # Flask REST API & route definitions
├── recommender.py    # ML pipeline: vectorisation, similarity, recommendations
├── database.py       # MySQL connection & query helpers
├── requirements.txt  # Python dependencies
└── README.md
```

---

## Database Setup

### 1. Create the database and table

```sql
CREATE DATABASE IF NOT EXISTS movies_db;

USE movies_db;

CREATE TABLE IF NOT EXISTS movies (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    title    VARCHAR(255)  NOT NULL,
    genre    VARCHAR(100),
    overview TEXT,
    director VARCHAR(255),
    cast     VARCHAR(500),
    rating   FLOAT
);
```

### 2. Insert sample data

```sql
INSERT INTO movies (title, genre, overview, director, cast, rating) VALUES
('Inception',       'Sci-Fi Thriller', 'A thief who steals corporate secrets through dream-sharing technology.',          'Christopher Nolan',  'Leonardo DiCaprio, Joseph Gordon-Levitt', 8.8),
('Interstellar',    'Sci-Fi Drama',    'A team of explorers travel through a wormhole in space.',                         'Christopher Nolan',  'Matthew McConaughey, Anne Hathaway',      8.6),
('The Dark Knight', 'Action Thriller', 'Batman faces the Joker, a criminal mastermind who wreaks chaos on Gotham City.', 'Christopher Nolan',  'Christian Bale, Heath Ledger',            9.0),
('The Matrix',      'Sci-Fi Action',   'A hacker discovers reality is a simulation controlled by machines.',              'The Wachowskis',      'Keanu Reeves, Laurence Fishburne',        8.7),
('Avengers: Endgame','Action Superhero','The Avengers assemble to reverse Thanos\'s actions.',                           'Russo Brothers',      'Robert Downey Jr., Chris Evans',         8.4),
('Parasite',        'Drama Thriller',  'A poor family schemes to become employed by a wealthy family.',                  'Bong Joon-ho',        'Song Kang-ho, Lee Sun-kyun',              8.5),
('Pulp Fiction',    'Crime Drama',     'Several stories of criminal Los Angeles interweave.',                             'Quentin Tarantino',   'John Travolta, Uma Thurman',              8.9),
('The Godfather',   'Crime Drama',     'The powerful Corleone family navigates organized crime in America.',              'Francis Ford Coppola','Marlon Brando, Al Pacino',                9.2);
```

### 3. Configure credentials

Open `database.py` and update the `DB_CONFIG` dictionary:

```python
DB_CONFIG = {
    "host":     "localhost",
    "port":     3306,
    "user":     "root",       # ← your MySQL username
    "password": "password",   # ← your MySQL password
    "database": "movies_db",
}
```

---

## Installation

```bash
# 1. Clone / navigate to the project directory
cd movie-recommendation

# 2. Create and activate a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Running the API

```bash
python app.py
```

The server starts on `http://localhost:5000`.

---

## API Reference

### `GET /recommend`

Returns content-based recommendations for a given movie.

| Parameter | Type   | Required | Default | Description                       |
|-----------|--------|----------|---------|-----------------------------------|
| `movie`   | string | Yes      | –       | Title of the seed movie           |
| `top_n`   | int    | No       | 5       | Number of recommendations         |

**Example request**

```
GET /recommend?movie=Inception&top_n=5
```

**Example response**

```json
{
  "input_movie": "Inception",
  "recommendations": [
    "Interstellar",
    "The Dark Knight",
    "The Matrix",
    "Parasite",
    "Pulp Fiction"
  ]
}
```

---

### `GET /recommend/genre`

Returns top-rated movies filtered by genre.

| Parameter | Type   | Required | Default | Description                |
|-----------|--------|----------|---------|----------------------------|
| `genre`   | string | Yes      | –       | Genre keyword (partial OK) |
| `top_n`   | int    | No       | 5       | Number of results          |

**Example request**

```
GET /recommend/genre?genre=Action&top_n=3
```

**Example response**

```json
{
  "genre": "Action",
  "recommendations": [
    { "title": "The Dark Knight", "rating": 9.0 },
    { "title": "The Matrix",      "rating": 8.7 },
    { "title": "Avengers: Endgame","rating": 8.4 }
  ]
}
```

---

### `GET /recommend/top-rated`

Returns the globally top-rated movies.

| Parameter | Type | Required | Default | Description           |
|-----------|------|----------|---------|-----------------------|
| `limit`   | int  | No       | 10      | Number of movies      |

**Example request**

```
GET /recommend/top-rated?limit=5
```

**Example response**

```json
{
  "top_rated_movies": [
    { "title": "The Godfather",   "rating": 9.2 },
    { "title": "The Dark Knight", "rating": 9.0 },
    { "title": "Pulp Fiction",    "rating": 8.9 },
    { "title": "Inception",       "rating": 8.8 },
    { "title": "The Matrix",      "rating": 8.7 }
  ]
}
```

---

### `GET /movies`

Returns an alphabetically sorted list of all movie titles.

```
GET /movies
```

---

### `POST /cache/reload`

Rebuilds the TF-IDF similarity matrix from the current database state without restarting the server. Call this after inserting new movies.

```
POST /cache/reload
```

---

### `GET /health`

Simple liveness check.

```json
{ "status": "ok" }
```

---

## How It Works

```
MySQL DB
   │
   ▼
database.py  ──► fetch_movies()   → raw DataFrame
   │
   ▼
recommender.py
   ├── _build_content_column()   → combines genre + overview + director + cast
   ├── TfidfVectorizer           → converts text to numeric vectors
   ├── cosine_similarity()       → (N × N) similarity matrix  [cached]
   └── recommend_movies()        → looks up seed movie, ranks neighbours
   │
   ▼
app.py (Flask)
   └── /recommend  /recommend/genre  /recommend/top-rated  /movies
```

### Why TF-IDF + Cosine Similarity?

- **TF-IDF** weights terms by how distinctive they are across the corpus,
  so common words ("the", "a") are suppressed while genre-specific or
  director-specific terms get boosted.
- **Cosine similarity** measures the angle between two document vectors,
  making it length-independent and well-suited to sparse text features.

### Caching

The similarity matrix is computed once and kept in memory (`_cosine_sim`).
For a database with thousands of movies this is far faster than
recomputing on every request. Use `POST /cache/reload` to refresh it
after a batch import.

---

## Error Responses

All errors return JSON in the format:

```json
{ "error": "Human-readable message" }
```

| HTTP Status | Meaning                                    |
|-------------|--------------------------------------------|
| 400         | Bad or missing query parameter             |
| 404         | Movie / genre not found in the database    |
| 500         | Database or internal server error          |

---

## Production Notes

- Replace `app.run(debug=True)` with a WSGI server such as **Gunicorn** (Linux/macOS) or **Waitress** (Windows).
- Store DB credentials in environment variables, not hard-coded in `database.py`.
- For datasets with 100 k+ movies, replace `cosine_similarity` with `linear_kernel` to reduce memory usage.
