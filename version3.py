import base64
import json
import os
import urllib.parse
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st


from sklearn.model_selection import train_test_split
from sklearn.multioutput import MultiOutputRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import MinMaxScaler
from sklearn.preprocessing import LabelEncoder


health = pd.read_csv("therapy.csv")
spotify = pd.read_csv("spotify.csv")

print(health.head())
print(spotify.head())

print("Health columns:")
print(health.columns.tolist())

print("Spotify columns:")
print(spotify.columns.tolist())

# ---- Health dataset columns ----
PRE_STRESS_COLUMN = "Pre_session_label"
POST_STRESS_COLUMN = "Post_session_label"
HEALTH_VALENCE_COLUMN = "Valence_spectral"
HEALTH_AROUSAL_COLUMN = "Arousal_spectral"

# ---- Spotify dataset columns ----
TRACK_NAME_COLUMN = "track_name"
ARTISTS_COLUMN = "artists"
SPOTIFY_VALENCE_COLUMN = "valence"
ENERGY_COLUMN = "energy"

if "track_genre" in spotify.columns:
    GENRE_COLUMN = "track_genre"
else:
    GENRE_COLUMN = None


# ---- Build health_model ----
health_model = health[
    [PRE_STRESS_COLUMN, POST_STRESS_COLUMN, HEALTH_VALENCE_COLUMN, HEALTH_AROUSAL_COLUMN]
].copy()

print(health_model.head())

# ---- Build spotify_model ----
spotify_model = spotify[
    [TRACK_NAME_COLUMN, ARTISTS_COLUMN, SPOTIFY_VALENCE_COLUMN, ENERGY_COLUMN]
].copy()

print(spotify_model.head())

# These ARE numeric — safe to coerce
health_model[HEALTH_VALENCE_COLUMN] = pd.to_numeric(
    health_model[HEALTH_VALENCE_COLUMN], errors="coerce"
)
health_model[HEALTH_AROUSAL_COLUMN] = pd.to_numeric(
    health_model[HEALTH_AROUSAL_COLUMN], errors="coerce"
)

# Pre_session_label IS ordinal stress -> preserve low->high order
stress_order = {"low_stress": 0, "moderate_stress": 1, "high_stress": 2}
health_model[PRE_STRESS_COLUMN] = health_model[PRE_STRESS_COLUMN].map(stress_order)

# Post_session_label is just an outcome category -> LabelEncoder is fine
le = LabelEncoder()
health_model[POST_STRESS_COLUMN] = le.fit_transform(health_model[POST_STRESS_COLUMN].astype(str))

print(health_model.head())
print(health_model.isna().sum())  # should now show 0 across the board

stress_scaler = MinMaxScaler()
valence_scaler = MinMaxScaler()
arousal_scaler = MinMaxScaler()

health_model[[PRE_STRESS_COLUMN]] = stress_scaler.fit_transform(health_model[[PRE_STRESS_COLUMN]])
health_model[[HEALTH_VALENCE_COLUMN]] = valence_scaler.fit_transform(health_model[[HEALTH_VALENCE_COLUMN]])
health_model[[HEALTH_AROUSAL_COLUMN]] = arousal_scaler.fit_transform(health_model[[HEALTH_AROUSAL_COLUMN]])

print(health_model.head())


X = health_model[[PRE_STRESS_COLUMN]]

y = health_model[
    [
        HEALTH_VALENCE_COLUMN,
        HEALTH_AROUSAL_COLUMN
    ]
]

print(X.head())
print(y.head())


X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=42
)

print("Training:", X_train.shape)
print("Testing:", X_test.shape)

base_model = RandomForestRegressor(
    n_estimators=200,
    random_state=42
)

model = MultiOutputRegressor(
    base_model
)

model.fit(
    X_train,
    y_train
)

print("Model trained")

predictions = model.predict(X_test)
predicted_valence = predictions[:, 0]
predicted_arousal = predictions[:, 1]
print(predictions[:10])

actual_valence = y_test[HEALTH_VALENCE_COLUMN]
actual_arousal = y_test[HEALTH_AROUSAL_COLUMN]

valence_error = mean_absolute_error(
    actual_valence,
    predicted_valence
)

arousal_error = mean_absolute_error(
    actual_arousal,
    predicted_arousal
)

print("Valence MAE:", valence_error)
print("Arousal MAE:", arousal_error)




# ---- Build spotify_model ----
spotify_model = spotify.copy()

spotify_model[SPOTIFY_VALENCE_COLUMN] = pd.to_numeric(
    spotify_model[SPOTIFY_VALENCE_COLUMN],
    errors="coerce"
)

spotify_model[ENERGY_COLUMN] = pd.to_numeric(
    spotify_model[ENERGY_COLUMN],
    errors="coerce"
)

spotify_model = spotify_model.dropna(
    subset=[
        SPOTIFY_VALENCE_COLUMN,
        ENERGY_COLUMN
    ]
)

print(
    spotify_model[
        [
            TRACK_NAME_COLUMN,
            ARTISTS_COLUMN,
            SPOTIFY_VALENCE_COLUMN,
            ENERGY_COLUMN
        ]
    ].head()
)

spotify_model = spotify_model[
    spotify_model[SPOTIFY_VALENCE_COLUMN].between(0, 1)
    &
    spotify_model[ENERGY_COLUMN].between(0, 1)
]

print("Number of songs:", len(spotify_model))

print(
    spotify_model[
        [
            SPOTIFY_VALENCE_COLUMN,
            ENERGY_COLUMN
        ]
    ].describe()
)


def predict_emotional_state(stress_value):

    stress_df = pd.DataFrame(
        {
            PRE_STRESS_COLUMN: [stress_value]
        }
    )

    normalized_stress = stress_scaler.transform(
        stress_df
    )[0][0]

    normalized_stress = np.clip(
        normalized_stress,
        0,
        1
    )

    model_input = pd.DataFrame(
        {
            PRE_STRESS_COLUMN: [
                normalized_stress
            ]
        }
    )

    prediction = model.predict(
        model_input
    )[0]

    current_valence = prediction[0]
    current_arousal = prediction[1]

    return (
        normalized_stress,
        current_valence,
        current_arousal
    )


# ============================================
# CALCULATE TARGET EMOTIONAL STATE
# ============================================

