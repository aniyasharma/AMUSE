import base64
import os
import socket
import sys
import urllib.parse
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

import requests
from flask import Flask, jsonify, redirect, render_template, request, session

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import version3 as amuse
from web import db
from web import shortcut_builder

app = Flask(__name__)
app.secret_key = os.environ.get("AMUSE_SECRET", "amuse-local-dev")

# Spotify only allows HTTP for loopback 127.0.0.1 — never LAN IP or localhost.
REDIRECT_URI = os.environ.get(
    "AMUSE_REDIRECT_URI",
    "http://127.0.0.1:8501/",
)


def spotify_redirect_uri():

    return REDIRECT_URI if REDIRECT_URI.endswith("/") else REDIRECT_URI + "/"


def public_base_url():

    return f"{request.scheme}://{request.host}"


def can_start_spotify_oauth():

    host = request.host.split(":")[0]
    return host == "127.0.0.1"


PSS_MAX_AGE_DAYS = 7


def today_local():

    return date.today().isoformat()


def parse_iso(value):

    if not value:

        return None

    try:

        return datetime.fromisoformat(str(value).replace("Z", ""))

    except ValueError:

        return None


def health_status(user_id, session_hrv_ok=False):

    health = db.load_health(user_id)
    prefs = db.load_preferences(user_id)
    sleep_ok = health.get("sleep_date") == today_local() and health.get("sleep_hours") is not None
    pss_at = parse_iso(health.get("pss_at"))
    pss_ok = False

    if pss_at and prefs and prefs.get("last_pss") and len(prefs["last_pss"]) == 10:

        pss_ok = datetime.utcnow() - pss_at <= timedelta(days=PSS_MAX_AGE_DAYS)

    # HRV is required once per browser/app open (client session flag).
    hrv_ok = bool(session_hrv_ok)

    return {
        "health": health,
        "sleep_ok": sleep_ok,
        "pss_ok": pss_ok,
        "hrv_ok": hrv_ok,
        "needs_sleep": not sleep_ok,
        "needs_pss": not pss_ok,
        "needs_hrv": not hrv_ok,
        "today": today_local(),
    }


def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if "user_id" not in session:

            if request.path.startswith("/api/"):

                return jsonify({"error": "Sign in first."}), 401

            return redirect("/")

        return view(*args, **kwargs)

    return wrapped


def exchange_code(code):

    client_id = amuse.DEFAULT_CLIENT_ID
    client_secret = amuse.DEFAULT_CLIENT_SECRET
    auth_string = f"{client_id}:{client_secret}"
    auth_base64 = base64.b64encode(
        auth_string.encode("utf-8")
    ).decode("utf-8")

    response = requests.post(
        amuse.TOKEN_URL,
        headers={"Authorization": f"Basic {auth_base64}"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": spotify_redirect_uri(),
        },
        timeout=30,
    )

    if response.status_code != 200:

        raise RuntimeError(response.text)

    return response.json()


def store_spotify_tokens(user_id, token_data, profile=None):

    expires_in = int(token_data.get("expires_in") or 3600)
    expires_at = (datetime.utcnow() + timedelta(seconds=expires_in - 60)).isoformat()
    profile = profile or {}

    db.save_spotify_account(
        user_id,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        spotify_user=profile.get("id") or session.get("spotify_user"),
        spotify_name=profile.get("display_name") or session.get("spotify_name"),
        scope=token_data.get("scope"),
        expires_at=expires_at,
    )

    session["spotify_token"] = token_data["access_token"]
    if profile.get("display_name"):
        session["spotify_name"] = profile["display_name"]
    if profile.get("id"):
        session["spotify_user"] = profile["id"]


def spotify_access_for_user(user_id):

    account = db.load_spotify_account(user_id)

    if not account:

        token = session.get("spotify_token")
        return token, session.get("spotify_name", ""), session.get("spotify_user", "")

    expires_at = account.get("expires_at")
    needs_refresh = False

    if expires_at:

        try:

            needs_refresh = datetime.fromisoformat(expires_at) <= datetime.utcnow()

        except ValueError:

            needs_refresh = True

    if needs_refresh and account.get("refresh_token"):

        try:

            token_data = amuse.refresh_access_token(account["refresh_token"])
            store_spotify_tokens(user_id, token_data, {
                "id": account.get("spotify_user"),
                "display_name": account.get("spotify_name"),
            })
            account = db.load_spotify_account(user_id)

        except RuntimeError:

            db.clear_spotify_account(user_id)
            session.pop("spotify_token", None)
            return None, "", ""

    session["spotify_token"] = account["access_token"]
    session["spotify_name"] = account.get("spotify_name") or "Spotify"
    session["spotify_user"] = account.get("spotify_user") or ""

    return (
        account["access_token"],
        account.get("spotify_name") or "Spotify",
        account.get("spotify_user") or "",
    )


