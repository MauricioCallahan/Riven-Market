"""
File-based JSON cache for Warframe Market riven data.

Caches /v1/riven/items (weapons) and /v1/riven/attributes so the frontend
can populate dropdowns without hitting the API on every page load.

- 24-hour TTL — serves stale cache while refreshing in background
- Falls back to last valid cache if the API is unreachable
- Respects Warframe Market's 3 req/sec rate limit
"""

import json
import os
import time
import threading
import requests
from datetime import datetime, timezone, timedelta
from config import API_HEADERS, API_BASE_URL, WARFRAMESTAT_WEAPONS_URL
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
CACHE_TTL = timedelta(hours=24)

# Rate-limit: minimum seconds between API requests
_rate_lock = threading.Lock()
_last_request_time = 0.0
_MIN_REQUEST_INTERVAL = 0.34  # ~3 requests/sec

# In-memory cache (populated from disk on startup, refreshed periodically)
_weapons: list[dict] | None = None
_attributes: list[dict] | None = None
_disposition_map: dict[str, int] | None = None
_weapons_lock = threading.Lock()
_attributes_lock = threading.Lock()
_dispositions_lock = threading.Lock()

# Derived caches — invalidated when source data changes
_merged_weapons: list[dict] | None = None
_positive_attr_names: set[str] | None = None
_negative_attr_names: set[str] | None = None

# Edge-case name overrides: warframe.market item_name → warframestat.us name
_NAME_OVERRIDES: dict[str, str] = {
    # Add mappings here as needed, e.g.:
    # "Vinquibus (Melee)": "Venka Prime",
}


def _rate_limited_get(url: str, headers: dict, timeout: int = 10) -> requests.Response:
    """GET with rate limiting and retry on 429."""
    global _last_request_time
    max_retries = 3
    for attempt in range(max_retries):
        with _rate_lock:
            elapsed = time.time() - _last_request_time
            if elapsed < _MIN_REQUEST_INTERVAL:
                time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
            _last_request_time = time.time()

        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 429:
            wait = float(resp.headers.get("Retry-After", 2 * (attempt + 1)))
            print(f"[cache] 429 rate-limited, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    # If still 429 after retries, raise
    resp.raise_for_status()
    return resp  # unreachable, but keeps type checker happy


# ---------------------------------------------------------------------------
# Disk cache helpers
# ---------------------------------------------------------------------------

def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, f"{name}.json")


def _read_disk_cache(name: str) -> tuple[list[dict] | None, datetime | None]:
    """Read cache file. Returns (data, fetched_at) or (None, None)."""
    path = _cache_path(name)
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
        fetched_at = datetime.fromisoformat(blob["fetched_at"])
        return blob["data"], fetched_at
    except (json.JSONDecodeError, KeyError, ValueError):
        return None, None


