"""
scrapers/obittree.py — ObitTree.com obituary search.
Aggregator pulling from regional US newspapers.
Note: SSL cert doesn't match www subdomain — use bare domain.
"""
from curl_cffi import requests as cf_requests
from bs4 import BeautifulSoup

from .base import ObitMatch, make_session, html_cards_to_matches

SOURCE_NAME  = "obittree.com"
SOURCE_LABEL = "ObitTree.com"

_BASE   = "https://obittree.com"
_SEARCH = f"{_BASE}/obituary/search/"


def search(first_name: str, last_name: str,
           session: cf_requests.Session = None) -> list[ObitMatch]:
    own = session is None
    if own:
        session = make_session()
    try:
        session.headers.update({"Referer": f"{_BASE}/"})
        resp = session.get(_SEARCH,
                           params={"fn": first_name, "ln": last_name},
                           timeout=20, verify=False)
        resp.raise_for_status()
        soup  = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("div.search-result, div.obit-result, article")
        print(f"[{SOURCE_NAME}] {len(cards)} results")
        return html_cards_to_matches(cards, first_name, last_name, SOURCE_NAME, _BASE)
    except Exception as e:
        print(f"[{SOURCE_NAME}] ERROR: {e}")
        return []
    finally:
        if own:
            session.close()