def song_rows(frame):

    rows = []

    for _, song in frame.iterrows():

        genre = ""

        if amuse.GENRE_COLUMN is not None:

            genre = str(song[amuse.GENRE_COLUMN])

        track_id = ""

        if "track_id" in song.index and song["track_id"] is not None:

            track_id = str(song["track_id"])

        rows.append({
            "track_id": track_id,
            "track_name": str(song[amuse.TRACK_NAME_COLUMN]),
            "artists": str(song[amuse.ARTISTS_COLUMN]),
            "genre": genre,
            "valence": round(float(song[amuse.SPOTIFY_VALENCE_COLUMN]), 3),
            "energy": round(float(song[amuse.ENERGY_COLUMN]), 3),
            "preference": round(float(song["preference_score"]), 2),
        })

    return rows


def number_or_none(value):

    if value in (None, ""):

        return None

    return float(value)


def lan_ip():

    try:

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        address = sock.getsockname()[0]
        sock.close()
        return address

    except OSError:

        return "your-computer-ip"


@app.get("/")
def home():

    if request.args.get("code") or request.args.get("error"):

        return finish_spotify_login()

    return render_template("index.html")


@app.get("/api/me")
def me():

    if "user_id" not in session:

        return jsonify({"signed_in": False})

    prefs = db.load_preferences(session["user_id"])
    status = health_status(
        session["user_id"],
        session_hrv_ok=bool(session.get("hrv_session_ok")),
    )

    return jsonify({
        "signed_in": True,
        "name": session.get("user_name", ""),
        "email": session.get("user_email", ""),
        "preferences": prefs,
        "has_taste": bool(
            prefs
            and (
                prefs["genres"]
                or prefs["artists"]
                or prefs["songs"]
                or prefs["use_spotify"]
            )
        ),
        "checkin": status,
    })


@app.post("/api/checkin")
@login_required
def post_checkin():

    data = request.get_json(force=True)
    sleep_hours = number_or_none(data.get("sleep_hours"))
    hrv = number_or_none(data.get("hrv"))
    heart_rate = number_or_none(data.get("heart_rate"))
    mark_sleep = bool(data.get("mark_sleep"))
    mark_hrv = bool(data.get("mark_hrv"))

    if mark_sleep:

        if sleep_hours is None or sleep_hours <= 0 or sleep_hours > 24:

            return jsonify({"error": "Enter last night's sleep in hours (required today)."}), 400

    if mark_hrv:

        if hrv is None or hrv <= 0:

            return jsonify({"error": "Enter your HRV for this session (required)."}), 400

        session["hrv_session_ok"] = True

    health = db.save_health(
        session["user_id"],
        sleep_hours=sleep_hours if mark_sleep else None,
        sleep_date=today_local() if mark_sleep else None,
        hrv=hrv if mark_hrv else None,
        hrv_at=datetime.utcnow().isoformat() if mark_hrv else None,
        heart_rate=heart_rate,
    )

    status = health_status(
        session["user_id"],
        session_hrv_ok=bool(session.get("hrv_session_ok")),
    )
    status["health"] = health

    return jsonify({"ok": True, "checkin": status})


@app.post("/api/signup")
def signup():

    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if len(name) < 2:

        return jsonify({"error": "Enter your name."}), 400

    if "@" not in email:

        return jsonify({"error": "Enter a valid email."}), 400

    if len(password) < 6:

        return jsonify({"error": "Password needs at least 6 characters."}), 400

    if db.find_user_by_email(email):

        return jsonify({"error": "That email already has an account."}), 400

    user = db.create_user(name, email, password)
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]

    return jsonify({"ok": True, "name": user["name"]})


@app.post("/api/signin")
def signin():

    data = request.get_json(force=True)
    user = db.authenticate(
        data.get("email") or "",
        data.get("password") or "",
    )

    if not user:

        return jsonify({"error": "Email or password is wrong."}), 401

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]

    return jsonify({"ok": True, "name": user["name"]})


