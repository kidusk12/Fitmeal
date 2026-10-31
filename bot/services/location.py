"""Delivery destinations: read coordinates out of Google Maps links and build map links.

Telegram cannot show an interactive Google map inside a chat, so we store latitude and
longitude and give the rider a link that opens in their maps app (SRS section 5.2).
"""
from __future__ import annotations

import logging
import re
from urllib.parse import unquote, urlparse

log = logging.getLogger("fitmeal.location")

_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_NUM = r"(-?\d{1,3}\.\d+)"

# Tried in this order. The !3d..!4d form is the actual pin; '@lat,lng' is only the map's centre.
_PATTERNS = [
    re.compile(r"!3d" + _NUM + r"!4d" + _NUM),
    re.compile(r"[?&](?:q|ll|query|destination|daddr|center)=\+?" + _NUM + r",\s*\+?" + _NUM),
    re.compile(r"@" + _NUM + r"," + _NUM),
    re.compile(r"/(?:place|dir)/" + _NUM + r"," + _NUM),
]

SHORT_HOSTS = {"maps.app.goo.gl", "goo.gl"}


def valid_coordinates(lat: float, lng: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lng <= 180


def maps_link(lat: float, lng: float) -> str:
    """The link the rider taps (SRS 5.2)."""
    return f"https://www.google.com/maps?q={lat:.6f},{lng:.6f}"


def find_url(text: str | None) -> str | None:
    match = _URL.search(text or "")
    return match.group(0).rstrip(".,;)]") if match else None


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_google_maps_link(url: str) -> bool:
    host = _host(url)
    return host in SHORT_HOSTS or host == "google.com" or host.endswith(".google.com")


def parse_coordinates(url: str) -> tuple[float, float] | None:
    """Coordinates written inside a full Google Maps URL, or None."""
    decoded = unquote(url)
    for pattern in _PATTERNS:
        match = pattern.search(decoded)
        if match:
            lat, lng = float(match.group(1)), float(match.group(2))
            if valid_coordinates(lat, lng):
                return lat, lng
    return None


async def coordinates_from_link(url: str) -> tuple[float, float] | None:
    """Coordinates for a pasted Google Maps link, following short links (maps.app.goo.gl) if needed."""
    if not is_google_maps_link(url):
        return None
    found = parse_coordinates(url)
    if found:
        return found
    if _host(url) not in SHORT_HOSTS:
        return None  # a full link that only names a place has no coordinates we can read

    try:
        import httpx  # installed with python-telegram-bot

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=8.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FitMealBot)"},
        ) as client:
            async with client.stream("GET", url) as response:  # headers only, body is never read
                chain = [str(r.url) for r in response.history] + [str(response.url)]
    except Exception as exc:  # network trouble must never crash the order flow
        log.warning("Could not resolve short link: %s", exc)
        return None

    for candidate in reversed(chain):
        found = parse_coordinates(candidate)
        if found:
            return found
    return None
