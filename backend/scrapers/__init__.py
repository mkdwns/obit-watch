"""
scrapers/__init__.py — Master scraper loader.

Auto-discovers all source modules in this package. Each module must expose:
  SOURCE_NAME:  str   — unique key used in DB settings, e.g. "legacy.com"
  SOURCE_LABEL: str   — display label for the UI, e.g. "Legacy.com"
  search(first_name, last_name, session) -> list[ObitMatch]

To add a new source: drop a new .py file in this directory with those three
things. Nothing else needs to change.

Source enable/disable state is stored in the settings table as:
  key:   "source:<SOURCE_NAME>"
  value: "true" | "false"
Defaults to enabled if no setting exists.
"""
import importlib
import pkgutil
import time
import os

from curl_cffi import requests as cf_requests

from .base import ObitMatch, make_session

SCRAPE_DELAY = float(os.getenv("SCRAPE_DELAY", "3"))

# Modules to skip when auto-discovering (not scrapers)
_SKIP = {"base"}


def _load_all_modules() -> list:
    """Import every submodule in this package that has SOURCE_NAME."""
    modules = []
    package = __name__   # "scrapers"
    for finder, name, _ in pkgutil.iter_modules(__path__):
        if name in _SKIP:
            continue
        try:
            mod = importlib.import_module(f".{name}", package=package)
            if hasattr(mod, "SOURCE_NAME") and hasattr(mod, "search"):
                modules.append(mod)
        except Exception as e:
            print(f"[scrapers] failed to load {name}: {e}")
    # Stable order: test-server last, rest alphabetical by SOURCE_NAME
    modules.sort(key=lambda m: (1 if m.SOURCE_NAME == "test-server" else 0, m.SOURCE_NAME))
    return modules


def get_all_sources() -> list[dict]:
    """Return metadata for all discovered sources — used by the API to populate the UI."""
    return [
        {"name": m.SOURCE_NAME, "label": getattr(m, "SOURCE_LABEL", m.SOURCE_NAME)}
        for m in _load_all_modules()
    ]


def _is_enabled(source_name: str) -> bool:
    """Check DB settings for this source. Defaults to enabled."""
    try:
        import database as db
        val = db.get_setting(f"source:{source_name}")
        if val is None:
            return True   # default on
        return val.lower() != "false"
    except Exception:
        return True


def search_all(first_name: str, last_name: str,
               session: cf_requests.Session = None) -> list[ObitMatch]:
    """Search every enabled source; deduplicate results by URL."""
    own     = session is None
    if own:
        session = make_session()
    all_matches = []
    seen_urls   = set()
    try:
        for mod in _load_all_modules():
            if not _is_enabled(mod.SOURCE_NAME):
                print(f"\n── {mod.SOURCE_NAME} (disabled) ──")
                continue
            print(f"\n── {mod.SOURCE_NAME} ──")
            try:
                results = mod.search(first_name, last_name, session=session)
                for m in results:
                    key = (m.obit_url or f"{m.first_name}|{m.last_name}|{m.source}").lower()
                    if key not in seen_urls:
                        seen_urls.add(key)
                        all_matches.append(m)
            except Exception as e:
                print(f"   skipped: {e}")
            if SCRAPE_DELAY > 0:
                time.sleep(SCRAPE_DELAY)
    finally:
        if own:
            session.close()
    print(f"\n── Total unique matches: {len(all_matches)} ──")
    return all_matches


def scan_watchlist(watches: list[dict]) -> list[tuple[dict, ObitMatch]]:
    """Scan all active watchlist entries across all enabled sources."""
    session = make_session()
    hits    = []
    try:
        for watch in watches:
            results = search_all(watch["first_name"], watch["last_name"], session=session)
            for r in results:
                hits.append((watch, r))
    finally:
        session.close()
    return hits
