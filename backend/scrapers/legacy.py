"""
scrapers/legacy.py — Legacy.com obituary search.

Legacy.com server-renders results as a JSON blob inside a <script> tag:
  <script type="application/json" data-hypernova-key="SearchPage" ...><!--{...}--></script>
"""
import json
import time

from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests

from .base import ObitMatch, make_session, name_matches, years_from_string

SOURCE_NAME  = "legacy.com"
SOURCE_LABEL = "Legacy.com"

_BASE   = "https://www.legacy.com"
_SEARCH = f"{_BASE}/obituaries/search"


def search(first_name: str, last_name: str,
           session: cf_requests.Session = None) -> list[ObitMatch]:
    own = session is None
    if own:
        session = make_session()
    try:
        session.headers.update({"Referer": f"{_BASE}/"})
        session.get(_BASE, timeout=15)
        time.sleep(1.5)

        resp = session.get(_SEARCH,
                           params={"firstName": first_name, "lastName": last_name,
                                   "dateRange": "allTime"},
                           timeout=20)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        tag  = soup.find("script", {"data-hypernova-key": "SearchPage",
                                     "type": "application/json"})
        if not tag:
            print(f"[{SOURCE_NAME}] WARNING: JSON blob not found")
            return []

        raw = (tag.string or "").strip()
        if raw.startswith("<!--"): raw = raw[4:]
        if raw.endswith("-->"):    raw = raw[:-3]
        data  = json.loads(raw)
        obits = (data.get("obituaryList") or {}).get("obituaries") or []
        print(f"[{SOURCE_NAME}] {len(obits)} raw results")

        matches = []
        for obit in obits:
            name  = obit.get("name", {})
            first = (name.get("firstName") or "").strip()
            last  = (name.get("lastName")  or "").strip()
            if not name_matches(first_name, last_name, first, last):
                continue
            by, dy   = years_from_string(obit.get("fromToYears") or "")
            loc      = obit.get("location", {})
            city     = (loc.get("city",  {}) or {}).get("fullName", "")
            state    = (loc.get("state", {}) or {}).get("code", "")
            location = ", ".join(filter(None, [city, state])) or None
            links    = obit.get("links", {})
            obit_url = (links.get("obituaryUrl") or {}).get("href") or None
            matches.append(ObitMatch(
                first_name=first, last_name=last,
                birth_year=by, death_year=dy,
                location=location,
                obit_snippet=obit.get("obitSnippet") or None,
                obit_url=obit_url,
                photo_url=(obit.get("mainPhoto") or {}).get("url") or None,
                age=obit.get("age") or None,
                published=obit.get("publishedLine") or obit.get("publishedDate") or None,
                source=SOURCE_NAME,
            ))
        return matches

    except Exception as e:
        print(f"[{SOURCE_NAME}] ERROR: {e}")
        return []
    finally:
        if own:
            session.close()
