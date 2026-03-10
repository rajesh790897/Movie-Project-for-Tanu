"""
database.py
-----------
Handles MySQL database connection and fetching movie records
into a pandas DataFrame.
"""

import mysql.connector
import pandas as pd
from mysql.connector import Error


# ---------------------------------------------------------------------------
# Configuration – update these values to match your MySQL setup
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "movies_db",
}


# 30 additional movies used for quick bootstrap in local environments.
SAMPLE_MOVIES = [
    ("The Shawshank Redemption", "Drama", "Two imprisoned men bond over a number of years.", "Frank Darabont", "Tim Robbins, Morgan Freeman", 9.3),
    ("Fight Club", "Drama Thriller", "An insomniac and a soap salesman form an underground club.", "David Fincher", "Brad Pitt, Edward Norton", 8.8),
    ("Forrest Gump", "Drama Romance", "The presidencies of Kennedy and Johnson through the eyes of Forrest.", "Robert Zemeckis", "Tom Hanks, Robin Wright", 8.8),
    ("The Lord of the Rings: The Fellowship of the Ring", "Fantasy Adventure", "A meek Hobbit begins a journey to destroy the One Ring.", "Peter Jackson", "Elijah Wood, Ian McKellen", 8.8),
    ("The Lord of the Rings: The Two Towers", "Fantasy Adventure", "The fellowship is broken but the quest continues.", "Peter Jackson", "Elijah Wood, Viggo Mortensen", 8.8),
    ("The Lord of the Rings: The Return of the King", "Fantasy Adventure", "Final confrontation for Middle-earth.", "Peter Jackson", "Elijah Wood, Ian McKellen", 9.0),
    ("The Silence of the Lambs", "Crime Thriller", "A young FBI trainee seeks help from a cannibal psychiatrist.", "Jonathan Demme", "Jodie Foster, Anthony Hopkins", 8.6),
    ("Se7en", "Crime Thriller", "Two detectives hunt a serial killer using seven deadly sins.", "David Fincher", "Brad Pitt, Morgan Freeman", 8.6),
    ("Gladiator", "Action Drama", "A Roman general seeks revenge against a corrupt emperor.", "Ridley Scott", "Russell Crowe, Joaquin Phoenix", 8.5),
    ("The Prestige", "Mystery Drama", "Two magicians engage in a bitter rivalry.", "Christopher Nolan", "Hugh Jackman, Christian Bale", 8.5),
    ("Memento", "Mystery Thriller", "A man with short-term memory loss hunts his wife's killer.", "Christopher Nolan", "Guy Pearce, Carrie-Anne Moss", 8.4),
    ("Whiplash", "Drama Music", "A promising drummer faces a ruthless instructor.", "Damien Chazelle", "Miles Teller, J.K. Simmons", 8.5),
    ("La La Land", "Romance Musical", "An aspiring actress and jazz musician fall in love in LA.", "Damien Chazelle", "Ryan Gosling, Emma Stone", 8.0),
    ("Mad Max: Fury Road", "Action Adventure", "In a post-apocalyptic wasteland, Max helps Furiosa flee.", "George Miller", "Tom Hardy, Charlize Theron", 8.1),
    ("Blade Runner 2049", "Sci-Fi Drama", "A young blade runner discovers a long-buried secret.", "Denis Villeneuve", "Ryan Gosling, Harrison Ford", 8.0),
    ("Dune", "Sci-Fi Adventure", "Paul Atreides leads nomadic tribes in a battle for Arrakis.", "Denis Villeneuve", "Timothee Chalamet, Zendaya", 8.0),
    ("Arrival", "Sci-Fi Drama", "A linguist communicates with mysterious alien visitors.", "Denis Villeneuve", "Amy Adams, Jeremy Renner", 7.9),
    ("Prisoners", "Crime Drama", "A father takes matters into his own hands after kidnapping.", "Denis Villeneuve", "Hugh Jackman, Jake Gyllenhaal", 8.1),
    ("The Wolf of Wall Street", "Comedy Drama", "A stockbroker rises and falls amid corruption.", "Martin Scorsese", "Leonardo DiCaprio, Jonah Hill", 8.2),
    ("Shutter Island", "Mystery Thriller", "A U.S. Marshal investigates a psychiatric facility.", "Martin Scorsese", "Leonardo DiCaprio, Mark Ruffalo", 8.2),
    ("The Departed", "Crime Thriller", "An undercover cop and a mole hunt each other.", "Martin Scorsese", "Leonardo DiCaprio, Matt Damon", 8.5),
    ("Django Unchained", "Western Drama", "A freed slave sets out to rescue his wife.", "Quentin Tarantino", "Jamie Foxx, Christoph Waltz", 8.5),
    ("Inglourious Basterds", "War Drama", "A group plots to assassinate Nazi leaders.", "Quentin Tarantino", "Brad Pitt, Christoph Waltz", 8.4),
    ("Once Upon a Time in Hollywood", "Comedy Drama", "A fading actor and stunt double navigate 1969 LA.", "Quentin Tarantino", "Leonardo DiCaprio, Brad Pitt", 7.6),
    ("Titanic", "Romance Drama", "A love story aboard the ill-fated RMS Titanic.", "James Cameron", "Leonardo DiCaprio, Kate Winslet", 7.9),
    ("Avatar", "Sci-Fi Adventure", "A marine on Pandora chooses between duty and conscience.", "James Cameron", "Sam Worthington, Zoe Saldana", 7.8),
    ("The Social Network", "Drama Biography", "The founding and lawsuits of Facebook.", "David Fincher", "Jesse Eisenberg, Andrew Garfield", 7.8),
    ("The Grand Budapest Hotel", "Comedy Drama", "Adventures of a concierge and his protege.", "Wes Anderson", "Ralph Fiennes, Tony Revolori", 8.1),
    ("Her", "Romance Sci-Fi", "A lonely writer develops a relationship with an AI assistant.", "Spike Jonze", "Joaquin Phoenix, Scarlett Johansson", 8.0),
    ("Edge of Tomorrow", "Sci-Fi Action", "A soldier relives the same day in a war against aliens.", "Doug Liman", "Tom Cruise, Emily Blunt", 7.9),
]


