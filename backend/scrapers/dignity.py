"""
scrapers/dignity.py — Dignity Memorial obituary search.
~2,000 funeral homes across North America (SCI / Service Corporation network).
"""
from curl_cffi import requests as cf_requests

from .base import ObitMatch, make_session, name_matches

SOURCE_NAME  = "dignitymemorial.com"
SOURCE_LABEL = "Dignity Mem."

_BASE   = "https://www.dignitymemorial.com"
_SEARCH = f"{_BASE}/api/obituaries"


def search(first_name: str, last_name: str,
           session: cf_requests.Session = None) -> list[ObitMatch]:
    own = session is None
    if own:
        session = make_session()
    try:
        session.headers.update({"Referer": f"{_BASE}/"})
        resp = session.get(_SEARCH,
                           params={"firstName": first_name, "lastName": last_name,
                                   "limit": 20},
                           timeout=20)
        resp.raise_for_status()
        data  = resp.json()
        items = data if isinstance(data, list) else (
                data.get("obituaries") or data.get("results") or [])
        print(f"[{SOURCE_NAME}] {len(items)} results")

        matches = []
        for item in items:
            first = (item.get("firstName") or item.get("first_name") or "").strip()
            last  = (item.get("lastName")  or item.get("last_name")  or "").strip()
            if not name_matches(first_name, last_name, first, last):
                continue
            city     = item.get("city") or ""
            state    = item.get("state") or item.get("stateCode") or ""
            location = ", ".join(filter(None, [city, state])) or None
            slug     = item.get("slug") or item.get("id") or ""
            obit_url = f"{_BASE}/obituaries/{slug}" if slug else None
            matches.append(ObitMatch(
                first_name=first, last_name=last,
                location=location,
                obit_snippet=item.get("summary") or item.get("bio") or None,
                obit_url=obit_url,
                source=SOURCE_NAME,
            ))
        return matches

    except Exception as e:
        print(f"[{SOURCE_NAME}] ERROR: {e}")
        return []
    finally:
        if own:
            session.close()