@app.post("/api/signout")
def signout():

    session.clear()
    return jsonify({"ok": True})


@app.post("/api/session-hrv-clear")
@login_required
def clear_session_hrv():

    session.pop("hrv_session_ok", None)
    return jsonify({"ok": True})


@app.post("/api/forgot-password")
def forgot_password():

    data = request.get_json(force=True)
    email = (data.get("email") or "").strip()
    name = (data.get("name") or "").strip()
    password = data.get("password") or ""
    confirm = data.get("confirm") or ""

    if "@" not in email:

        return jsonify({"error": "Enter the email on your account."}), 400

    if len(name) < 2:

        return jsonify({"error": "Enter the name on your account."}), 400

    if len(password) < 6:

        return jsonify({"error": "Password needs at least 6 characters."}), 400

    if password != confirm:

        return jsonify({"error": "Passwords do not match."}), 400

    user = db.reset_password(email, name, password)

    if not user:

        return jsonify({
            "error": "No account matched that email and name.",
        }), 404

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]

    return jsonify({"ok": True, "name": user["name"]})


@app.get("/api/options")
@login_required
def options():

    return jsonify({
        "genres": amuse.catalog_genre_choices(),
        "artists": amuse.catalog_artist_choices(),
        "songs": amuse.catalog_song_choices(),
        "questions": amuse.PSS_QUESTIONS,
        "choices": [
            "Never",
            "Almost never",
            "Sometimes",
            "Fairly often",
            "Very often",
        ],
    })


@app.get("/api/preferences")
@login_required
def get_preferences():

    prefs = db.load_preferences(session["user_id"])

    return jsonify(prefs or {
        "genres": [],
        "artists": [],
        "songs": [],
        "use_spotify": False,
        "last_pss": None,
    })


@app.post("/api/preferences")
@login_required
def post_preferences():

    data = request.get_json(force=True)
    last_pss = data.get("last_pss")

    db.save_preferences(
        session["user_id"],
        data.get("genres") or [],
        data.get("artists") or [],
        data.get("songs") or [],
        bool(data.get("use_spotify")),
        last_pss,
    )

    if last_pss is not None and len(last_pss) == 10:

        db.save_health(
            session["user_id"],
            pss_at=datetime.utcnow().isoformat(),
        )

    return jsonify({"ok": True})


@app.get("/api/spotify")
@login_required
def spotify_status():

    token, name, _user = spotify_access_for_user(session["user_id"])

    return jsonify({
        "connected": bool(token),
        "name": name if token else "",
        "redirect_uri": spotify_redirect_uri(),
        "can_connect_here": can_start_spotify_oauth(),
        "connect_url": "http://127.0.0.1:8501/",
    })


@app.get("/api/device")
def device_info():

    base = public_base_url().rstrip("/")
    return jsonify({
        "base_url": base,
        "lan_ip": lan_ip(),
        "spotify_redirect": spotify_redirect_uri(),
        "can_connect_spotify_here": can_start_spotify_oauth(),
        "watch_shortcut_name": "AMUSE Watch",
        "watch_install_url": "/amuse-watch.shortcut",
        "watch_run_url": "shortcuts://run-shortcut?name=AMUSE%20Watch",
        "watch_url_prefix": f"{base}/?hk_hrv=",
        "watch_url_example": (
            f"{base}/?hk_hrv=45&hk_sleep=7.5&hk_hr=62"
        ),
        "spotify_help": (
            "Delete any phone / Wi‑Fi IP from the Spotify Dashboard. "
            "Keep only http://127.0.0.1:8501/ then connect on your Mac at that URL."
        ),
    })


@app.get("/amuse-watch.shortcut")
def download_watch_shortcut():

    """Generate (and sign when possible) an AMUSE Watch shortcut for this host."""

    base = public_base_url().rstrip("/")
    path, signed = shortcut_builder.build_for_base_url(base)
    data = path.read_bytes()
    headers = {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": 'attachment; filename="AMUSE-Watch.shortcut"',
        "X-AMUSE-Shortcut-Signed": "1" if signed else "0",
    }
    return data, 200, headers


@app.get("/spotify/login")
@login_required
def spotify_login():

    if not can_start_spotify_oauth():

        return redirect("/?spotify=use-computer")

    params = urllib.parse.urlencode({
        "client_id": amuse.DEFAULT_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": spotify_redirect_uri(),
        "scope": amuse.SCOPES,
        "show_dialog": "true",
    })

    return redirect(f"{amuse.AUTH_URL}?{params}")


