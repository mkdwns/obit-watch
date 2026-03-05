"""
scrapers/test_server.py — Local fake obituary server for testing.

Only active when TEST_OBITS_ENABLED=true in environment.
The test obit store lives at /api/test/obits in main.py.
"""
import os
import urllib.request
import urllib.parse
import json
from curl_cffi import requests as cf_requests

from .base import ObitMatch, name_matches

SOURCE_NAME  = "test-server"
SOURCE_LABEL = "Test Server"


def search(first_name: str, last_name: str,
           session: cf_requests.Session = None) -> list[ObitMatch]:
    if os.getenv("TEST_OBITS_ENABLED", "").lower() != "true":
        return []

    # Read at call time so env changes are picked up without restart
    server_url = os.getenv("TEST_SERVER_URL", "http://localhost:8000")

    try:
        # Use stdlib urllib instead of curl_cffi — avoids Chrome TLS
        # impersonation issues when connecting to plain localhost HTTP
        params = urllib.parse.urlencode({"first_name": first_name, "last_name": last_name})
        url    = f"{server_url}/api/test/obits/search?{params}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            items = json.loads(resp.read().decode())

        print(f"[{SOURCE_NAME}] {len(items)} results")

        matches = []
        for item in items:
            first = item.get("first_name", "")
            last  = item.get("last_name",  "")
            if not name_matches(first_name, last_name, first, last):
                continue
            matches.append(ObitMatch(
                first_name   = first,
                last_name    = last,
                birth_year   = item.get("birth_year"),
                death_year   = item.get("death_year"),
                location     = item.get("location"),
                obit_snippet = item.get("obit_snippet"),
                obit_url     = item.get("obit_url") or f"{server_url}/api/test/obits/{item.get('id', '')}",
                photo_url    = item.get("photo_url"),
                age          = item.get("age"),
                published    = item.get("published"),
                source       = SOURCE_NAME,
            ))
        return matches

    except Exception as e:
        print(f"[{SOURCE_NAME}] ERROR: {e}")
        return []