def get_connection():
    """
    Create and return a MySQL connection using the DB_CONFIG settings.
    Raises a RuntimeError if the connection cannot be established.
    """
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            return connection
    except Error as e:
        raise RuntimeError(f"Failed to connect to MySQL: {e}") from e


def fetch_movies() -> pd.DataFrame:
    """
    Fetch all rows from the `movies` table and return them as a
    pandas DataFrame.

    Expected columns: id, title, genre, overview, director, cast, rating

    Returns
    -------
    pd.DataFrame
        DataFrame with one row per movie. Empty DataFrame if the table
        has no rows.
    """
    query = """
        SELECT
            id,
            title,
            genre,
            overview,
            director,
            `cast`,
            rating
        FROM movies
    """
    connection = None
    try:
        connection = get_connection()
        # Using pandas read_sql for efficient large-dataset loading
        df = pd.read_sql(query, con=connection)
        return df
    except Error as e:
        raise RuntimeError(f"Error fetching movies from database: {e}") from e
    finally:
        if connection and connection.is_connected():
            connection.close()


def fetch_movies_by_genre(genre: str) -> pd.DataFrame:
    """
    Fetch movies that match a specific genre (case-insensitive partial match).

    Parameters
    ----------
    genre : str
        Genre string to filter on (e.g. 'Action').

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame.
    """
    query = """
        SELECT
            id,
            title,
            genre,
            overview,
            director,
            `cast`,
            rating
        FROM movies
        WHERE LOWER(genre) LIKE LOWER(%s)
    """
    connection = None
    try:
        connection = get_connection()
        df = pd.read_sql(query, con=connection, params=(f"%{genre}%",))
        return df
    except Error as e:
        raise RuntimeError(f"Error fetching movies by genre: {e}") from e
    finally:
        if connection and connection.is_connected():
            connection.close()


def fetch_top_rated_movies(limit: int = 10) -> pd.DataFrame:
    """
    Fetch the top-rated movies from the database.

    Parameters
    ----------
    limit : int
        Number of top-rated movies to return (default 10).

    Returns
    -------
    pd.DataFrame
        DataFrame sorted by rating descending.
    """
    query = """
        SELECT
            id,
            title,
            genre,
            overview,
            director,
            `cast`,
            rating
        FROM movies
        ORDER BY rating DESC
        LIMIT %s
    """
    connection = None
    try:
        connection = get_connection()
        df = pd.read_sql(query, con=connection, params=(limit,))
        return df
    except Error as e:
        raise RuntimeError(f"Error fetching top-rated movies: {e}") from e
    finally:
        if connection and connection.is_connected():
            connection.close()


def seed_movies() -> int:
    """
    Insert 30 sample movies if they are not already present.

    Returns
    -------
    int
        Number of rows inserted.
    """
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT title FROM movies")
        existing_titles = {row[0].strip().lower() for row in cursor.fetchall()}

        to_insert = [
            movie for movie in SAMPLE_MOVIES
            if movie[0].strip().lower() not in existing_titles
        ]

        if not to_insert:
            return 0

        insert_query = """
            INSERT INTO movies (title, genre, overview, director, `cast`, rating)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(insert_query, to_insert)
        connection.commit()
        return cursor.rowcount
    except Error as e:
        raise RuntimeError(f"Error seeding movies: {e}") from e
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