@app.get("/spotify/callback")
@app.get("/callback")
def spotify_callback():

    return finish_spotify_login()


def finish_spotify_login():

    if request.args.get("error"):

        return redirect("/?spotify=denied")

    code = request.args.get("code")

    if not code:

        return redirect("/")

    if "user_id" not in session:

        return redirect("/?spotify=signin-first")

    token_data = exchange_code(code)
    access_token = token_data["access_token"]
    profile = amuse.get_spotify_profile(access_token)
    store_spotify_tokens(session["user_id"], token_data, profile)
    prefs = db.load_preferences(session["user_id"]) or {
        "genres": [],
        "artists": [],
        "songs": [],
        "use_spotify": True,
        "last_pss": None,
    }
    db.save_preferences(
        session["user_id"],
        prefs.get("genres") or [],
        prefs.get("artists") or [],
        prefs.get("songs") or [],
        True,
        prefs.get("last_pss"),
    )

    return redirect("/?spotify=connected")


@app.post("/spotify/logout")
@login_required
def spotify_logout():

    db.clear_spotify_account(session["user_id"])
    session.pop("spotify_token", None)
    session.pop("spotify_name", None)
    session.pop("spotify_user", None)

    return jsonify({"ok": True})


@app.post("/api/recommend")
@login_required
def recommend():

    data = request.get_json(force=True)
    answers = [int(value) for value in data.get("pss", [])]

    if len(answers) != 10:

        return jsonify({"error": "Answer all 10 stress questions."}), 400

    pss_total, pss_value = amuse.score_pss(answers)
    status = health_status(
        session["user_id"],
        session_hrv_ok=bool(session.get("hrv_session_ok")),
    )
    health = status["health"]

    if status["needs_pss"]:

        return jsonify({
            "error": "Complete this week's stress questionnaire first.",
            "needs_pss": True,
        }), 400

    if status["needs_sleep"]:

        return jsonify({
            "error": "Enter last night's sleep hours (required once each day).",
            "needs_sleep": True,
        }), 400

    if status["needs_hrv"]:

        return jsonify({
            "error": "Enter your HRV for this session (required each time you open AMUSE).",
            "needs_hrv": True,
        }), 400

    heart_rate = number_or_none(data.get("heart_rate"))
    if heart_rate is None:
        heart_rate = health.get("heart_rate")

    sleep_hours = number_or_none(data.get("sleep_hours"))
    if sleep_hours is None:
        sleep_hours = health.get("sleep_hours")

    hrv = number_or_none(data.get("hrv"))
    if hrv is None:
        hrv = health.get("hrv")

    other_value = amuse.average_health_stress(
        heart_rate,
        hrv,
        sleep_hours,
    )

    stress_value = amuse.blend_stress(pss_value, other_value)
    stress_level = amuse.stress_label_from_value(stress_value)
    start_at = int(data.get("start_at") or 0)
    access_token, _name, _spotify_user = spotify_access_for_user(session["user_id"])
    use_spotify = bool(data.get("use_spotify")) and bool(access_token)
    user_key = f"user-{session['user_id']}"

    if use_spotify:

        top_tracks = amuse.get_user_top_tracks(access_token)
        emotional_state, recommendations, taste = amuse.recommend_songs(
            stress_value,
            stress_level,
            user_key,
            top_tracks,
            access_token,
            number_of_songs=10,
            start_at=start_at,
        )

    else:

        genres = data.get("genres") or []
        artists = [
            name.strip().lower()
            for name in data.get("artists") or []
            if str(name).strip()
        ]
        raw_songs = data.get("songs") or []
        if isinstance(raw_songs, list):
            songs = [name.strip().lower() for name in raw_songs if str(name).strip()]
        else:
            songs = amuse.split_names(raw_songs)

        if not genres and not artists and not songs:

            return jsonify({
                "error": "Pick at least one genre, artist, or song."
            }), 400

        emotional_state, recommendations, taste = amuse.recommend_from_choices(
            stress_value,
            stress_level,
            user_key,
            artists,
            songs,
            set(genres),
            number_of_songs=10,
            start_at=start_at,
        )

    payload = {
        "songs": song_rows(recommendations),
        "stress_level": stress_level,
        "pss_total": pss_total,
        "pss_band": amuse.pss_band(pss_total),
        "target_arousal": round(float(emotional_state["target_arousal"]), 3),
        "target_valence": round(float(emotional_state["target_valence"]), 3),
        "start_at": int(taste.get("start_at", 0)),
        "genres": taste.get("favorite_genres", []),
        "user_id": user_key,
    }

    db.save_recommendation(
        session["user_id"],
        stress_level,
        pss_total,
        payload,
    )

    if not use_spotify:

        db.save_preferences(
            session["user_id"],
            data.get("genres") or [],
            [
                name.strip().lower()
                for name in data.get("artists") or []
                if str(name).strip()
            ],
            amuse.split_names(
                ", ".join(data.get("songs") or [])
                if isinstance(data.get("songs"), list)
                else (data.get("songs") or "")
            ),
            False,
            answers,
        )

    else:

        prefs = db.load_preferences(session["user_id"]) or {
            "genres": [],
            "artists": [],
            "songs": [],
        }

        db.save_preferences(
            session["user_id"],
            prefs.get("genres") or [],
            prefs.get("artists") or [],
            prefs.get("songs") or [],
            True,
            answers,
        )

    return jsonify(payload)