def _write_disk_cache(name: str, data: list[dict]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    blob = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    path = _cache_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(blob, f, ensure_ascii=False)


def _is_stale(fetched_at: datetime | None) -> bool:
    if fetched_at is None:
        return True
    now = datetime.now(timezone.utc)
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return (now - fetched_at) > CACHE_TTL


# ---------------------------------------------------------------------------
# Fetch + parse from API
# ---------------------------------------------------------------------------

def _fetch_weapons() -> list[dict]:
    """Fetch riven weapon list from API and return cleaned records."""
    headers = {**API_HEADERS, "Platform": "pc", "Language": "en"}
    resp = _rate_limited_get(f"{API_BASE_URL}/riven/items", headers)
    raw_items = resp.json().get("payload", {}).get("items", [])
    weapons = []
    for item in raw_items:
        weapons.append({
            "url_name": item.get("url_name", ""),
            "item_name": item.get("item_name", ""),
            "group": item.get("group", ""),            # display grouping: primary, secondary, melee, etc.
            "riven_type": item.get("riven_type", ""),   # for attribute filtering: rifle, pistol, melee, etc.
        })
    weapons.sort(key=lambda w: w["item_name"].lower())
    return weapons


def _fetch_attributes() -> list[dict]:
    """Fetch riven attributes from API and return cleaned records."""
    headers = {**API_HEADERS, "Platform": "pc", "Language": "en"}
    resp = _rate_limited_get(f"{API_BASE_URL}/riven/attributes", headers)
    raw_attrs = resp.json().get("payload", {}).get("attributes", [])
    attributes = []
    for attr in raw_attrs:
        attributes.append({
            "url_name": attr.get("url_name", ""),
            "effect": attr.get("effect", ""),
            "positive_only": attr.get("positive_only", False),
            "negative_only": attr.get("negative_only", False),
            "search_only": attr.get("search_only", False),
            "group": attr.get("group", ""),
            "exclusive_to": attr.get("exclusive_to"),   # list of riven_types or None (= all)
        })
    attributes.sort(key=lambda a: a["effect"].lower())
    return attributes


def _fetch_dispositions() -> list[dict]:
    """Fetch weapon disposition data from warframestat.us and return cleaned records."""
    resp = requests.get(WARFRAMESTAT_WEAPONS_URL, timeout=15)
    resp.raise_for_status()
    raw_weapons = resp.json()
    dispositions = []
    for weapon in raw_weapons:
        dispo = weapon.get("disposition")
        name = weapon.get("name", "")
        if dispo is not None and name:
            dispositions.append({
                "name": name.lower(),
                "disposition": int(dispo),
            })
    return dispositions


def _build_disposition_map(data: list[dict]) -> dict[str, int]:
    """Convert disposition list to a lowercase-name-keyed lookup dict."""
    return {entry["name"]: entry["disposition"] for entry in data}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _refresh_cache(name: str, fetch_fn, mem_lock: threading.Lock, setter):
    """Fetch fresh data and update both disk and in-memory cache."""
    try:
        data = fetch_fn()
        _write_disk_cache(name, data)
        with mem_lock:
            setter(data)
        print(f"[cache] Refreshed {name} — {len(data)} entries")
    except Exception as e:
        print(f"[cache] Failed to refresh {name}: {e}")


def _set_weapons(data):
    global _weapons, _merged_weapons
    _weapons = data
    _merged_weapons = None  # invalidate derived cache


def _set_attributes(data):
    global _attributes, _positive_attr_names, _negative_attr_names
    _attributes = data
    _positive_attr_names = None  # invalidate derived caches
    _negative_attr_names = None


def _set_dispositions(data):
    global _disposition_map, _merged_weapons
    _disposition_map = _build_disposition_map(data) if data else None
    _merged_weapons = None  # invalidate derived cache


# (name, fetch_fn, lock, setter) for each cached resource
_CACHE_ENTRIES = [
    ("weapons",      _fetch_weapons,      _weapons_lock,      _set_weapons),
    ("attributes",   _fetch_attributes,   _attributes_lock,   _set_attributes),
    ("dispositions", _fetch_dispositions, _dispositions_lock, _set_dispositions),
]


def init_cache():
    """Load cache from disk on startup. Refresh stale entries in background."""
    for name, fetch_fn, lock, setter in _CACHE_ENTRIES:
        data, fetched_at = _read_disk_cache(name)
        if data is not None:
            with lock:
                setter(data)
            print(f"[cache] Loaded {len(data)} {name} from disk cache")

        if _is_stale(fetched_at):
            print(f"[cache] {name.capitalize()} cache is stale — refreshing in background")
            threading.Thread(
                target=_refresh_cache,
                args=(name, fetch_fn, lock, setter),
                daemon=True,
            ).start()


def get_weapons() -> list[dict] | None:
    """Return cached weapons list with disposition merged in, or None if not yet available."""
    global _merged_weapons

    # Return cached merge if available
    if _merged_weapons is not None:
        return _merged_weapons

    with _weapons_lock:
        weapons = _weapons
    if weapons is None:
        return None

    with _dispositions_lock:
        dispo_map = _disposition_map or {}

    # Merge disposition into each weapon dict
    result = []
    unmatched = []
    for w in weapons:
        item_name = w.get("item_name", "")
        lookup_name = _NAME_OVERRIDES.get(item_name, item_name).lower()
        disposition = dispo_map.get(lookup_name, 3)
        result.append({**w, "disposition": disposition})
        if lookup_name not in dispo_map and dispo_map:
            unmatched.append(item_name)

    if unmatched and len(unmatched) <= 20:
        print(f"[cache] Weapons with no disposition match (defaulting to 3): {unmatched}")
    elif unmatched:
        print(f"[cache] {len(unmatched)} weapons with no disposition match (defaulting to 3)")

    _merged_weapons = result
    return result


def get_disposition(weapon_name: str) -> int:
    """Get disposition for a weapon by display name. Returns 3 if unknown."""
    with _dispositions_lock:
        dispo_map = _disposition_map
    if not dispo_map:
        return 3
    lookup_name = _NAME_OVERRIDES.get(weapon_name, weapon_name).lower()
    return dispo_map.get(lookup_name, 3)


def get_attributes() -> list[dict] | None:
    """Return cached attributes list, or None if not yet available."""
    with _attributes_lock:
        return _attributes


def get_positive_attribute_names() -> set[str]:
    """All attribute url_names that can be used as positive stats."""
    global _positive_attr_names
    if _positive_attr_names is not None:
        return _positive_attr_names
    attrs = get_attributes()
    if not attrs:
        return set()
    _positive_attr_names = {a["url_name"] for a in attrs if not a.get("search_only", False)}
    return _positive_attr_names


def get_negative_attribute_names() -> set[str]:
    """Attribute url_names that can be used as negative stats (excludes positive_only)."""
    global _negative_attr_names
    if _negative_attr_names is not None:
        return _negative_attr_names
    attrs = get_attributes()
    if not attrs:
        return set()
    _negative_attr_names = {a["url_name"] for a in attrs if not a.get("positive_only", False) and not a.get("search_only", False)}
    return _negative_attr_names
