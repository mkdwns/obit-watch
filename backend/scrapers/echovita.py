"""
scrapers/echovita.py — Echovita.com obituary search.
Clean HTML, good US coverage.
"""
from curl_cffi import requests as cf_requests
from bs4 import BeautifulSoup

from .base import ObitMatch, make_session, html_cards_to_matches

SOURCE_NAME  = "echovita.com"
SOURCE_LABEL = "Echovita.com"

_BASE   = "https://echovita.com"
_SEARCH = f"{_BASE}/us/obituaries"


def search(first_name: str, last_name: str,
           session: cf_requests.Session = None) -> list[ObitMatch]:
    own = session is None
    if own:
        session = make_session()
    try:
        session.headers.update({"Referer": f"{_BASE}/"})
        resp = session.get(_SEARCH,
                           params={"fname": first_name, "lname": last_name},
                           timeout=20)
        resp.raise_for_status()
        soup  = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("div.c-person-item, div.obituary-card, article")
        print(f"[{SOURCE_NAME}] {len(cards)} results")
        return html_cards_to_matches(
            cards, first_name, last_name, SOURCE_NAME, _BASE,
            name_sel=".c-person-item__name, h2, h3, .name",
            loc_sel=".c-person-item__location, .location, .city",
        )
    except Exception as e:
        print(f"[{SOURCE_NAME}] ERROR: {e}")
        return []
    finally:
        if own:
            session.close()