def calculate_target_state(stress_value):
    (
        normalized_stress,
        current_valence,
        current_arousal
    ) = predict_emotional_state(stress_value)

    # Increase valence more when stress is higher
    valence_increase = (
            0.10
            +
            0.20 * normalized_stress
    )

    target_valence = (
            current_valence
            +

            valence_increase
    )

    target_valence = np.clip(
        target_valence,
        0,
        1
    )

    # High stress should land on quiet music, not a small step down.
    if normalized_stress >= 0.67:

        calm_arousal = 0.25
        movement_strength = 1.0

    else:

        calm_arousal = 0.45

        movement_strength = (
                0.30
                +
                0.40 * normalized_stress
        )

    target_arousal = (
            current_arousal
            +
            movement_strength
            *
            (
                calm_arousal
                -
                current_arousal
            )
    )

    target_arousal = np.clip(
        target_arousal,
        0,
        1
    )

    return {
        "normalized_stress": normalized_stress,
        "current_valence": current_valence,
        "current_arousal": current_arousal,
        "target_valence": target_valence,
        "target_arousal": target_arousal
    }


# ============================================
# EMOTIONAL MUSIC MATCHING
# ============================================

def calculate_emotional_matches(
        target_valence,
        target_arousal
):
    songs = spotify_model.copy()

    # High stress targets quiet music. Drop hype, high-energy,
    # and rock tracks before ranking so a favorite artist cannot
    # pull them back to the top.
    if target_arousal <= 0.35:

        songs = songs[
            songs[ENERGY_COLUMN] <= target_arousal + 0.12
        ]

        if GENRE_COLUMN is not None:

            hype_genres = {
                "alt-rock",
                "black-metal",
                "dance",
                "death-metal",
                "edm",
                "grindcore",
                "hard-rock",
                "hardcore",
                "hardstyle",
                "heavy-metal",
                "metal",
                "metalcore",
                "party",
                "punk",
                "punk-rock",
                "rock",
                "rock-n-roll"
            }

            songs = songs[
                ~songs[GENRE_COLUMN]
                .astype(str)
                .str.strip()
                .str.lower()
                .isin(hype_genres)
            ]

    if songs.empty:

        songs = spotify_model.copy()

    # Difference between song valence
    # and target valence
    songs["valence_distance"] = abs(
        songs[SPOTIFY_VALENCE_COLUMN]
        -
        target_valence
    )

    # Spotify energy is being used
    # as the music-side approximation of arousal
    songs["arousal_distance"] = abs(
        songs[ENERGY_COLUMN]
        -
        target_arousal
    )

    VALENCE_WEIGHT = 0.40
    AROUSAL_WEIGHT = 0.60

    songs["emotional_distance"] = np.sqrt(

        VALENCE_WEIGHT
        *
        (
                songs["valence_distance"] ** 2
        )

        +

        AROUSAL_WEIGHT
        *
        (
                songs["arousal_distance"] ** 2
        )
    )

    return songs





# Spotify credentials: environment variables first, then local_secrets.py (gitignored).
DEFAULT_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
DEFAULT_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
if not DEFAULT_CLIENT_ID or not DEFAULT_CLIENT_SECRET:
    try:
        from local_secrets import SPOTIFY_CLIENT_ID as DEFAULT_CLIENT_ID
        from local_secrets import SPOTIFY_CLIENT_SECRET as DEFAULT_CLIENT_SECRET
    except ImportError:
        pass
LOCAL_REDIRECT_URI = "http://127.0.0.1:8501/"
SCOPES = (
    "user-read-private "
    "user-read-email "
    "user-top-read "
    "playlist-modify-public "
    "playlist-modify-private"
)

TOKEN_FILE = ".spotify_token.json"

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
PROFILE_URL = "https://api.spotify.com/v1/me"


def is_streamlit_cloud():

    return (
        Path("/mount/src").exists()
        or os.environ.get("STREAMLIT_RUNTIME_ENV") == "cloud"
    )


def get_secret(name, default=None):

    try:
        return st.secrets[name]
    except Exception:
        return default


def get_spotify_client_id():

    return get_secret(
        "SPOTIFY_CLIENT_ID",
        DEFAULT_CLIENT_ID
    )


def get_spotify_client_secret():

    return get_secret(
        "SPOTIFY_CLIENT_SECRET",
        DEFAULT_CLIENT_SECRET
    )


def get_redirect_uri():

    configured = get_secret("SPOTIFY_REDIRECT_URI")

    if configured:

        return configured.rstrip("/") + "/"

    if is_streamlit_cloud():

        try:

            host = (
                st.context.headers.get("Host")
                or st.context.headers.get("host")
            )

        except Exception:

            host = None

        if host:

            return f"https://{host}/"

        raise RuntimeError(
            "Set SPOTIFY_REDIRECT_URI in Streamlit secrets to your "
            "exact app URL, for example "
            "https://your-app.streamlit.app/"
        )

    return LOCAL_REDIRECT_URI


def build_spotify_auth_url():

    auth_params = urllib.parse.urlencode(
        {
            "client_id": get_spotify_client_id(),
            "response_type": "code",
            "redirect_uri": get_redirect_uri(),
            "scope": SCOPES,
            "show_dialog": "true",
        }
    )

    return f"{AUTH_URL}?{auth_params}"


def exchange_code_for_token(code):

    client_id = get_spotify_client_id()
    client_secret = get_spotify_client_secret()
    auth_string = f"{client_id}:{client_secret}"
    auth_base64 = base64.b64encode(
        auth_string.encode("utf-8")
    ).decode("utf-8")

    response = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth_base64}"
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": get_redirect_uri(),
        },
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Token exchange failed ({response.status_code}): {response.text}"
        )

    return response.json()


def refresh_access_token(refresh_token):

    client_id = get_spotify_client_id()
    client_secret = get_spotify_client_secret()
    auth_string = f"{client_id}:{client_secret}"
    auth_base64 = base64.b64encode(
        auth_string.encode("utf-8")
    ).decode("utf-8")

    response = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth_base64}"
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Token refresh failed ({response.status_code}): {response.text}"
        )

    return response.json()


def load_saved_token():

    saved = st.session_state.get("spotify_token_data")

    if saved:

        return saved

    # Shared token files are unsafe for multi-user Cloud apps
    if is_streamlit_cloud():

        return None

    try:

        with open(TOKEN_FILE, encoding="utf-8") as file:

            return json.load(file)

    except (FileNotFoundError, json.JSONDecodeError):

        return None


