"""
scrapers/findagrave.py — FindAGrave.com memorial search.
Massive cemetery database — good for confirming deaths even without a formal obituary.
"""
from curl_cffi import requests as cf_requests
from bs4 import BeautifulSoup

from .base import ObitMatch, make_session, html_cards_to_matches

SOURCE_NAME  = "findagrave.com"
SOURCE_LABEL = "Find a Grave"

_BASE   = "https://www.findagrave.com"
_SEARCH = f"{_BASE}/memorial/search"


def search(first_name: str, last_name: str,
           session: cf_requests.Session = None) -> list[ObitMatch]:
    own = session is None
    if own:
        session = make_session()
    try:
        session.headers.update({"Referer": f"{_BASE}/"})
        resp = session.get(_SEARCH,
                           params={"firstname": first_name, "lastname": last_name,
                                   "orderby": "r"},
                           timeout=20)
        resp.raise_for_status()
        soup  = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("li.memorial-item, div.memorial-card, div[data-memorial-id]")
        print(f"[{SOURCE_NAME}] {len(cards)} results")
        return html_cards_to_matches(
            cards, first_name, last_name, SOURCE_NAME, _BASE,
            name_sel=".memorial-name, h2, h3, .name",
            loc_sel=".memorial-location, .burial-location, .location",
            date_sel=".memorial-dates, .dates, time",
        )
    except Exception as e:
        print(f"[{SOURCE_NAME}] ERROR: {e}")
        return []
    finally:
        if own:
            session.close()
