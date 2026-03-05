"""
scheduler.py — daily scan job using APScheduler.
Imported and started by main.py at app startup.
"""
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import database as db
import scraper
import notifier

SCAN_HOUR   = int(os.getenv("SCAN_CRON_HOUR",   "6"))
SCAN_MINUTE = int(os.getenv("SCAN_CRON_MINUTE", "0"))

_scheduler = BackgroundScheduler(timezone="America/New_York")


def run_scan():
    """Main scan job — called by scheduler and exposed via API for manual trigger."""
    print("[scheduler] starting scan...")
    log_id = db.start_scan_log()
    watches = db.list_watches(active_only=True)

    if not watches:
        print("[scheduler] watchlist is empty, nothing to scan")
        db.finish_scan_log(log_id, 0, 0)
        return {"scanned": 0, "new_matches": 0}

    errors = []
    new_matches = []

    try:
        hits = scraper.scan_watchlist(watches)

        for watch, match in hits:
            saved = db.save_match(
                watchlist_id = watch["id"],
                first_name   = match.first_name,
                last_name    = match.last_name,
                birth_year   = match.birth_year,
                death_year   = match.death_year,
                location     = match.location,
                obit_snippet = match.obit_snippet,
                obit_url     = match.obit_url,
                source       = match.source,
            )
            if saved:  # None means duplicate — already notified
                new_matches.append(saved)
                print(f"[scheduler] NEW match: {match}")

    except Exception as e:
        errors.append(str(e))
        print(f"[scheduler] scan error: {e}")

    # Send email if there are new matches
    if new_matches:
        notifier.send_alert(new_matches)

    db.finish_scan_log(
        log_id,
        names_scanned = len(watches),
        matches_found = len(new_matches),
        errors        = "; ".join(errors) if errors else None,
    )

    print(f"[scheduler] scan complete — {len(watches)} names, {len(new_matches)} new matches")
    return {"scanned": len(watches), "new_matches": len(new_matches)}


def start():
    """Start the background scheduler."""
    _scheduler.add_job(
        run_scan,
        trigger=CronTrigger(hour=SCAN_HOUR, minute=SCAN_MINUTE),
        id="daily_scan",
        replace_existing=True,
    )
    _scheduler.start()
    print(f"[scheduler] started — daily scan at {SCAN_HOUR:02d}:{SCAN_MINUTE:02d}")


def stop():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[scheduler] stopped")