def save_token(token_data):

    st.session_state["spotify_token_data"] = token_data

    if is_streamlit_cloud():

        return

    with open(TOKEN_FILE, "w", encoding="utf-8") as file:

        json.dump(token_data, file, indent=2)


def has_required_scopes(token_data):

    granted = set(
        token_data.get("scope", "").split()
    )

    return set(SCOPES.split()).issubset(granted)


def refresh_saved_access_token():

    saved = load_saved_token()

    if not saved or not saved.get("refresh_token"):

        return None

    # Refreshing keeps the scopes of the original login, so an older
    # token has to be replaced rather than reused
    if not has_required_scopes(saved):

        return None

    try:

        refreshed = refresh_access_token(
            saved["refresh_token"]
        )

    except RuntimeError:

        return None

    # Spotify only returns a new refresh token some of the time
    refresh_token = saved["refresh_token"]
    saved.update(refreshed)
    saved["refresh_token"] = refresh_token
    save_token(saved)

    return saved["access_token"]


def handle_spotify_callback():

    query_params = st.query_params

    if "error" in query_params:

        error = query_params.get("error")
        st.query_params.clear()
        st.error(
            f"Spotify login was denied or failed: {error}"
        )
        return False

    if "code" not in query_params:

        return False

    code = query_params.get("code")

    if isinstance(code, list):

        code = code[0]

    try:

        token_data = exchange_code_for_token(code)
        save_token(token_data)
        connected = connect_spotify(
            token_data["access_token"]
        )

    except RuntimeError as error:

        st.query_params.clear()
        st.error(
            f"Spotify login failed: {error}"
        )
        return False

    st.query_params.clear()

    return connected


# ============================================
# SPOTIFY USER PREFERENCES
# ============================================

def get_user_top_tracks(
    access_token,
    limit=30
):

    url = (
        "https://api.spotify.com/v1/"
        "me/top/tracks"
    )

    headers = {
        "Authorization":
            f"Bearer {access_token}"
    }

    params = {
        "limit": limit,
        "time_range": "medium_term"
    }

    response = requests.get(
        url,
        headers=headers,
        params=params
    )

    if response.status_code != 200:

        raise RuntimeError(
            "Could not retrieve Spotify preferences "
            f"({response.status_code}): {response.text}"
        )

    return response.json().get(
        "items",
        []
    )

def get_artist_genres(
    access_token,
    artist_ids
):

    genres = set()

    unique_ids = list(
        dict.fromkeys(artist_ids)
    )

    # The artists endpoint accepts 50 ids per request
    for start in range(0, len(unique_ids), 50):

        batch = unique_ids[start:start + 50]

        response = requests.get(
            "https://api.spotify.com/v1/artists",
            headers={
                "Authorization":
                    f"Bearer {access_token}"
            },
            params={
                "ids": ",".join(batch)
            }
        )

        if response.status_code != 200:
            continue

        for artist in response.json().get(
            "artists",
            []
        ):

            if not artist:
                continue

            for genre in artist.get(
                "genres",
                []
            ):

                genres.add(
                    genre.strip().lower()
                )

    return genres


# ============================================
# PERSONAL MUSIC PREFERENCES FROM SPOTIFY
# ============================================

def extract_artist_ids(
    top_tracks
):

    artist_ids = []

    for track in top_tracks:

        for artist in track.get(
            "artists",
            []
        ):

            artist_id = artist.get("id")

            if artist_id:

                artist_ids.append(artist_id)

    return artist_ids


def extract_spotify_preferences(
    top_tracks
):

    favorite_artists = []

    favorite_songs = []

    for track in top_tracks:

        track_name = (
            track.get(
                "name",
                ""
            )
            .strip()
            .lower()
        )

        if track_name:

            favorite_songs.append(
                track_name
            )

        for artist in track.get(
            "artists",
            []
        ):

            artist_name = (
                artist.get(
                    "name",
                    ""
                )
                .strip()
                .lower()
            )

            if artist_name:

                favorite_artists.append(
                    artist_name
                )

    favorite_artists = list(
        set(
            favorite_artists
        )
    )

    favorite_songs = list(
        set(
            favorite_songs
        )
    )

    return (
        favorite_artists,
        favorite_songs
    )


# ============================================
# MATCH SPOTIFY GENRES TO THE CATALOG
# ============================================

# Spotify uses free-form artist genres, the catalog uses 114 fixed labels,
# so a few common spellings need to be bridged by hand
GENRE_ALIASES = {
    "r-n-b": {"rnb", "rb", "randb"},
    "hip-hop": {"hiphop"},
    "drum-and-bass": {"drumandbass", "dnb"},
    "rock-n-roll": {"rocknroll", "rockandroll"},
    "world-music": {"world"},
    "singer-songwriter": {"singersongwriter"},
    "trip-hop": {"triphop"},
    "synth-pop": {"synthpop"},
    "indie-pop": {"indiepop"},
    "power-pop": {"powerpop"},
    "punk-rock": {"punkrock"},
    "hard-rock": {"hardrock"},
    "heavy-metal": {"heavymetal"},
    "new-age": {"newage"},
    "alt-rock": {"altrock", "alternativerock"}
}


def normalize_genre_text(text):

    return "".join(
        character
        for character in text.lower()
        if character.isalnum()
    )


