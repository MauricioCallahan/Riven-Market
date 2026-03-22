"""
File-based JSON cache for auction search results.

Provides stale-while-error fallback when the warframe.market API is
unreachable.  Writes are non-blocking (background daemon thread).
"""

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

SEARCH_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), ".cache", "search_results"
)
SEARCH_CACHE_TTL = timedelta(hours=24)


@dataclass
class CachedResult:
    """A cached search result with its timestamp."""
    auctions: list[dict]
    cached_at: str  # ISO 8601


@dataclass
class _InFlightEntry:
    """Tracks a single in-flight API request for deduplication."""
    event: threading.Event
    result: list[dict] | None = None
    error: Exception | None = None


class SearchResultCache:
    """File-based JSON cache for search results with background writes
    and request deduplication for concurrent identical searches."""

    def __init__(
        self,
        cache_dir: str = SEARCH_CACHE_DIR,
        ttl: timedelta = SEARCH_CACHE_TTL,
    ) -> None:
        self._cache_dir = cache_dir
        self._ttl = ttl
        self._in_flight: dict[str, _InFlightEntry] = {}
        self._in_flight_lock = threading.Lock()

    @staticmethod
    def build_cache_key(params: dict[str, Any]) -> str:
        """Deterministic SHA256 from sorted, cleaned params."""
        cleaned = {
            k: (sorted(v) if isinstance(v, list) else v)
            for k, v in params.items()
            if v is not None
        }
        canonical = json.dumps(cleaned, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> str:
        return os.path.join(self._cache_dir, f"{key}.json")

    def get(self, key: str) -> CachedResult | None:
        """Return cached result if present and within TTL, else None."""
        path = self._path(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                blob = json.load(f)
            cached_at_dt = datetime.fromisoformat(blob["cached_at"])
            if cached_at_dt.tzinfo is None:
                cached_at_dt = cached_at_dt.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - cached_at_dt) > self._ttl:
                return None
            return CachedResult(
                auctions=blob["auctions"],
                cached_at=blob["cached_at"],
            )
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            return None

    def set(self, key: str, auctions: list[dict]) -> None:
        """Write result to disk in a background daemon thread (non-blocking)."""
        cached_at = datetime.now(timezone.utc).isoformat()
        blob = {"cached_at": cached_at, "auctions": auctions}
        threading.Thread(
            target=self._write, args=(key, blob), daemon=True
        ).start()

    def _write(self, key: str, blob: dict) -> None:
        try:
            os.makedirs(self._cache_dir, exist_ok=True)
            path = self._path(key)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(blob, f, ensure_ascii=False)
        except OSError as e:
            logger.warning("Failed to write search cache: %s", e)

    # ------------------------------------------------------------------
    # Request deduplication
    # ------------------------------------------------------------------

    def acquire_or_wait(
        self, key: str,
    ) -> tuple[bool, list[dict] | None, Exception | None]:
        """Try to become the owner of an in-flight request for *key*.

        Returns (is_owner, result_data, error):
        - (True, None, None)       — caller should proceed with the API call
        - (False, data, None)      — another thread completed successfully
        - (False, None, exception) — another thread's request failed
        """
        with self._in_flight_lock:
            if key in self._in_flight:
                entry = self._in_flight[key]
            else:
                self._in_flight[key] = _InFlightEntry(event=threading.Event())
                return True, None, None

        # Wait for the owning thread to finish (does not hold the lock)
        entry.event.wait()
        return False, entry.result, entry.error

    def complete(
        self,
        key: str,
        result: list[dict] | None,
        error: Exception | None,
    ) -> None:
        """Signal that the in-flight request for *key* is done."""
        with self._in_flight_lock:
            entry = self._in_flight.get(key)

        if entry is None:
            return

        entry.result = result
        entry.error = error
        entry.event.set()

        # Clean up after a short delay so all waiters can read the result
        def _cleanup() -> None:
            with self._in_flight_lock:
                self._in_flight.pop(key, None)

        threading.Timer(1.0, _cleanup).start()
