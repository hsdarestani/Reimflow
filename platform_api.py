"""Persistent community API for Reimflow. Standard library only; no payment integration.

The existing rhyme engine remains independent. Accounts and uploads live in the
already mounted SQLite/data volume. Never trust client-side points or roles.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from email.parser import BytesParser
from email.policy import default as email_policy
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlparse

DATABASE = os.getenv("REIMFLOW_DB", "/var/lib/reimflow/reimflow.sqlite3")
MEDIA_DIR = Path(os.getenv("REIMFLOW_MEDIA_DIR", str(Path(DATABASE).parent / "media")))
MAX_AUDIO = 12 * 1024 * 1024
MAX_BODY = MAX_AUDIO + 1024 * 1024
SESSION_AGE = 30 * 24 * 3600
USERNAME = re.compile(r"^[a-z0-9_.]{3,24}$")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
limiter = {}
limiter_lock = threading.Lock()


@contextmanager
def connection():
    Path(DATABASE).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DATABASE, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=15000")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def initialize():
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    with connection() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS rf_users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            bio TEXT NOT NULL DEFAULT '',
            persona TEXT NOT NULL DEFAULT 'rapper',
            role TEXT NOT NULL DEFAULT 'member',
            password_hash TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rf_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES rf_users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rf_submissions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES rf_users(id) ON DELETE CASCADE,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            category TEXT NOT NULL,
            syllables TEXT NOT NULL,
            pronunciation TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rf_reviews (
            submission_id INTEGER NOT NULL REFERENCES rf_submissions(id) ON DELETE CASCADE,
            reviewer_id INTEGER REFERENCES rf_users(id) ON DELETE SET NULL,
            decision TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY(submission_id, reviewer_id)
        );
        CREATE TABLE IF NOT EXISTS rf_beats (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES rf_users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            bpm INTEGER NOT NULL,
            license TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            mime TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            hidden INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rf_favorites (
            user_id INTEGER NOT NULL REFERENCES rf_users(id) ON DELETE CASCADE,
            word TEXT NOT NULL,
            PRIMARY KEY(user_id, word)
        );
        CREATE TABLE IF NOT EXISTS rf_scores (
            user_id INTEGER NOT NULL REFERENCES rf_users(id) ON DELETE CASCADE,
            bpm INTEGER NOT NULL,
            mode TEXT NOT NULL,
            best INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY(user_id,bpm,mode)
        );
        CREATE TABLE IF NOT EXISTS rf_reports (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES rf_users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL, content_id INTEGER NOT NULL,
            reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rf_blocks (
            blocker_id INTEGER NOT NULL REFERENCES rf_users(id) ON DELETE CASCADE,
            blocked_id INTEGER NOT NULL REFERENCES rf_users(id) ON DELETE CASCADE,
            PRIMARY KEY(blocker_id,blocked_id)
        );
        CREATE INDEX IF NOT EXISTS rf_submissions_created ON rf_submissions(created_at DESC);
        CREATE INDEX IF NOT EXISTS rf_beats_created ON rf_beats(created_at DESC);
        """)


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf8"), salt, 600000)
    return salt.hex() + ":" + hashed.hex()


def verify_password(password, saved):
    try:
        salt, expected = saved.split(":", 1)
        got = password_hash(password, bytes.fromhex(salt)).split(":", 1)[1]
        return hmac.compare_digest(got, expected)
    except (ValueError, TypeError):
        return False


def request_allowed(h, kind, limit, window):
    ip = h.headers.get("X-Real-IP") or h.client_address[0]
    key = (ip, kind)
    now = time.time()
    with limiter_lock:
        attempts = [v for v in limiter.get(key, []) if now-v < window]
        if len(attempts) >= limit:
            limiter[key] = attempts
            return False
        attempts.append(now)
        limiter[key] = attempts
        if len(limiter) > 20000:
            limiter.clear()
        return True


