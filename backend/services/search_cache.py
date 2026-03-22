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


class SearchResultCache:
    """File-based JSON cache for search results with background writes."""

    def __init__(
        self,
        cache_dir: str = SEARCH_CACHE_DIR,
        ttl: timedelta = SEARCH_CACHE_TTL,
    ) -> None:
        self._cache_dir = cache_dir
        self._ttl = ttl

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
