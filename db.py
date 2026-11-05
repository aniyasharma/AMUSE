import json
import sqlite3
from datetime import datetime
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(__file__).resolve().parents[1] / "amuse_data.db"


def connect():

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():

    with connect() as connection:

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS preferences (
                user_id INTEGER PRIMARY KEY,
                genres TEXT NOT NULL DEFAULT '[]',
                artists TEXT NOT NULL DEFAULT '[]',
                songs TEXT NOT NULL DEFAULT '[]',
                use_spotify INTEGER NOT NULL DEFAULT 0,
                last_pss TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                stress_level TEXT,
                pss_total INTEGER,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                track_name TEXT,
                artists TEXT,
                pre_stress TEXT,
                post_stress TEXT,
                helpfulness INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS spotify_accounts (
                user_id INTEGER PRIMARY KEY,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                spotify_user TEXT,
                spotify_name TEXT,
                scope TEXT,
                expires_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS health_checkins (
                user_id INTEGER PRIMARY KEY,
                sleep_hours REAL,
                sleep_date TEXT,
                hrv REAL,
                hrv_at TEXT,
                heart_rate REAL,
                pss_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )


def create_user(name, email, password):

    email = email.strip().lower()

    with connect() as connection:

        connection.execute(
            """
            INSERT INTO users (name, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                name.strip(),
                email,
                generate_password_hash(password),
                datetime.utcnow().isoformat(),
            ),
        )

        row = connection.execute(
            "SELECT id, name, email FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    return dict(row)


def find_user_by_email(email):

    with connect() as connection:

        row = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()

    return dict(row) if row else None


def authenticate(email, password):

    user = find_user_by_email(email)

    if not user:

        return None

    if not check_password_hash(user["password_hash"], password):

        return None

    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
    }


def reset_password(email, name, new_password):

    user = find_user_by_email(email)

    if not user:

        return None

    if user["name"].strip().lower() != (name or "").strip().lower():

        return None

    with connect() as connection:

        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), user["id"]),
        )

    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
    }


def save_preferences(user_id, genres, artists, songs, use_spotify=False, last_pss=None):

    payload = {
        "genres": list(genres or []),
        "artists": list(artists or []),
        "songs": list(songs or []),
        "use_spotify": 1 if use_spotify else 0,
        "last_pss": json.dumps(last_pss) if last_pss is not None else None,
        "updated_at": datetime.utcnow().isoformat(),
    }

    with connect() as connection:

        existing = connection.execute(
            "SELECT user_id FROM preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if existing:

            if last_pss is None:

                connection.execute(
                    """
                    UPDATE preferences
                    SET genres = ?, artists = ?, songs = ?,
                        use_spotify = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (
                        json.dumps(payload["genres"]),
                        json.dumps(payload["artists"]),
                        json.dumps(payload["songs"]),
                        payload["use_spotify"],
                        payload["updated_at"],
                        user_id,
                    ),
                )

            else:

                connection.execute(
                    """
                    UPDATE preferences
                    SET genres = ?, artists = ?, songs = ?,
                        use_spotify = ?, last_pss = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (
                        json.dumps(payload["genres"]),
                        json.dumps(payload["artists"]),
                        json.dumps(payload["songs"]),
                        payload["use_spotify"],
                        payload["last_pss"],
                        payload["updated_at"],
                        user_id,
                    ),
                )

        else:

            connection.execute(
                """
                INSERT INTO preferences
                (user_id, genres, artists, songs, use_spotify, last_pss, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    json.dumps(payload["genres"]),
                    json.dumps(payload["artists"]),
                    json.dumps(payload["songs"]),
                    payload["use_spotify"],
                    payload["last_pss"],
                    payload["updated_at"],
                ),
            )


def load_preferences(user_id):

    with connect() as connection:

        row = connection.execute(
            "SELECT * FROM preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if not row:

        return None

    data = dict(row)

    return {
        "genres": json.loads(data["genres"] or "[]"),
        "artists": json.loads(data["artists"] or "[]"),
        "songs": json.loads(data["songs"] or "[]"),
        "use_spotify": bool(data["use_spotify"]),
        "last_pss": json.loads(data["last_pss"]) if data["last_pss"] else None,
        "updated_at": data["updated_at"],
    }


def load_health(user_id):

    with connect() as connection:

        row = connection.execute(
            "SELECT * FROM health_checkins WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if not row:

        return {
            "sleep_hours": None,
            "sleep_date": None,
            "hrv": None,
            "hrv_at": None,
            "heart_rate": None,
            "pss_at": None,
        }

    data = dict(row)

    return {
        "sleep_hours": data["sleep_hours"],
        "sleep_date": data["sleep_date"],
        "hrv": data["hrv"],
        "hrv_at": data["hrv_at"],
        "heart_rate": data["heart_rate"],
        "pss_at": data["pss_at"],
    }


def save_health(
    user_id,
    sleep_hours=None,
    sleep_date=None,
    hrv=None,
    hrv_at=None,
    heart_rate=None,
    pss_at=None,
):

    current = load_health(user_id)
    next_sleep = current["sleep_hours"] if sleep_hours is None else sleep_hours
    next_sleep_date = current["sleep_date"] if sleep_date is None else sleep_date
    next_hrv = current["hrv"] if hrv is None else hrv
    next_hrv_at = current["hrv_at"] if hrv_at is None else hrv_at
    next_hr = current["heart_rate"] if heart_rate is None else heart_rate
    next_pss_at = current["pss_at"] if pss_at is None else pss_at
    now = datetime.utcnow().isoformat()

    with connect() as connection:

        connection.execute(
            """
            INSERT INTO health_checkins
            (user_id, sleep_hours, sleep_date, hrv, hrv_at,
             heart_rate, pss_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                sleep_hours = excluded.sleep_hours,
                sleep_date = excluded.sleep_date,
                hrv = excluded.hrv,
                hrv_at = excluded.hrv_at,
                heart_rate = excluded.heart_rate,
                pss_at = excluded.pss_at,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                next_sleep,
                next_sleep_date,
                next_hrv,
                next_hrv_at,
                next_hr,
                next_pss_at,
                now,
            ),
        )

    return load_health(user_id)


def save_recommendation(user_id, stress_level, pss_total, payload):

    with connect() as connection:

        connection.execute(
            """
            INSERT INTO recommendations
            (user_id, stress_level, pss_total, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                stress_level,
                pss_total,
                json.dumps(payload),
                datetime.utcnow().isoformat(),
            ),
        )


def save_feedback(
    user_id,
    track_name,
    artists,
    pre_stress,
    post_stress,
    helpfulness,
):

    with connect() as connection:

        connection.execute(
            """
            INSERT INTO feedback
            (user_id, track_name, artists, pre_stress, post_stress,
             helpfulness, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                track_name,
                artists,
                pre_stress,
                post_stress,
                helpfulness,
                datetime.utcnow().isoformat(),
            ),
        )


def save_spotify_account(
    user_id,
    access_token,
    refresh_token=None,
    spotify_user=None,
    spotify_name=None,
    scope=None,
    expires_at=None,
):

    with connect() as connection:

        existing = connection.execute(
            "SELECT refresh_token FROM spotify_accounts WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if not refresh_token and existing:

            refresh_token = existing["refresh_token"]

        connection.execute(
            """
            INSERT INTO spotify_accounts
            (user_id, access_token, refresh_token, spotify_user,
             spotify_name, scope, expires_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = COALESCE(excluded.refresh_token, spotify_accounts.refresh_token),
                spotify_user = COALESCE(excluded.spotify_user, spotify_accounts.spotify_user),
                spotify_name = COALESCE(excluded.spotify_name, spotify_accounts.spotify_name),
                scope = COALESCE(excluded.scope, spotify_accounts.scope),
                expires_at = excluded.expires_at,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                access_token,
                refresh_token,
                spotify_user,
                spotify_name,
                scope,
                expires_at,
                datetime.utcnow().isoformat(),
            ),
        )


def load_spotify_account(user_id):

    with connect() as connection:

        row = connection.execute(
            "SELECT * FROM spotify_accounts WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    return dict(row) if row else None


def clear_spotify_account(user_id):

    with connect() as connection:

        connection.execute(
            "DELETE FROM spotify_accounts WHERE user_id = ?",
            (user_id,),
        )