@app.post("/api/playlist")
@login_required
def create_playlist():

    access_token, _name, spotify_user = spotify_access_for_user(session["user_id"])

    if not access_token or not spotify_user:

        return jsonify({
            "error": "Connect Spotify on your computer at http://127.0.0.1:8501 first."
        }), 400

    data = request.get_json(force=True)
    songs = data.get("songs") or []
    track_ids = [
        song.get("track_id")
        for song in songs
        if song.get("track_id")
    ]

    if not track_ids:

        return jsonify({"error": "No Spotify track ids in this list."}), 400

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    stress = data.get("stress_level") or "today"
    name = data.get("name") or f"AMUSE · {stress}"

    create = requests.post(
        f"https://api.spotify.com/v1/users/{spotify_user}/playlists",
        headers=headers,
        json={
            "name": name,
            "description": "Built by AMUSE for your stress level.",
            "public": False,
        },
        timeout=30,
    )

    if create.status_code not in (200, 201):

        return jsonify({
            "error": "Could not create the playlist. "
            "Disconnect Spotify and log in again so playlist access is granted."
        }), 400

    playlist = create.json()
    uris = [f"spotify:track:{track_id}" for track_id in track_ids]

    add = requests.post(
        f"https://api.spotify.com/v1/playlists/{playlist['id']}/tracks",
        headers=headers,
        json={"uris": uris},
        timeout=30,
    )

    if add.status_code not in (200, 201):

        return jsonify({"error": "Playlist was created, but songs failed to add."}), 400

    return jsonify({
        "ok": True,
        "url": playlist.get("external_urls", {}).get("spotify"),
        "name": playlist.get("name"),
    })


@app.post("/api/feedback")
@login_required
def feedback():

    data = request.get_json(force=True)

    db.save_feedback(
        session["user_id"],
        data.get("track_name"),
        data.get("artists"),
        data.get("pre_stress"),
        data.get("post_stress"),
        int(data.get("helpfulness") or 3),
    )

    amuse.save_feedback(
        f"user-{session['user_id']}",
        data.get("track_name"),
        data.get("artists"),
        data.get("pre_stress"),
        data.get("post_stress"),
        int(data.get("helpfulness") or 3),
    )

    return jsonify({"ok": True})


@app.get("/manifest.webmanifest")
def web_manifest():

    return jsonify({
        "name": "AMUSE",
        "short_name": "AMUSE",
        "description": "Adaptive music for unburdening stress and emotions.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f2f7fb",
        "theme_color": "#0a84ff",
        "icons": [
            {
                "src": "/static/logo.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            }
        ],
    }), 200, {"Content-Type": "application/manifest+json"}


if __name__ == "__main__":

    db.init_db()
    address = lan_ip()
    print("Computer (Spotify here):  http://127.0.0.1:8501")
    print(f"Phone (same Wi‑Fi):       http://{address}:8501")
    print("Spotify redirect URI:     ", spotify_redirect_uri())
    print("Add exactly that URI in the Spotify Developer Dashboard.")
    print("Accounts and history are stored in amuse_data.db")
    app.run(host="0.0.0.0", port=8501, debug=False)
