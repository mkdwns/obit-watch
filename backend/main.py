"""
main.py — FastAPI backend for Obit Watch
"""
from contextlib import asynccontextmanager
from typing import Optional
import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database as db
import scheduler


# ── Lifespan ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="Obit Watch API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten this if you expose to the internet
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ────────────────────────────────────────────────────────────────
class WatchCreate(BaseModel):
    first_name: str
    last_name:  str
    city:       Optional[str] = None
    state:      Optional[str] = None
    age_min:    Optional[int] = None
    age_max:    Optional[int] = None
    note:       Optional[str] = None


# ── Watchlist endpoints ────────────────────────────────────────────────────
@app.get("/api/watchlist")
def get_watchlist():
    return db.list_watches()


@app.post("/api/watchlist", status_code=201)
def create_watch(body: WatchCreate):
    try:
        entry = db.add_watch(**body.model_dump())
    except Exception as e:
        print(f"[watchlist] ERROR creating entry: {e}")
        raise HTTPException(500, f"Database error: {e}")
    if not entry:
        print(f"[watchlist] ERROR: add_watch returned None for {body.first_name} {body.last_name}")
        raise HTTPException(500, "Failed to create watchlist entry")
    # Kick off an immediate background search for this new entry
    import threading
    entry_id = entry["id"]
    first    = body.first_name
    last     = body.last_name
    def immediate_scan():
        print(f"[immediate_scan] starting for {first} {last} (watchlist id={entry_id})")
        try:
            print("[immediate_scan] importing scraper...")
            import scraper
            print("[immediate_scan] running search_all...")
            results = scraper.search_all(first, last)
            print(f"[immediate_scan] got {len(results)} results, saving...")
            for r in results:
                print(f"[immediate_scan] result: {r} url={r.obit_url}")
            new = []
            for r in results:
                saved = db.save_match(
                    watchlist_id = entry_id,
                    first_name   = r.first_name,
                    last_name    = r.last_name,
                    birth_year   = r.birth_year,
                    death_year   = r.death_year,
                    location     = r.location,
                    obit_snippet = r.obit_snippet,
                    obit_url     = r.obit_url,
                    source       = r.source,
                )
                if saved:
                    new.append(saved)
                    print(f"[immediate_scan] saved new match: {r}")
                else:
                    print(f"[immediate_scan] duplicate (already saved): {r}")
            if new:
                print(f"[immediate_scan] calling send_alert with {len(new)} match(es): {[m.get('id') for m in new]}")
                import notifier
                notifier.send_alert(new)
            else:
                print("[immediate_scan] no new matches to alert")
        except Exception as e:
            import traceback
            print(f"[immediate_scan] ERROR for {first} {last}: {e}")
            print(traceback.format_exc())
    threading.Thread(target=immediate_scan, daemon=True).start()
    return entry


@app.delete("/api/watchlist/{watch_id}")
def delete_watch(watch_id: int):
    if not db.get_watch(watch_id):
        raise HTTPException(404, "Watch entry not found")
    db.delete_watch(watch_id)
    return {"ok": True}


# ── Match endpoints ────────────────────────────────────────────────────────
@app.get("/api/matches")
def get_matches(dismissed: bool = False):
    return db.list_matches(dismissed=dismissed)


@app.post("/api/matches/{match_id}/dismiss")
def dismiss_match(match_id: int):
    if not db.get_match(match_id):
        raise HTTPException(404, "Match not found")
    db.dismiss_match(match_id)
    return {"ok": True}


# ── Scan endpoints ─────────────────────────────────────────────────────────
@app.post("/api/scan")
def trigger_scan():
    """Manually trigger a scan right now."""
    import threading
    result = {}
    def run():
        nonlocal result
        result = scheduler.run_scan()
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=120)  # wait up to 2 min
    return result


@app.get("/api/scan/log")
def get_scan_log():
    return db.list_scan_log()


# ── Sources endpoints ───────────────────────────────────────────────────────

@app.get("/api/sources")
def get_sources():
    """Return all discovered sources with their enabled/disabled state."""
    import scraper
    sources = scraper.get_all_sources()
    for s in sources:
        val = db.get_setting(f"source:{s['name']}")
        s["enabled"] = (val is None) or (val.lower() != "false")
    return sources


@app.post("/api/sources/{source_name}/toggle")
def toggle_source(source_name: str):
    """Enable or disable a source by name."""
    current = db.get_setting(f"source:{source_name}")
    enabled = (current is None) or (current.lower() != "false")
    db.set_setting(f"source:{source_name}", "false" if enabled else "true")
    return {"name": source_name, "enabled": not enabled}




