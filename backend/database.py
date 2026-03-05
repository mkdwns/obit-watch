"""
database.py — SQLite database layer for Obit Watch
"""
import sqlite3
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "/app/data/obit_watch.db")


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name  TEXT NOT NULL,
                last_name   TEXT NOT NULL,
                city        TEXT,
                state       TEXT,
                age_min     INTEGER,
                age_max     INTEGER,
                note        TEXT,
                added_at    TEXT NOT NULL,
                active      INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS matches (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                watchlist_id    INTEGER NOT NULL REFERENCES watchlist(id),
                first_name      TEXT NOT NULL,
                last_name       TEXT NOT NULL,
                birth_year      TEXT,
                death_year      TEXT,
                location        TEXT,
                obit_snippet    TEXT,
                obit_url        TEXT,
                source          TEXT,
                found_at        TEXT NOT NULL,
                dismissed       INTEGER NOT NULL DEFAULT 0,
                UNIQUE(watchlist_id, obit_url)
            );

            CREATE TABLE IF NOT EXISTS scan_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at  TEXT NOT NULL,
                finished_at TEXT,
                names_scanned   INTEGER DEFAULT 0,
                matches_found   INTEGER DEFAULT 0,
                errors      TEXT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
    print(f"[db] initialized at {DB_PATH}")


# ── Watchlist ──────────────────────────────────────────────────────────────

def add_watch(first_name: str, last_name: str, city: str = None,
              state: str = None, age_min: int = None, age_max: int = None,
              note: str = None) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO watchlist
               (first_name, last_name, city, state, age_min, age_max, note, added_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (first_name.strip(), last_name.strip(), city, state,
             age_min, age_max, note, datetime.utcnow().isoformat())
        )
        row_id = cur.lastrowid
        # Read back within the same connection/transaction so it's always visible
        row = conn.execute(
            "SELECT * FROM watchlist WHERE id = ?", (row_id,)
        ).fetchone()
        return dict(row) if row else None


def get_watch(watch_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM watchlist WHERE id = ?", (watch_id,)
        ).fetchone()
        return dict(row) if row else None


def list_watches(active_only: bool = True) -> list[dict]:
    with get_conn() as conn:
        q = "SELECT * FROM watchlist"
        if active_only:
            q += " WHERE active = 1"
        q += " ORDER BY added_at DESC"
        return [dict(r) for r in conn.execute(q).fetchall()]


def delete_watch(watch_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE watchlist SET active = 0 WHERE id = ?", (watch_id,))


# ── Matches ────────────────────────────────────────────────────────────────

def save_match(watchlist_id: int, first_name: str, last_name: str,
               birth_year: str = None, death_year: str = None,
               location: str = None, obit_snippet: str = None,
               obit_url: str = None, source: str = "legacy.com") -> Optional[dict]:
    """Insert a match; returns None if it already exists (dedup by URL)."""
    with get_conn() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO matches
                   (watchlist_id, first_name, last_name, birth_year, death_year,
                    location, obit_snippet, obit_url, source, found_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (watchlist_id, first_name, last_name, birth_year, death_year,
                 location, obit_snippet, obit_url, source,
                 datetime.utcnow().isoformat())
            )
            row = conn.execute(
                "SELECT * FROM matches WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.IntegrityError:
            return None  # duplicate


def get_match(match_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM matches WHERE id = ?", (match_id,)
        ).fetchone()
        return dict(row) if row else None


def list_matches(dismissed: bool = False, limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT m.*, w.note as watch_note,
                      w.city as watch_city, w.state as watch_state
               FROM matches m
               JOIN watchlist w ON w.id = m.watchlist_id
               WHERE m.dismissed = ?
               ORDER BY m.found_at DESC
               LIMIT ?""",
            (1 if dismissed else 0, limit)
        ).fetchall()
        matches = [dict(r) for r in rows]

    # Sort: location matches (city+state) first, then city-only, then rest.
    # Within each tier, preserve recency (already ordered by found_at DESC).
    def location_score(m):
        location = (m.get("location") or "").lower()
        watch_city  = (m.get("watch_city")  or "").lower().strip()
        watch_state = (m.get("watch_state") or "").lower().strip()
        city_match  = bool(watch_city  and watch_city  in location)
        state_match = bool(watch_state and watch_state in location)
        if city_match and state_match:
            return 0
        if city_match or state_match:
            return 1
        return 2

    matches.sort(key=location_score)
    return matches


def dismiss_match(match_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE matches SET dismissed = 1 WHERE id = ?", (match_id,))


# ── Scan log ───────────────────────────────────────────────────────────────

def start_scan_log() -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO scan_log (started_at) VALUES (?)",
            (datetime.utcnow().isoformat(),)
        )
        return cur.lastrowid


def finish_scan_log(log_id: int, names_scanned: int,
                    matches_found: int, errors: str = None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE scan_log
               SET finished_at=?, names_scanned=?, matches_found=?, errors=?
               WHERE id=?""",
            (datetime.utcnow().isoformat(), names_scanned, matches_found,
             errors, log_id)
        )


def list_scan_log(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scan_log ORDER BY started_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Settings ───────────────────────────────────────────────────────────────

# Keys we expose via the API (whitelist — never expose SMTP_PASS etc.)
SETTINGS_KEYS = {
    "alert_to",        # notification recipient(s), comma-separated
    "alert_from",      # sender address
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "smtp_pass",       # stored in DB, never echoed back to the UI
    "notifications_enabled",   # "true" / "false"
    "scan_cron_hour",
    "scan_cron_minute",
}

# Keys that must never be returned to the frontend
_SECRET_KEYS = {"smtp_pass"}


def get_setting(key: str, default: str = None) -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row and row["value"]:  # treat empty string as unset
            return row["value"]
        # Fall back to environment variable (so existing .env still works)
        env_key = key.upper()
        return os.getenv(env_key, default)


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )


def get_all_settings(include_secrets: bool = False) -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    stored = {r["key"]: r["value"] for r in rows}
    # Merge env vars as defaults for any key not yet in DB
    result = {}
    for key in SETTINGS_KEYS:
        if key in _SECRET_KEYS and not include_secrets:
            # Return a masked placeholder if a value exists, else empty
            val = stored.get(key) or os.getenv(key.upper(), "")
            result[key] = "••••••••" if val else ""
        else:
            result[key] = stored.get(key) or os.getenv(key.upper(), "")
    return result
