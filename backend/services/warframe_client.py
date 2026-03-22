import logging
import time
import threading
import requests
from core.config import API_HEADERS, API_BASE_URL

logger = logging.getLogger(__name__)

# Shared rate-limit state — governs ALL warframe.market HTTP calls (cache + search)
_rate_lock = threading.Lock()
_last_request_time = 0.0
_MIN_REQUEST_INTERVAL = 0.34  # ~3 requests/sec (warframe.market limit)


def _rate_limited_get(url: str, headers: dict, timeout: int = 10, params: dict | None = None) -> requests.Response:
    """GET with shared rate limiting and retry on 429. Used for all warframe.market calls."""
    global _last_request_time
    max_retries = 3
    for attempt in range(max_retries):
        with _rate_lock:
            elapsed = time.time() - _last_request_time
            if elapsed < _MIN_REQUEST_INTERVAL:
                time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
            _last_request_time = time.time()

        resp = requests.get(url, headers=headers, timeout=timeout, params=params)
        if resp.status_code == 429:
            wait = float(resp.headers.get("Retry-After", 2 * (attempt + 1)))
            logger.warning("429 rate-limited, retrying in %ss (attempt %d/%d)", wait, attempt + 1, max_retries)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp  # unreachable, keeps type checker happy


def fetch_auction_bids(auction_id: str, platform: str = "pc") -> list[dict]:
    """Fetch bid history for a single auction. Returns raw bid dicts."""
    headers = {**API_HEADERS, "Platform": platform, "Language": "en"}
    response = _rate_limited_get(
        f"{API_BASE_URL}/auctions/entry/{auction_id}/bids",
        headers=headers,
        timeout=10,
    )
    return response.json().get("payload", {}).get("bids", [])


def search_auctions_raw(params: dict, platform: str = "pc", crossplay: str = "true") -> list[dict]:
    """Call warframe.market auction search. Returns raw auction dicts from the API."""
    headers = {**API_HEADERS, "Platform": platform, "Crossplay": crossplay}
    response = _rate_limited_get(
        f"{API_BASE_URL}/auctions/search", headers=headers, timeout=10, params=params
    )
    return response.json().get("payload", {}).get("auctions", [])