def respond(h, status, payload, cookie=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf8")
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store")
    h.send_header("X-Content-Type-Options", "nosniff")
    if cookie:
        h.send_header("Set-Cookie", cookie)
    h.end_headers()
    h.wfile.write(body)


def cookie_header(token, max_age=SESSION_AGE):
    return ("rf_session=" + token + "; Path=/api/platform; HttpOnly; Secure; "
            "SameSite=Lax; Max-Age=" + str(max_age))


def current_user(h):
    try:
        cookie = SimpleCookie()
        cookie.load(h.headers.get("Cookie", ""))
        token = cookie["rf_session"].value
        if len(token) != 64:
            return None
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        with connection() as c:
            row = c.execute("""SELECT u.id,u.username,u.email,u.display_name,u.bio,
                u.persona,u.role,u.points FROM rf_sessions s
                JOIN rf_users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.expires_at>?""",
                (token_hash, int(time.time()))).fetchone()
        return dict(row) if row else None
    except (KeyError, ValueError):
        return None


def require_user(h):
    user = current_user(h)
    if not user:
        respond(h, 401, {"error": "AUTH_REQUIRED", "message": "Bitte zuerst anmelden."})
    return user


def read_json(h):
    try:
        length = int(h.headers.get("Content-Length", "0"))
    except ValueError:
        raise ValueError("Ungültige Daten.")
    if length < 2 or length > 32768:
        raise ValueError("Ungültige Eingabegröße.")
    data = json.loads(h.rfile.read(length).decode("utf8"))
    if not isinstance(data, dict):
        raise ValueError("Ungültiges JSON Objekt.")
    return data


def new_session(user_id):
    token = secrets.token_hex(32)
    with connection() as c:
        c.execute("DELETE FROM rf_sessions WHERE expires_at<?", (int(time.time()),))
        c.execute("INSERT INTO rf_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                  (hashlib.sha256(token.encode()).hexdigest(), user_id,
                   int(time.time()) + SESSION_AGE))
    return token


def trim(value, cap):
    return str(value if value is not None else "").strip()[:cap]


def view_user(user):
    if not user:
        return None
    return {k: user[k] for k in
            ("id", "username", "display_name", "bio", "persona", "role", "points")}


def bootstrap(h):
    user = current_user(h)
    with connection() as c:
        uid = user["id"] if user else -1
        feed = [dict(row) for row in c.execute("""
          SELECT s.id,s.source,s.target,s.category,s.syllables,s.pronunciation,
                 s.status,s.created_at,u.username,u.display_name,u.id AS author_id
          FROM rf_submissions s JOIN rf_users u ON u.id=s.user_id
          WHERE (s.status='accepted' OR s.user_id=?)
            AND NOT EXISTS (SELECT 1 FROM rf_blocks bl WHERE bl.blocker_id=? AND bl.blocked_id=s.user_id)
            ORDER BY s.created_at DESC LIMIT 60""", (uid,uid))]
        beats = [dict(row) for row in c.execute("""
          SELECT b.id,b.title,b.kind,b.bpm,b.license,b.bytes,b.created_at,b.hidden,
                 u.username,u.display_name,u.id AS author_id
          FROM rf_beats b JOIN rf_users u ON u.id=b.user_id
          WHERE (b.hidden=0 OR b.user_id=?)
           AND NOT EXISTS (SELECT 1 FROM rf_blocks bl WHERE bl.blocker_id=? AND bl.blocked_id=b.user_id)
           ORDER BY b.created_at DESC LIMIT 60""", (uid,uid))]
        leaders = [dict(row) for row in c.execute("""
          SELECT id,username,display_name,points FROM rf_users
          WHERE points>0 AND id NOT IN (SELECT blocked_id FROM rf_blocks WHERE blocker_id=?)
           ORDER BY points DESC,id ASC LIMIT 10""", (uid,))]
        favorites, scores, mine, queue, blocked, reports, pending_beats, members = [], [], [], [], [], [], [], []
        if user:
            uid = user["id"]
            favorites = [r["word"] for r in c.execute(
                "SELECT word FROM rf_favorites WHERE user_id=? LIMIT 400", (uid,))]
            scores = [dict(r) for r in c.execute(
                "SELECT bpm,mode,best FROM rf_scores WHERE user_id=?", (uid,))]
            mine = [dict(r) for r in c.execute(
                "SELECT id,source,target,status FROM rf_submissions WHERE user_id=? ORDER BY id DESC LIMIT 10",(uid,))]
            blocked = [dict(r) for r in c.execute("""SELECT u.id,u.username,u.display_name FROM rf_blocks b
                JOIN rf_users u ON u.id=b.blocked_id WHERE b.blocker_id=?""",(uid,))]
            if user["role"] == "admin":
                reports = [dict(r) for r in c.execute("""SELECT r.id,r.kind,r.content_id,r.reason,r.status,u.username
                    FROM rf_reports r JOIN rf_users u ON u.id=r.user_id WHERE r.status='open' ORDER BY r.id DESC LIMIT 100""")]
                pending_beats = [dict(r) for r in c.execute("""SELECT b.id,b.title,b.kind,b.license,b.bpm,
                    u.username,u.display_name FROM rf_beats b JOIN rf_users u ON u.id=b.user_id
                    WHERE b.hidden=1 ORDER BY b.id DESC LIMIT 100""")]
                members = [dict(r) for r in c.execute("""SELECT id,username,display_name,role FROM rf_users
                    ORDER BY id DESC LIMIT 100""")]
            if user["role"] in ("tester", "admin"):
                queue = [dict(r) for r in c.execute("""
                   SELECT s.id,s.source,s.target,s.category,s.syllables,
                     s.pronunciation,s.created_at,u.username,u.display_name,u.id AS author_id
                   FROM rf_submissions s JOIN rf_users u ON u.id=s.user_id
                   WHERE s.status='pending' ORDER BY s.created_at LIMIT 60""")]
    respond(h, 200, {"ok": True, "user": view_user(user), "feed": feed,
                     "queue": queue, "beats": beats, "leaders": leaders,
                     "favorites": favorites, "scores": scores, "mine": mine,
                     "blocked":blocked, "reports":reports, "pending_beats":pending_beats,
                     "members":members, "payments_enabled": False})