class SettingsUpdate(BaseModel):
    # All optional — only fields present in the payload are updated
    alert_to:               Optional[str] = None
    alert_from:             Optional[str] = None
    smtp_host:              Optional[str] = None
    smtp_port:              Optional[str] = None
    smtp_user:              Optional[str] = None
    smtp_pass:              Optional[str] = None   # only saved if non-empty & not masked
    notifications_enabled:  Optional[str] = None
    scan_cron_hour:         Optional[str] = None
    scan_cron_minute:       Optional[str] = None


@app.get("/api/settings")
def get_settings():
    """Return all settings. smtp_pass is masked."""
    return db.get_all_settings(include_secrets=False)


@app.post("/api/settings")
def update_settings(body: SettingsUpdate):
    """Persist settings to the database. Takes effect immediately — no restart needed."""
    for key, value in body.model_dump().items():
        if value is None:
            continue
        # Don't overwrite the stored password with the masked placeholder
        if key == "smtp_pass" and set(value) <= {"•"}:
            continue
        db.set_setting(key, value.strip())
    return db.get_all_settings(include_secrets=False)


@app.post("/api/settings/test-email")
def test_email():
    """Send a test notification to the configured alert_to address."""
    import notifier
    fake_match = {
        "first_name":   "Test",
        "last_name":    "Notification",
        "birth_year":   "1940",
        "death_year":   "2025",
        "location":     "Your City, ST",
        "obit_snippet": "This is a test notification from Obit Watch to confirm your email settings are working correctly.",
        "obit_url":     None,
        "watch_note":   "Test entry",
    }
    ok = notifier.send_alert([fake_match])
    if ok:
        return {"ok": True, "message": f"Test email sent to {db.get_setting('alert_to')}"}
    alert_to = db.get_setting("alert_to", "")
    smtp_user = db.get_setting("smtp_user", "")
    smtp_pass = db.get_setting("smtp_pass", "")
    if not alert_to:
        raise HTTPException(400, "No alert_to address configured")
    if not smtp_user or not smtp_pass:
        raise HTTPException(400, "SMTP credentials not configured")
    raise HTTPException(500, "Failed to send test email — check server logs for SMTP error")



@app.get("/api/health")
def health():
    return {"status": "ok", "db": db.DB_PATH}


# ── Test obit server ────────────────────────────────────────────────────────
# A fake obituary store that mimics what a real source returns.
# Enable with TEST_OBITS_ENABLED=true in .env
# The scraper will query /api/test/obits/search automatically when enabled.

import time as _time

_test_obits: dict[int, dict] = {}   # in-memory store
_test_obit_seq = 0


class TestObitCreate(BaseModel):
    first_name:   str
    last_name:    str
    location:     Optional[str] = None
    birth_year:   Optional[str] = None
    death_year:   Optional[str] = None
    age:          Optional[int] = None
    obit_snippet: Optional[str] = None
    published:    Optional[str] = None
    photo_url:    Optional[str] = None


@app.get("/api/test/obits")
def list_test_obits():
    return list(_test_obits.values())


@app.post("/api/test/obits", status_code=201)
def create_test_obit(body: TestObitCreate):
    # Timestamp-based ID so it's unique across container restarts
    obit_id = int(_time.time() * 1000)
    obit = {
        "id":           obit_id,
        **body.model_dump(),
        "obit_url":     f"http://localhost:8000/api/test/obits/{obit_id}",
        "source":       "test-server",
    }
    _test_obits[obit_id] = obit
    return obit


@app.get("/api/test/obits/search")
def search_test_obits(first_name: str = "", last_name: str = ""):
    """Search fake obits by name — called automatically by the scraper."""
    fn, ln = first_name.lower().strip(), last_name.lower().strip()
    results = []
    for obit in _test_obits.values():
        ofn = obit.get("first_name", "").lower()
        oln = obit.get("last_name",  "").lower()
        if ln and ln not in oln:
            continue
        if fn and fn not in ofn and ofn not in fn and (not ofn or ofn[0] != fn[0]):
            continue
        results.append(obit)
    return results


@app.get("/api/test/obits/{obit_id}")
def get_test_obit(obit_id: int):
    """Retrieve a single fake obituary (acts as the 'obit page')."""
    obit = _test_obits.get(obit_id)
    if not obit:
        raise HTTPException(404, "Test obit not found")
    return obit


@app.delete("/api/test/obits/{obit_id}")
def delete_test_obit(obit_id: int):
    """Remove a fake obituary."""
    if obit_id not in _test_obits:
        raise HTTPException(404, "Test obit not found")
    del _test_obits[obit_id]
    return {"ok": True}


@app.delete("/api/test/obits")
def clear_test_obits():
    """Wipe all fake obituaries."""
    _test_obits.clear()
    return {"ok": True, "cleared": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
