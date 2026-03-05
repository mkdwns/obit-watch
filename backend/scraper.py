"""
scraper.py — backward-compatibility shim.

All scraping logic now lives in the scrapers/ package.
This file just re-exports the public API so existing imports
(scheduler.py, main.py) continue to work unchanged.
"""
from scrapers import search_all, scan_watchlist, get_all_sources
from scrapers.base import ObitMatch

__all__ = ["search_all", "scan_watchlist", "get_all_sources", "ObitMatch"]