def read_audio(h):
    typ = h.headers.get("Content-Type", "")
    if not typ.startswith("multipart/form-data;") or "boundary=" not in typ:
        raise ValueError("Audio Datei erforderlich.")
    try:
        size = int(h.headers.get("Content-Length", "0"))
    except ValueError:
        raise ValueError("Ungültige Dateigröße.")
    if size < 100 or size > MAX_BODY:
        raise ValueError("Audio maximal 12 MB.")
    msg = BytesParser(policy=email_policy).parsebytes(
        ("Content-Type: " + typ + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + h.rfile.read(size))
    if not msg.is_multipart():
        raise ValueError("Ungültiger Dateiupload.")
    fields = {}
    sound = None
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        raw = part.get_payload(decode=True) or b""
        if name == "audio":
            sound = raw
        elif len(raw) < 1024:
            fields[name] = raw.decode("utf8", errors="replace").strip()
    if not sound or len(sound) > MAX_AUDIO:
        raise ValueError("Audio maximal 12 MB.")
    if sound.startswith(b"ID3") or sound[:1] == b"\xff" and sound[1:2] in (b"\xfb", b"\xf3", b"\xf2"):
        mime, suffix = "audio/mpeg", ".mp3"
    elif sound[:4] == b"RIFF" and sound[8:12] == b"WAVE":
        mime, suffix = "audio/wav", ".wav"
    elif sound[:4] == b"OggS":
        mime, suffix = "audio/ogg", ".ogg"
    elif sound[:4] == b"fLaC":
        mime, suffix = "audio/flac", ".flac"
    elif sound[4:8] == b"ftyp":
        mime, suffix = "audio/mp4", ".m4a"
    else:
        raise ValueError("Erlaubte Formate: MP3, WAV, OGG, FLAC, M4A.")
    return fields, sound, mime, suffix


def send_audio(h, beat_id):
    actor = current_user(h)
    with connection() as c:
        beat = c.execute("""SELECT stored_name,mime,bytes FROM rf_beats
            WHERE id=? AND (hidden=0 OR user_id=? OR ?='admin')""",
                         (beat_id, actor["id"] if actor else -1, actor["role"] if actor else "")).fetchone()
    if not beat:
        respond(h, 404, {"error": "NOT_FOUND"})
        return
    file = MEDIA_DIR / beat["stored_name"]
    if not file.is_file():
        respond(h, 404, {"error": "MISSING_AUDIO"})
        return
    size = file.stat().st_size
    start, end = 0, size - 1
    range_header = h.headers.get("Range", "")
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if not match or not match.group(1):
            h.send_response(416)
            h.send_header("Content-Range", "bytes */" + str(size))
            h.send_header("Content-Length", "0")
            h.end_headers()
            return
        start = int(match.group(1))
        end = min(int(match.group(2)), end) if match.group(2) else end
        if start > end or start >= size:
            h.send_response(416)
            h.send_header("Content-Range", "bytes */" + str(size))
            h.send_header("Content-Length", "0")
            h.end_headers()
            return
    h.send_response(206 if range_header else 200)
    h.send_header("Content-Type", beat["mime"])
    h.send_header("Content-Length", str(end - start + 1))
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Cache-Control", "public, max-age=3600")
    h.send_header("X-Content-Type-Options", "nosniff")
    if range_header:
        h.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    h.end_headers()
    try:
        with file.open("rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                h.wfile.write(chunk)
                remaining -= len(chunk)
    except (BrokenPipeError, ConnectionResetError):
        pass


def handle(h):
    path = urlparse(h.path).path
    if not path.startswith("/api/platform/"):
        return False
    if h.command == "GET":
        if path == "/api/platform/bootstrap":
            bootstrap(h)
        elif path == "/api/platform/export":
            user = require_user(h)
            if user:
                with connection() as c:
                    personal = dict(c.execute("SELECT username,email,display_name,bio,persona,points,created_at FROM rf_users WHERE id=?", (user["id"],)).fetchone())
                    personal["submissions"]=[dict(row) for row in c.execute("SELECT source,target,category,syllables,pronunciation,status,created_at FROM rf_submissions WHERE user_id=?", (user["id"],))]
                    personal["beats"]=[dict(row) for row in c.execute("SELECT id,title,kind,bpm,license,created_at FROM rf_beats WHERE user_id=?", (user["id"],))]
                    personal["favorites"]=[row["word"] for row in c.execute("SELECT word FROM rf_favorites WHERE user_id=?", (user["id"],))]
                    personal["scores"]=[dict(row) for row in c.execute("SELECT bpm,mode,best FROM rf_scores WHERE user_id=?", (user["id"],))]
                respond(h,200,{"ok":True,"export":personal})
        elif re.fullmatch(r"/api/platform/media/\d+", path):
            send_audio(h, int(path.rsplit("/", 1)[1]))
        else:
            respond(h, 404, {"error": "NOT_FOUND"})
        return True
    if h.command != "POST":
        respond(h, 405, {"error": "METHOD_NOT_ALLOWED"})
        return True
    # Mandatory non-simple header prevents cookie-based cross-site form CSRF.
    # CORS is intentionally not enabled.
    if h.headers.get("X-Reimflow-Client") != "1":
        respond(h, 403, {"error": "CLIENT_HEADER_REQUIRED"})
        return True
    origin = h.headers.get("Origin", "")
    host = h.headers.get("Host", "")
    if origin and origin != "https://" + host and not (
        os.getenv("REIMFLOW_DEV_ORIGIN", "") and
        origin == os.getenv("REIMFLOW_DEV_ORIGIN", "")):
        respond(h, 403, {"error": "ORIGIN_REJECTED"})
        return True
    kind = path.rsplit("/", 1)[-1]
    if not request_allowed(h, "platform", 80, 60):
        respond(h, 429, {"error": "RATE_LIMIT"})
        return True
    try:
        if kind == "register":
            if not request_allowed(h, "register", 5, 3600):
                respond(h, 429, {"error": "TOO_MANY_SIGNUPS"})
                return True
            data = read_json(h)
            username = trim(data.get("username"), 24).lower()
            email = trim(data.get("email"), 254).lower()
            password = str(data.get("password") or "")
            persona = data.get("persona", "rapper")
            if (not USERNAME.fullmatch(username) or not EMAIL.fullmatch(email)
                    or len(password) < 12 or len(password) > 128
                    or persona not in ("rapper", "producer")):
                respond(h, 400, {"error": "INVALID_REGISTRATION",
                                 "message": "Nutzername, E-Mail oder Passwort ungültig (mindestens 12 Zeichen)."})
                return True
            hashed = password_hash(password)
            with connection() as c:
                try:
                    cursor = c.execute("""INSERT INTO rf_users
                        (username,email,display_name,persona,password_hash,created_at)
                        VALUES(?,?,?,?,?,?)""",
                        (username, email, username, persona, hashed, int(time.time())))
                    uid = cursor.lastrowid
                except sqlite3.IntegrityError:
                    respond(h, 409, {"error": "ACCOUNT_EXISTS",
                                     "message": "Nutzername oder E-Mail ist bereits vergeben."})
                    return True
            respond(h, 201, {"ok": True}, cookie_header(new_session(uid)))
            return True
        if kind == "login":
            if not request_allowed(h, "login", 15, 900):
                respond(h, 429, {"error": "LOGIN_RATE_LIMIT"})
                return True
            data = read_json(h)
            identity = trim(data.get("identity"), 254).lower()
            password = str(data.get("password") or "")
            with connection() as c:
                row = c.execute("SELECT id,password_hash FROM rf_users WHERE username=? OR email=?",
                                (identity, identity)).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                respond(h, 401, {"error": "BAD_CREDENTIALS",
                                 "message": "Anmeldedaten nicht korrekt."})
                return True
            respond(h, 200, {"ok": True}, cookie_header(new_session(row["id"])))
            return True
        if kind == "logout":
            try:
                cookie = SimpleCookie()
                cookie.load(h.headers.get("Cookie", ""))
                token = cookie["rf_session"].value
                with connection() as c:
                    c.execute("DELETE FROM rf_sessions WHERE token_hash=?",
                              (hashlib.sha256(token.encode()).hexdigest(),))
            except (KeyError, ValueError):
                pass
            respond(h, 200, {"ok": True}, cookie_header("", 0))
            return True
        user = require_user(h)
        if not user:
            return True
        uid = user["id"]
        if kind == "profile":
            data = read_json(h)
            name = trim(data.get("display_name"), 48)
            bio = trim(data.get("bio"), 500)
            persona = data.get("persona", user["persona"])
            if not name or persona not in ("rapper", "producer"):
                raise ValueError("Profilangaben unvollständig.")
            with connection() as c:
                c.execute("UPDATE rf_users SET display_name=?,bio=?,persona=? WHERE id=?",
                          (name, bio, persona, uid))
            respond(h, 200, {"ok": True})
        elif kind == "password":
            data = read_json(h)
            new = str(data.get("new_password") or "")
            if len(new) < 12 or len(new) > 128:
                raise ValueError("Passwort muss mindestens 12 Zeichen haben.")
            with connection() as c:
                old = c.execute("SELECT password_hash FROM rf_users WHERE id=?", (uid,)).fetchone()
                if not old or not verify_password(str(data.get("current_password") or ""), old[0]):
                    respond(h, 403, {"error": "WRONG_PASSWORD"})
                    return True
                c.execute("UPDATE rf_users SET password_hash=? WHERE id=?", (password_hash(new), uid))
                c.execute("DELETE FROM rf_sessions WHERE user_id=?", (uid,))
            respond(h, 200, {"ok": True}, cookie_header("", 0))
        elif kind == "delete-account":
            data = read_json(h)
            with connection() as c:
                saved = c.execute("SELECT password_hash FROM rf_users WHERE id=?", (uid,)).fetchone()
                if not saved or not verify_password(str(data.get("password") or ""), saved[0]):
                    respond(h, 403, {"error": "WRONG_PASSWORD"})
                    return True
                files = [r[0] for r in c.execute("SELECT stored_name FROM rf_beats WHERE user_id=?", (uid,))]
                c.execute("DELETE FROM rf_users WHERE id=?", (uid,))
            for name in files:
                (MEDIA_DIR / name).unlink(missing_ok=True)
            respond(h, 200, {"ok": True}, cookie_header("", 0))
        elif kind == "submissions":
            if not request_allowed(h, "submission-" + str(uid), 15, 3600):
                respond(h, 429, {"error": "SUBMISSION_RATE_LIMIT"})
                return True
            d = read_json(h)
            source, target = trim(d.get("source"), 90), trim(d.get("target"), 90)
            category = d.get("category")
            syllables = str(d.get("syllables"))
            pronunciation = trim(d.get("pronunciation"), 90)
            if (len(source) < 2 or len(target) < 2 or
                category not in ("Nomen", "Adjektiv", "Verb", "Umgangssprache", "Sonstiges") or
                syllables not in ("1", "2", "3", "4+") or source.casefold() == target.casefold()):
                raise ValueError("Bitte gültige Reimwörter und Filter angeben.")
            with connection() as c:
                c.execute("""INSERT INTO rf_submissions
                    (user_id,source,target,category,syllables,pronunciation,created_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (uid, source, target, category, syllables, pronunciation, int(time.time())))
            respond(h, 201, {"ok": True, "message": "Beitrag wartet auf Prüfung."})
        elif kind == "review":
            if user["role"] not in ("tester", "admin"):
                respond(h, 403, {"error": "TESTER_REQUIRED"})
                return True
            d = read_json(h)
            sid, decision = int(d.get("id", 0)), d.get("decision")
            if decision not in ("accepted", "rejected"):
                raise ValueError("Ungültiges Prüfergebnis.")
            with connection() as c:
                row = c.execute("SELECT user_id,status FROM rf_submissions WHERE id=?", (sid,)).fetchone()
                if not row:
                    respond(h, 404, {"error": "NOT_FOUND"})
                    return True
                if row["user_id"] == uid:
                    respond(h, 403, {"error": "SELF_REVIEW_FORBIDDEN"})
                    return True
                changed = c.execute("UPDATE rf_submissions SET status=? WHERE id=? AND status='pending'",
                                    (decision, sid)).rowcount
                if not changed:
                    respond(h, 409, {"error": "ALREADY_REVIEWED"})
                    return True
                c.execute("INSERT INTO rf_reviews(submission_id,reviewer_id,decision,created_at) VALUES(?,?,?,?)",
                          (sid,uid,decision,int(time.time())))
                c.execute("UPDATE rf_users SET points=points+? WHERE id=?", (10 if decision=="accepted" else 0,row["user_id"]))
                c.execute("UPDATE rf_users SET points=points+2 WHERE id=?", (uid,))
            respond(h, 200, {"ok": True})
        elif kind == "favorites":
            d = read_json(h)
            word = trim(d.get("word"), 90)
            if not word:
                raise ValueError("Wort fehlt.")
            with connection() as c:
                if d.get("remove"):
                    c.execute("DELETE FROM rf_favorites WHERE user_id=? AND word=?", (uid,word))
                else:
                    c.execute("INSERT OR IGNORE INTO rf_favorites(user_id,word) VALUES(?,?)", (uid,word))
            respond(h, 200, {"ok": True})
        elif kind == "scores":
            d = read_json(h)
            score, bpm, mode = int(d.get("score", -1)), int(d.get("bpm", 0)), d.get("mode")
            if not 0 <= score <= 100 or bpm not in (80,92,110,140) or mode not in ("tap","mic"):
                raise ValueError("Ungültiges Spielergebnis.")
            # Client results are unverified. Store only personal best, not competitive points.
            with connection() as c:
                c.execute("""INSERT INTO rf_scores(user_id,bpm,mode,best,updated_at)
                    VALUES(?,?,?,?,?) ON CONFLICT(user_id,bpm,mode)
                    DO UPDATE SET best=MAX(best,excluded.best),updated_at=excluded.updated_at""",
                    (uid,bpm,mode,score,int(time.time())))
            respond(h, 200, {"ok": True})
        elif kind == "beats":
            if not request_allowed(h, "uploads-" + str(uid), 8, 3600):
                respond(h, 429, {"error": "UPLOAD_LIMIT"})
                return True
            fields, audio, mime, ext = read_audio(h)
            title = trim(fields.get("title"), 80)
            kind_value = fields.get("kind")
            license_value = fields.get("license")
            try:
                bpm = int(fields.get("bpm", "0"))
            except ValueError:
                bpm = 0
            if (not title or kind_value not in ("Beat","Sample")
                    or license_value not in ("Free Use","Non Commercial","Commercial License")
                    or not 40 <= bpm <= 240 or fields.get("rights") != "yes"):
                raise ValueError("Titel, BPM, Lizenz und Rechtebestätigung sind erforderlich.")
            stored = secrets.token_hex(24) + ext
            file = MEDIA_DIR / stored
            try:
                with file.open("xb") as stream:
                    stream.write(audio)
                with connection() as c:
                    c.execute("""INSERT INTO rf_beats
                        (user_id,title,kind,bpm,license,stored_name,mime,bytes,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?)""",
                        (uid,title,kind_value,bpm,license_value,stored,mime,len(audio),int(time.time())))
                    c.execute("UPDATE rf_beats SET hidden=1 WHERE stored_name=?", (stored,))
            except Exception:
                file.unlink(missing_ok=True)
                raise
            respond(h, 201, {"ok": True})
        elif kind == "delete-beat":
            d = read_json(h)
            bid = int(d.get("id", 0))
            with connection() as c:
                row = c.execute("SELECT user_id,stored_name FROM rf_beats WHERE id=?", (bid,)).fetchone()
                if not row or (row["user_id"] != uid and user["role"] != "admin"):
                    respond(h, 404, {"error": "NOT_FOUND"})
                    return True
                c.execute("DELETE FROM rf_beats WHERE id=?", (bid,))
            (MEDIA_DIR / row["stored_name"]).unlink(missing_ok=True)
            respond(h, 200, {"ok": True})
        elif kind == "block-user":
            d = read_json(h)
            target = int(d.get("user_id",0))
            if target <= 0 or target == uid:
                raise ValueError("Ungültiges Konto.")
            with connection() as c:
                found = c.execute("SELECT 1 FROM rf_users WHERE id=?", (target,)).fetchone()
                if not found:
                    respond(h,404,{"error":"NOT_FOUND"})
                    return True
                if d.get("remove"):
                    c.execute("DELETE FROM rf_blocks WHERE blocker_id=? AND blocked_id=?", (uid,target))
                else:
                    c.execute("INSERT OR IGNORE INTO rf_blocks(blocker_id,blocked_id) VALUES(?,?)",(uid,target))
            respond(h,200,{"ok":True})
        elif kind == "set-tester":
            if user["role"] != "admin":
                respond(h,403,{"error":"ADMIN_REQUIRED"})
                return True
            d=read_json(h)
            target=int(d.get("user_id",0))
            role=d.get("role")
            if role not in ("member","tester") or target<=0 or target==uid:
                raise ValueError("Ungültige Rollenzuweisung.")
            with connection() as c:
                changed=c.execute("UPDATE rf_users SET role=? WHERE id=? AND role IN ('member','tester')",(role,target)).rowcount
            if not changed:
                respond(h,404,{"error":"NOT_FOUND"})
                return True
            respond(h,200,{"ok":True})
        elif kind == "report":
            d = read_json(h)
            category, reason = d.get("kind"), trim(d.get("reason"), 500)
            object_id = int(d.get("id", 0))
            if category not in ("beat", "submission") or not reason or object_id <= 0:
                raise ValueError("Meldung unvollständig.")
            with connection() as c:
                c.execute("""INSERT INTO rf_reports(user_id,kind,content_id,reason,created_at)
                             VALUES(?,?,?,?,?)""", (uid,category,object_id,reason,int(time.time())))
            respond(h, 201, {"ok": True})
        elif kind == "moderate":
            if user["role"] != "admin":
                respond(h, 403, {"error": "ADMIN_REQUIRED"})
                return True
            d = read_json(h)
            category, object_id = d.get("kind"), int(d.get("id", 0))
            with connection() as c:
                decision=d.get("decision","hide")
                if decision not in ("hide","approve"):
                    raise ValueError("Ungültige Moderation.")
                if category == "beat":
                    c.execute("UPDATE rf_beats SET hidden=? WHERE id=?", (0 if decision=="approve" else 1,object_id))
                elif category == "submission":
                    c.execute("UPDATE rf_submissions SET status=? WHERE id=?", ("accepted" if decision=="approve" else "rejected",object_id))
                else:
                    raise ValueError("Unbekannter Inhalt.")
                c.execute("UPDATE rf_reports SET status='resolved' WHERE kind=? AND content_id=?", (category,object_id))
            respond(h, 200, {"ok": True})
        else:
            respond(h, 404, {"error": "NOT_FOUND"})
    except (ValueError, TypeError, json.JSONDecodeError):
        respond(h, 400, {"error": "BAD_INPUT", "message": "Bitte Eingaben prüfen."})
    except sqlite3.Error:
        respond(h, 503, {"error": "DB_UNAVAILABLE", "message": "Datenbank vorübergehend nicht erreichbar."})
    except Exception as exc:
        print("platform error:", type(exc).__name__, flush=True)
        respond(h, 500, {"error": "INTERNAL_ERROR"})
    return True


if __name__ == "__main__":
    initialize()
    print("Platform database is ready:", DATABASE)