def match_catalog_genres(spotify_genres):

    if GENRE_COLUMN is None:

        return set()

    # Match on the whole genre and on each word inside it, so that
    # "new wave pop" can still line up with the catalog's "pop"
    listened = set()

    for genre in spotify_genres:

        listened.add(
            normalize_genre_text(genre)
        )

        for word in genre.split():

            listened.add(
                normalize_genre_text(word)
            )

    catalog_genres = set(
        spotify_model[GENRE_COLUMN]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    matched = set()

    for catalog_genre in catalog_genres:

        spellings = {
            normalize_genre_text(catalog_genre)
        }

        spellings |= GENRE_ALIASES.get(
            catalog_genre,
            set()
        )

        if spellings & listened:

            matched.add(catalog_genre)

    return matched


# ============================================
# SCORE SONGS AGAINST SPOTIFY PREFERENCES
# ============================================

def add_preference_scores(
    songs,
    favorite_artists,
    favorite_songs,
    favorite_genres
):

    personalized = songs.copy()

    favorite_artists = set(favorite_artists)

    favorite_songs = set(favorite_songs)

    favorite_genres = set(favorite_genres)

    track_names = []
    artist_names = []

    for track_name, artists in zip(
        personalized[TRACK_NAME_COLUMN].tolist(),
        personalized[ARTISTS_COLUMN].tolist()
    ):

        if track_name is None or (
            isinstance(track_name, float)
            and pd.isna(track_name)
        ):

            track_names.append("")

        else:

            track_names.append(
                str(track_name).strip().lower()
            )

        if artists is None or (
            isinstance(artists, float)
            and pd.isna(artists)
        ):

            artist_names.append("")

        else:

            artist_names.append(
                str(artists).strip().lower()
            )

    title_match = [
        name in favorite_songs
        for name in track_names
    ]

    def has_favorite_artist(value):

        # A track can credit several artists, as in "artist a;artist b"
        for artist in value.split(";"):

            if artist.strip() in favorite_artists:

                return True

        return False

    artist_match = [
        has_favorite_artist(value)
        for value in artist_names
    ]

    # Titles repeat across the catalog, so a track only counts as one
    # the user listens to when the artist lines up as well
    song_match = [
        title and artist
        for title, artist in zip(
            title_match,
            artist_match
        )
    ]

    if GENRE_COLUMN is not None:

        genre_values = []

        for genre in personalized[GENRE_COLUMN].tolist():

            if genre is None or (
                isinstance(genre, float)
                and pd.isna(genre)
            ):

                genre_values.append("")

            else:

                genre_values.append(
                    str(genre).strip().lower()
                )

        genre_match = [
            genre in favorite_genres
            for genre in genre_values
        ]

    else:

        genre_match = [False] * len(personalized)

    SONG_MATCH_SCORE = 1.00
    ARTIST_MATCH_SCORE = 0.70
    GENRE_MATCH_SCORE = 0.35

    preference_scores = []

    for song_hit, artist_hit, genre_hit in zip(
        song_match,
        artist_match,
        genre_match
    ):

        if song_hit:

            preference_scores.append(
                SONG_MATCH_SCORE
            )

        elif artist_hit:

            preference_scores.append(
                ARTIST_MATCH_SCORE
            )

        elif genre_hit:

            preference_scores.append(
                GENRE_MATCH_SCORE
            )

        else:

            preference_scores.append(0.0)

    personalized["preference_score"] = preference_scores

    return personalized


# ============================================
# FEEDBACK MEMORY
# ============================================

FEEDBACK_FILE = "recommendation_feedback.csv"


def load_feedback():

    if Path(FEEDBACK_FILE).exists():

        feedback = pd.read_csv(
            FEEDBACK_FILE
        )

    else:

        feedback = pd.DataFrame(
            columns=[
                "user_id",
                "track_name",
                "artists",
                "pre_stress",
                "post_stress",
                "helpfulness",
                "timestamp"
            ]
        )

    return feedback


# ============================================
# SPOTIFY USER PROFILE
# ============================================

def get_spotify_profile(access_token):

    response = requests.get(
        PROFILE_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    )

    if response.status_code != 200:
        raise RuntimeError(
            "Could not retrieve Spotify profile."
        )

    return response.json()


def connect_spotify(access_token):

    try:
        profile = get_spotify_profile(access_token)
    except RuntimeError:
        return False

    st.session_state["spotify_access_token"] = access_token
    st.session_state["spotify_profile"] = profile

    return True


def restore_spotify_session():

    access_token = refresh_saved_access_token()

    if access_token is None:
        return False

    return connect_spotify(access_token)


def forget_spotify_session():

    if not is_streamlit_cloud():

        Path(TOKEN_FILE).unlink(
            missing_ok=True
        )

    for key in [
        "spotify_access_token",
        "spotify_profile",
        "spotify_token_data",
        "recommendations",
        "emotional_state",
        "taste"
    ]:

        st.session_state.pop(
            key,
            None
        )


# ============================================
# LEARN FROM PREVIOUS FEEDBACK
# ============================================

def add_feedback_scores(
    songs,
    user_id,
    stress_level
):

    personalized = songs.copy()

    feedback = load_feedback()

    # Unique song identifier
    personalized["song_key"] = (

        personalized[TRACK_NAME_COLUMN]
        .astype(str)
        .str.strip()
        .str.lower()

        +

        " | "

        +

        personalized[ARTISTS_COLUMN]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    # Artist identifier
    personalized["artist_key"] = (

        personalized[ARTISTS_COLUMN]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    # No previous feedback yet
    if feedback.empty:

        personalized["feedback_score"] = 0.0

        return personalized

    # Only use this user's previous results
    feedback = feedback[
        (
            feedback["user_id"] == user_id
        )
        &
        (
            feedback["pre_stress"] == stress_level
        )
    ].copy()

    if feedback.empty:

        personalized["feedback_score"] = 0.0

        return personalized

    feedback["song_key"] = (

        feedback["track_name"]
        .astype(str)
        .str.strip()
        .str.lower()

        +

        " | "

        +

        feedback["artists"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    feedback["artist_key"] = (

        feedback["artists"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    # Turn helpfulness rating into
    # values between -1 and +1
    feedback["helpfulness_score"] = (

        feedback["helpfulness"]
        -
        3

    ) / 2

    stress_numbers = {
        "Low Stress": 0,
        "Moderate Stress": 1,
        "High Stress": 2
    }

    feedback["pre_number"] = (
        feedback["pre_stress"]
        .map(stress_numbers)
    )

    feedback["post_number"] = (
        feedback["post_stress"]
        .map(stress_numbers)
    )

    # Positive number means stress decreased
    feedback["stress_improvement"] = (

        feedback["pre_number"]
        -
        feedback["post_number"]

    ) / 2

    # Combine subjective helpfulness
    # and reported stress change
    feedback["feedback_effect"] = (

        0.70
        *
        feedback["helpfulness_score"]

        +

        0.30
        *
        feedback["stress_improvement"]
    )

    # Average previous result for each song
    song_history = (

        feedback
        .groupby("song_key")[
            "feedback_effect"
        ]
        .mean()
    )

    # Average previous result for each artist
    artist_history = (

        feedback
        .groupby("artist_key")[
            "feedback_effect"
        ]
        .mean()
    )

    personalized["song_feedback"] = (

        personalized["song_key"]
        .map(song_history)
        .fillna(0)
    )

    personalized["artist_feedback"] = (

        personalized["artist_key"]
        .map(artist_history)
        .fillna(0)
    )

    personalized["feedback_score"] = (

        0.65
        *
        personalized["song_feedback"]

        +

        0.35
        *
        personalized["artist_feedback"]
    )

    return personalized



# ============================================
# FINAL PERSONALIZED SCORE
# ============================================

def calculate_final_score(songs):

    personalized = songs.copy()

    PREFERENCE_BONUS = 0.25
    FEEDBACK_BONUS = 0.10

    personalized["final_score"] = (

        personalized["emotional_distance"]

        -

        PREFERENCE_BONUS
        *
        personalized["preference_score"]

        -

        FEEDBACK_BONUS
        *
        personalized["feedback_score"]
    )

    # Lower score = better recommendation
    personalized = personalized.sort_values(
        "final_score",
        ascending=True
    )

    # Avoid duplicate versions of the same track
    personalized = personalized.drop_duplicates(
        subset=[
            TRACK_NAME_COLUMN,
            ARTISTS_COLUMN
        ]
    )

    return personalized


# ============================================
# COMPLETE VERSION 2 PIPELINE
# ============================================

def recommend_songs(
    stress_value,
    stress_level,
    user_id,
    spotify_top_tracks,
    access_token,
    number_of_songs=10,
    start_at=0
):

    # 1. Predict emotional state
    emotional_state = (
        calculate_target_state(
            stress_value
        )
    )

    # 2. Find emotional matches
    songs = (
        calculate_emotional_matches(

            emotional_state[
                "target_valence"
            ],

            emotional_state[
                "target_arousal"
            ]
        )
    )

    # 3. Convert Spotify listening
    # history into preferences
    (
        favorite_artists,
        favorite_songs
    ) = extract_spotify_preferences(
        spotify_top_tracks
    )

    spotify_genres = get_artist_genres(

        access_token,

        extract_artist_ids(
            spotify_top_tracks
        )
    )

    favorite_genres = match_catalog_genres(
        spotify_genres
    )

    # 4. Add Spotify preference score
    songs = add_preference_scores(

        songs,

        favorite_artists,

        favorite_songs,

        favorite_genres
    )

    # 5. Keep only music that matches the
    # user's taste, as long as that leaves
    # enough candidates to choose from
    familiar = songs[
        songs["preference_score"] > 0
    ]

    if len(familiar) >= number_of_songs:

        songs = familiar.copy()

    # 6. Add previous feedback
    songs = add_feedback_scores(

        songs,

        user_id,

        stress_level
    )

    # 7. Calculate final score
    songs = calculate_final_score(
        songs
    )

    start_at = max(int(start_at), 0)

    if start_at >= len(songs):

        start_at = 0

    recommendations = (
        songs
        .iloc[start_at:start_at + number_of_songs]
        .copy()
    )

    taste = {
        "favorite_genres": sorted(
            favorite_genres
        ),
        "favorite_artists": favorite_artists,
        "candidate_count": len(songs),
        "start_at": start_at
    }

    return (
        emotional_state,
        recommendations,
        taste
    )


def recommend_from_choices(
    stress_value,
    stress_level,
    user_id,
    favorite_artists,
    favorite_songs,
    favorite_genres,
    number_of_songs=10,
    start_at=0
):

    emotional_state = calculate_target_state(
        stress_value
    )

    songs = calculate_emotional_matches(
        emotional_state["target_valence"],
        emotional_state["target_arousal"]
    )

    songs = add_preference_scores(
        songs,
        favorite_artists,
        favorite_songs,
        favorite_genres
    )

    familiar = songs[
        songs["preference_score"] > 0
    ]

    if len(familiar) >= number_of_songs:

        songs = familiar.copy()

    songs = add_feedback_scores(
        songs,
        user_id,
        stress_level
    )

    songs = calculate_final_score(
        songs
    )

    start_at = max(int(start_at), 0)

    if start_at >= len(songs):

        start_at = 0

    recommendations = (
        songs
        .iloc[start_at:start_at + number_of_songs]
        .copy()
    )

    taste = {
        "favorite_genres": sorted(favorite_genres),
        "favorite_artists": list(favorite_artists),
        "candidate_count": len(songs),
        "start_at": start_at
    }

    return (
        emotional_state,
        recommendations,
        taste
    )


# ============================================
# STRESS FROM THE PSS FORM AND HEALTH INPUTS
# ============================================

# Perceived Stress Scale (PSS-10). Questions 4, 5, 7, and 8
# are reverse-scored: 0 becomes 4, 1 becomes 3, and so on.
PSS_QUESTIONS = [
    "In the last month, how often have you been upset because of something that happened unexpectedly?",
    "In the last month, how often have you felt that you were unable to control the important things in your life?",
    "In the last month, how often have you felt nervous and stressed?",
    "In the last month, how often have you felt confident about your ability to handle your personal problems?",
    "In the last month, how often have you felt that things were going your way?",
    "In the last month, how often have you found that you could not cope with all the things that you had to do?",
    "In the last month, how often have you been able to control irritations in your life?",
    "In the last month, how often have you felt that you were on top of things?",
    "In the last month, how often have you been angered because of things that happened that were outside of your control?",
    "In the last month, how often have you felt difficulties were piling up so high that you could not overcome them?"
]

PSS_REVERSE_QUESTIONS = {4, 5, 7, 8}

PSS_CHOICES = [
    "0 - never",
    "1 - almost never",
    "2 - sometimes",
    "3 - fairly often",
    "4 - very often"
]

FORM_WEIGHT = 0.40
OTHER_WEIGHT = 0.60


def score_pss(answers):

    total = 0

    for number, answer in enumerate(answers, start=1):

        if number in PSS_REVERSE_QUESTIONS:

            total += 4 - answer

        else:

            total += answer

    # Official total is 0–40. Divide by 20 so it sits on the
    # same 0 (low) to 2 (high) scale as the rest of the model.
    return total, total / 20.0


def pss_band(total):

    if total <= 13:

        return "Low Stress"

    if total <= 26:

        return "Moderate Stress"

    return "High Stress"


def heart_rate_stress(heart_rate):

    # Resting heart rate: about 60 bpm is low stress, about 105 is high.
    return float(
        np.clip((heart_rate - 60) / 22.5, 0, 2)
    )


def hrv_stress(hrv):

    # Higher heart-rate variability is calmer.
    # About 60 ms is low stress, about 20 ms is high.
    return float(
        np.clip((60 - hrv) / 20, 0, 2)
    )


def sleep_stress(hours):

    # 8 hours is the calm center. Two hours away is one stress step.
    return float(
        np.clip(abs(hours - 8) / 2, 0, 2)
    )


def average_health_stress(heart_rate, hrv, sleep_hours):

    pieces = []

    if heart_rate is not None:

        pieces.append(heart_rate_stress(heart_rate))

    if hrv is not None:

        pieces.append(hrv_stress(hrv))

    if sleep_hours is not None:

        pieces.append(sleep_stress(sleep_hours))

    if not pieces:

        return None

    return float(np.mean(pieces))


def blend_stress(form_value, other_value):

    if other_value is None:

        return form_value

    return (
        FORM_WEIGHT * form_value
        +
        OTHER_WEIGHT * other_value
    )


def stress_label_from_value(value):

    if value < 0.67:

        return "Low Stress"

    if value < 1.34:

        return "Moderate Stress"

    return "High Stress"


def catalog_genre_choices():

    if GENRE_COLUMN is None:

        return []

    genres = (
        spotify_model[GENRE_COLUMN]
        .dropna()
        .astype(str)
        .str.strip()
        .str.lower()
        .unique()
    )

    return sorted(genres)


def catalog_artist_choices(limit=250):

    counts = {}

    for value in spotify_model[ARTISTS_COLUMN].dropna().astype(str):

        for artist in value.split(";"):

            name = artist.strip()

            if name:

                counts[name] = counts.get(name, 0) + 1

    ranked = sorted(
        counts,
        key=counts.get,
        reverse=True
    )

    return ranked[:limit]


def catalog_song_choices(limit=400):

    counts = {}

    for value in spotify_model[TRACK_NAME_COLUMN].dropna().astype(str):

        name = value.strip()

        if name:

            counts[name] = counts.get(name, 0) + 1

    ranked = sorted(
        counts,
        key=counts.get,
        reverse=True
    )

    return ranked[:limit]


def split_names(text):

    names = []

    for piece in text.split(","):

        name = piece.strip().lower()

        if name:

            names.append(name)

    return names


def read_healthkit_callback():

    params = st.query_params

    if not any(
        key in params
        for key in ("hk_hr", "hk_hrv", "hk_sleep")
    ):

        return

    def read_number(key):

        raw = params.get(key)

        if raw in (None, ""):

            return None

        try:

            return float(raw)

        except (TypeError, ValueError):

            return None

    st.session_state["healthkit_reading"] = {
        "heart_rate": read_number("hk_hr"),
        "hrv": read_number("hk_hrv"),
        "sleep_hours": read_number("hk_sleep")
    }

    for key in ("hk_hr", "hk_hrv", "hk_sleep"):

        if key in st.query_params:

            del st.query_params[key]


# ============================================
# SAVE USER FEEDBACK
# ============================================

def save_feedback(
    user_id,
    track_name,
    artists,
    pre_stress,
    post_stress,
    helpfulness
):

    feedback = load_feedback()

    new_feedback = pd.DataFrame(
        [
            {
                "user_id": user_id,
                "track_name": track_name,
                "artists": artists,
                "pre_stress": pre_stress,
                "post_stress": post_stress,
                "helpfulness": helpfulness,
                "timestamp": pd.Timestamp.now()
            }
        ]
    )

    feedback = pd.concat(
        [
            feedback,
            new_feedback
        ],
        ignore_index=True
    )

    feedback.to_csv(
        FEEDBACK_FILE,
        index=False
    )

def run_streamlit_app():
    st.title(
        "Stress-Aware Music Recommender"
    )

    st.write(
        """
        This system combines a stress questionnaire,
        optional heart rate, HRV, and sleep, and either
        your Spotify history or genres and artists you pick.
        """
    )

    # ============================================
    # MUSIC TASTE: SPOTIFY OR MANUAL CHOICES
    # ============================================

    if "spotify_access_token" not in st.session_state:

        if handle_spotify_callback():

            st.rerun()

    if "spotify_access_token" not in st.session_state:

        restore_spotify_session()

    spotify_connected = (
        "spotify_access_token" in st.session_state
    )

    st.subheader(
        "Your music taste"
    )

    taste_mode = st.radio(
        "How should songs be personalized?",
        [
            "I'll choose genres and artists",
            "Use my Spotify account"
        ],
        horizontal=True
    )

    manual_genres = []
    manual_artists = []
    manual_songs = []

    if taste_mode == "Use my Spotify account":

        if spotify_connected:

            profile = st.session_state["spotify_profile"]

            st.success(
                "Spotify connected: "
                +
                profile.get(
                    "display_name",
                    "Spotify User"
                )
            )

            if st.button("Disconnect Spotify"):

                forget_spotify_session()
                st.rerun()

        else:

            st.write(
                "Log in to use your top tracks, artists, and genres. "
                "You can also switch to choosing them yourself."
            )

            try:

                redirect_uri = get_redirect_uri()
                auth_url = build_spotify_auth_url()

                st.info(
                    "In your Spotify Developer Dashboard, add this "
                    "exact Redirect URI and click Save:\n\n"
                    f"`{redirect_uri}`"
                )

                st.link_button(
                    "Log in with Spotify",
                    auth_url
                )

            except RuntimeError as error:

                st.error(str(error))

    else:

        manual_genres = st.multiselect(
            "Favorite genres",
            catalog_genre_choices()
        )

        manual_artists = st.multiselect(
            "Favorite artists",
            catalog_artist_choices()
        )

        extra_artists = st.text_input(
            "Other artists (comma-separated)",
            placeholder="e.g. Mitski, Laufey"
        )

        manual_songs = st.text_input(
            "Favorite songs, optional (comma-separated)",
            placeholder="e.g. Heartbeat, Last Christmas"
        )

        manual_artists = (
            [name.lower() for name in manual_artists]
            +
            split_names(extra_artists)
        )

        manual_songs = split_names(manual_songs)

    # ============================================
    # STRESS: PSS FORM (40%) + HEALTH OR SELF (60%)
    # ============================================

    st.subheader(
        "Your stress level"
    )

    st.write(
        """
        The questionnaire is 40% of the stress score.
        Heart rate, HRV, and sleep — or your own rating —
        are the other 60%. If you skip that second part,
        the questionnaire is used on its own.
        """
    )

    st.caption(
        "0 - never, 1 - almost never, 2 - sometimes, "
        "3 - fairly often, 4 - very often. "
        "Questions 4, 5, 7, and 8 are reverse-scored."
    )

    pss_answers = []

    for number, question in enumerate(PSS_QUESTIONS, start=1):

        choice = st.selectbox(
            f"{number}. {question}",
            PSS_CHOICES,
            key=f"pss_{number}"
        )

        pss_answers.append(
            PSS_CHOICES.index(choice)
        )

    health_mode = st.radio(
        "Where should heart rate, HRV, and sleep come from?",
        [
            "Apple Health (HealthKit)",
            "I'll enter them myself"
        ]
    )

    heart_rate = None
    hrv = None
    sleep_hours = None

    read_healthkit_callback()

    if health_mode == "Apple Health (HealthKit)":

        st.write(
            """
            Apple HealthKit can only be read by the Health app and
            Shortcuts on your iPhone. This website cannot open HealthKit
            itself. A Shortcut reads resting heart rate, HRV, and last
            night's sleep, then sends those numbers back here.
            """
        )

        try:

            app_url = get_redirect_uri()

        except RuntimeError:

            app_url = "https://YOUR-APP.streamlit.app/"

        return_url = (
            f"{app_url}?hk_hr=HR&hk_hrv=HRV&hk_sleep=SLEEP"
        )

        with st.expander(
            "Set up the HealthKit Shortcut (one time)"
        ):

            st.markdown(
                "In the Shortcuts app, create a shortcut named "
                "**Music Stress Health** with these actions:\n\n"
                "1. **Find Health Samples** where Type is Resting Heart Rate, "
                "Sort by Start Date, Order Latest First, Limit 1. "
                "Set the variable name to HR.\n"
                "2. **Find Health Samples** where Type is "
                "Heart Rate Variability, same sort and limit. "
                "Name it HRV.\n"
                "3. **Find Health Samples** where Type is Sleep, "
                "last night's asleep time in hours. Name it SLEEP.\n"
                "4. **Open URLs** with this address, using the sample values:\n\n"
                f"`{return_url}`"
            )

        st.link_button(
            "Read from Apple Health",
            "shortcuts://run-shortcut?name=Music%20Stress%20Health"
        )

        reading = st.session_state.get("healthkit_reading")

        if reading:

            heart_rate = reading.get("heart_rate")
            hrv = reading.get("hrv")
            sleep_hours = reading.get("sleep_hours")

            st.success(
                "HealthKit sent "
                f"heart rate {heart_rate if heart_rate is not None else '—'} bpm, "
                f"HRV {hrv if hrv is not None else '—'} ms, "
                f"sleep {sleep_hours if sleep_hours is not None else '—'} hours."
            )

        else:

            st.info(
                "After the Shortcut runs, this page reopens with your "
                "HealthKit numbers. Until then, the questionnaire is used alone."
            )

    else:

        hrv = None

        st.caption(
            "Resting heart rate near 60 bpm and about 8 hours "
            "of sleep score as low stress."
        )

        heart_rate = st.number_input(
            "Resting heart rate (bpm)",
            min_value=30,
            max_value=220,
            value=72
        )

        sleep_hours = st.number_input(
            "Sleep last night (hours)",
            min_value=0.0,
            max_value=16.0,
            value=7.5,
            step=0.5
        )


    if st.button(
        "Recommend Music"
    ):

        pss_total, pss_value = score_pss(pss_answers)

        if health_mode == "I'll enter them myself" or (
            heart_rate is not None
            or hrv is not None
            or sleep_hours is not None
        ):

            other_value = average_health_stress(
                heart_rate,
                hrv,
                sleep_hours
            )

        else:

            other_value = None

        stress_value = blend_stress(
            pss_value,
            other_value
        )

        stress_level = stress_label_from_value(
            stress_value
        )

        use_spotify = (
            taste_mode == "Use my Spotify account"
            and
            spotify_connected
        )

        if (
            taste_mode == "Use my Spotify account"
            and
            not spotify_connected
        ):

            st.warning(
                "Log in with Spotify, or switch to "
                "choosing genres and artists yourself."
            )

        elif (
            not use_spotify
            and
            not manual_genres
            and
            not manual_artists
            and
            not manual_songs
        ):

            st.warning(
                "Pick at least one genre, artist, or song."
            )

        else:

            if use_spotify:

                access_token = st.session_state[
                    "spotify_access_token"
                ]

                profile = st.session_state[
                    "spotify_profile"
                ]

                user_id = profile["id"]

                with st.spinner(
                    "Reading your Spotify taste and "
                    "matching it to your stress level..."
                ):

                    top_tracks = get_user_top_tracks(
                        access_token
                    )

                    (
                        emotional_state,
                        recommendations,
                        taste
                    ) = recommend_songs(
                        stress_value,
                        stress_level,
                        user_id,
                        top_tracks,
                        access_token,
                        number_of_songs=10,
                        start_at=0
                    )

            else:

                user_id = "self-reported"

                with st.spinner(
                    "Matching songs to your stress level "
                    "and the genres and artists you picked..."
                ):

                    (
                        emotional_state,
                        recommendations,
                        taste
                    ) = recommend_from_choices(
                        stress_value,
                        stress_level,
                        user_id,
                        manual_artists,
                        manual_songs,
                        set(manual_genres),
                        number_of_songs=10,
                        start_at=0
                    )

            st.session_state["recommendations"] = recommendations
            st.session_state["emotional_state"] = emotional_state
            st.session_state["taste"] = taste
            st.session_state["user_id"] = user_id
            st.session_state["pre_stress"] = stress_level
            st.session_state["stress_breakdown"] = {
                "pss_total": pss_total,
                "pss_band": pss_band(pss_total),
                "form_value": pss_value,
                "other_value": other_value,
                "combined": stress_value,
                "label": stress_level,
                "used_other": other_value is not None
            }

            st.session_state["last_request"] = {
                "stress_value": stress_value,
                "stress_level": stress_level,
                "user_id": user_id,
                "use_spotify": use_spotify,
                "start_at": taste.get("start_at", 0)
            }

            if use_spotify:

                st.session_state["last_request"]["top_tracks"] = top_tracks
                st.session_state["last_request"]["access_token"] = access_token

            else:

                st.session_state["last_request"]["manual_artists"] = manual_artists
                st.session_state["last_request"]["manual_songs"] = manual_songs
                st.session_state["last_request"]["manual_genres"] = list(manual_genres)

    # ============================================
    # DISPLAY EMOTIONAL STATE
    # ============================================

    if "emotional_state" in st.session_state:

        emotional_state = (
            st.session_state[
                "emotional_state"
            ]
        )

        st.subheader(
            "Emotional State Analysis"
        )

        breakdown = st.session_state.get(
            "stress_breakdown"
        )

        if breakdown:

            if breakdown["used_other"]:

                mix = (
                    f"Questionnaire {int(FORM_WEIGHT * 100)}% + "
                    f"health or self-rating {int(OTHER_WEIGHT * 100)}%"
                )

            else:

                mix = "Questionnaire only (the other 60% was left blank)"

            st.caption(mix)

            score_cols = st.columns(3)

            score_cols[0].metric(
                "PSS total (0–40)",
                breakdown["pss_total"]
            )

            score_cols[1].metric(
                "PSS band",
                breakdown["pss_band"]
            )

            score_cols[2].metric(
                "Combined stress",
                breakdown["label"]
            )

        col1, col2 = st.columns(2)

        with col1:

            st.write(
                "Predicted Current State"
            )

            st.metric(
                "Current Valence",
                round(
                    emotional_state[
                        "current_valence"
                    ],
                    3
                )
            )

            st.metric(
                "Current Arousal",
                round(
                    emotional_state[
                        "current_arousal"
                    ],
                    3
                )
            )

        with col2:

            st.write(
                "Target State"
            )

            st.metric(
                "Target Valence",
                round(
                    emotional_state[
                        "target_valence"
                    ],
                    3
                )
            )

            st.metric(
                "Target Arousal",
                round(
                    emotional_state[
                        "target_arousal"
                    ],
                    3
                )
            )


    # ============================================
    # DISPLAY RECOMMENDATIONS
    # ============================================

    if "recommendations" in st.session_state:

        recommendations = (
            st.session_state[
                "recommendations"
            ]
        )

        taste = st.session_state.get(
            "taste",
            {}
        )

        st.subheader(
            "Your Top 10 Songs"
        )

        favorite_genres = taste.get(
            "favorite_genres",
            []
        )

        if favorite_genres:

            st.caption(
                "Matched against genres you listen to: "
                +
                ", ".join(favorite_genres)
            )

        else:

            target_arousal = st.session_state.get(
                "emotional_state",
                {}
            ).get("target_arousal")

            if target_arousal is not None and target_arousal <= 0.35:

                st.caption(
                    "High stress, so these stay low-energy "
                    "and skip rock and hype genres."
                )

            else:

                st.caption(
                    "No overlap was found between your Spotify genres "
                    "and this catalog, so these are ranked on emotional "
                    "fit alone."
                )

        for rank, (_, song) in enumerate(
            recommendations.iterrows(),
            start=taste.get("start_at", 0) + 1
        ):

            if GENRE_COLUMN is not None:

                genre_note = f" · {song[GENRE_COLUMN]}"

            else:

                genre_note = ""

            st.markdown(
                f"**{rank}. {song[TRACK_NAME_COLUMN]}** — "
                f"{song[ARTISTS_COLUMN]}{genre_note}"
            )

            st.caption(
                f"valence {song[SPOTIFY_VALENCE_COLUMN]:.2f} · "
                f"energy {song[ENERGY_COLUMN]:.2f} · "
                f"taste match {song['preference_score']:.2f}"
            )

        if st.button("Recommend again"):

            request = st.session_state.get("last_request")

            if not request:

                st.warning(
                    "Get a first set of songs before asking for another."
                )

            else:

                next_start = request.get("start_at", 0) + 10

                if request.get("use_spotify"):

                    (
                        emotional_state,
                        recommendations,
                        taste
                    ) = recommend_songs(
                        request["stress_value"],
                        request["stress_level"],
                        request["user_id"],
                        request["top_tracks"],
                        request["access_token"],
                        number_of_songs=10,
                        start_at=next_start
                    )

                else:

                    (
                        emotional_state,
                        recommendations,
                        taste
                    ) = recommend_from_choices(
                        request["stress_value"],
                        request["stress_level"],
                        request["user_id"],
                        request["manual_artists"],
                        request["manual_songs"],
                        set(request["manual_genres"]),
                        number_of_songs=10,
                        start_at=next_start
                    )

                request["start_at"] = taste.get("start_at", 0)
                st.session_state["last_request"] = request
                st.session_state["recommendations"] = recommendations
                st.session_state["emotional_state"] = emotional_state
                st.session_state["taste"] = taste
                st.rerun()

        with st.expander(
            "Show scoring details"
        ):

            display_columns = [
                TRACK_NAME_COLUMN,
                ARTISTS_COLUMN,
                SPOTIFY_VALENCE_COLUMN,
                ENERGY_COLUMN,
                "preference_score",
                "feedback_score",
                "final_score"
            ]

            if GENRE_COLUMN is not None:

                display_columns.insert(
                    2,
                    GENRE_COLUMN
                )

            st.dataframe(
                recommendations[
                    display_columns
                ],
                use_container_width=True,
                hide_index=True
            )


    # ============================================
    # FEEDBACK ON ONE SONG
    # ============================================

    if "recommendations" in st.session_state:

        recommendations = (
            st.session_state[
                "recommendations"
            ]
        )

        st.subheader(
            "Rate one of these songs"
        )

        song_labels = [

            f"{rank}. {song[TRACK_NAME_COLUMN]}"
            f" — {song[ARTISTS_COLUMN]}"

            for rank, (_, song) in enumerate(
                recommendations.iterrows(),
                start=1
            )
        ]

        chosen_label = st.selectbox(
            "Which song did you listen to?",
            song_labels
        )

        current_song = recommendations.iloc[
            song_labels.index(chosen_label)
        ]

        helpfulness = st.slider(
            "How much did the song help?",
            min_value=1,
            max_value=5,
            value=3
        )

        post_stress = st.selectbox(
            "How stressed do you feel after listening?",
            [
                "Low Stress",
                "Moderate Stress",
                "High Stress"
            ]
        )

        if st.button(
            "Save Feedback"
        ):

            save_feedback(

                st.session_state[
                    "user_id"
                ],

                current_song[
                    TRACK_NAME_COLUMN
                ],

                current_song[
                    ARTISTS_COLUMN
                ],

                st.session_state[
                    "pre_stress"
                ],

                post_stress,

                helpfulness
            )

            st.success(
                "Feedback saved. "
                "Future recommendations can use this result."
            )




if __name__ == "__main__":
    run_streamlit_app()
