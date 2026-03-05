"""
scrapers/base.py — shared data model, helpers, and base class.

Every source module must expose:
  SOURCE_NAME: str          — unique key, e.g. "legacy.com"
  SOURCE_LABEL: str         — display name for the UI, e.g. "Legacy.com"
  search(first, last, session) -> list[ObitMatch]
"""
import re
from dataclasses import dataclass
from typing import Optional

from curl_cffi import requests as cf_requests
from bs4 import BeautifulSoup


# ── Data model ──────────────────────────────────────────────────────────────

@dataclass
class ObitMatch:
    first_name:   str
    last_name:    str
    birth_year:   Optional[str] = None
    death_year:   Optional[str] = None
    location:     Optional[str] = None
    obit_snippet: Optional[str] = None
    obit_url:     Optional[str] = None
    source:       str = "unknown"
    photo_url:    Optional[str] = None
    age:          Optional[int] = None
    published:    Optional[str] = None

    def __str__(self):
        years = f" ({self.birth_year or '?'} – {self.death_year or '?'})" if (self.birth_year or self.death_year) else ""
        loc   = f" — {self.location}" if self.location else ""
        return f"{self.first_name} {self.last_name}{years}{loc} [{self.source}]"


# ── Shared helpers ───────────────────────────────────────────────────────────

def make_session() -> cf_requests.Session:
    s = cf_requests.Session(impersonate="chrome120")
    s.headers.update({
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection":      "keep-alive",
    })
    return s


def name_matches(search_first: str, search_last: str,
                 result_first: str, result_last: str) -> bool:
    """Loose name matching — last name must match; first allows
    nicknames/initials (Bill/William, B./Bill, etc.)."""
    if search_last.lower() not in result_last.lower():
        return False
    sf, rf = search_first.lower().strip(), result_first.lower().strip()
    if not sf or not rf:
        return True
    if sf in rf or rf in sf:
        return True
    if sf[0] == rf[0]:   # same first initial catches Bill/William
        return True
    return False


def years_from_string(text: str):
    """Extract (birth_year, death_year) from '1945 – 2024' style strings."""
    m = re.search(r'(\d{4})\s*[-–—]\s*(\d{4})', text)
    if m:
        return m.group(1), m.group(2)
    return None, None


def html_cards_to_matches(cards, search_first: str, search_last: str,
                           source: str, base_url: str,
                           name_sel: str = "h2, h3, .name, .obituary-name",
                           loc_sel:  str = ".location, .city-state, .city",
                           date_sel: str = ".dates, time",
                           snip_sel: str = "p, .snippet") -> list[ObitMatch]:
    """Generic HTML card parser shared by sources that use similar markup."""
    matches = []
    for card in cards:
        name_el = card.select_one(name_sel)
        if not name_el:
            continue
        full  = name_el.get_text(strip=True)
        parts = full.split()
        if len(parts) < 2:
            continue
        first, last = parts[0], parts[-1]
        if not name_matches(search_first, search_last, first, last):
            continue
        loc_el   = card.select_one(loc_sel)
        location = loc_el.get_text(strip=True) if loc_el else None
        date_el  = card.select_one(date_sel)
        dates    = date_el.get_text(strip=True) if date_el else ""
        by, dy   = years_from_string(dates)
        snip_el  = card.select_one(snip_sel)
        snippet  = snip_el.get_text(strip=True)[:300] if snip_el else None
        link_el  = card.select_one("a[href]")
        href     = link_el["href"] if link_el else None
        if href and not href.startswith("http"):
            href = base_url + href
        matches.append(ObitMatch(
            first_name=first, last_name=last,
            birth_year=by, death_year=dy,
            location=location, obit_snippet=snippet,
            obit_url=href, source=source,
        ))
    return matches
