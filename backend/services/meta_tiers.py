"""
Meta tier caching service for weapon Incarnon-based pricing multipliers.

Two data sources:
1. Warframe Wiki (MediaWiki API) — list of Incarnon-eligible weapons
2. Overframe.gg (Playwright scrape) — tier rankings (S/A/B/C/D)

Cross-references both to produce a multiplier for Incarnon-eligible weapons only.
Weapons with only a Prime variant (no Incarnon) get no multiplier.

Cache files (backend/.cache/):
- incarnon_weapons.json  — wiki Incarnon list (24hr TTL)
- overframe_tiers.json   — raw Overframe tier data (24hr TTL)
- meta_tiers.json        — final combined result (24hr TTL)
"""

import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")
CACHE_TTL = timedelta(hours=24)

WIKI_API_URL = "https://warframe.fandom.com/api.php"
INCARNON_WIKI_PAGE = "Incarnon"
INCARNON_SECTIONS = [4, 5, 6]  # Primary, Secondary, Melee Genesis sections

OVERFRAME_BASE_URL = "https://overframe.gg/tier-list/"
OVERFRAME_CATEGORIES = ["primary-weapons", "secondary-weapons", "melee-weapons"]
FETCH_TIMEOUT_MS = 15000

# Known suffixes to strip when normalizing riven weapon names to base names
_WEAPON_SUFFIXES = (" prime", " vandal", " wraith", " prisma")


class TierLevel(str, Enum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


TIER_MULTIPLIERS: dict[TierLevel, float] = {
    TierLevel.S: 1.3,
    TierLevel.A: 1.0,
    TierLevel.B: 0.8,
    TierLevel.C: 0.5,
    TierLevel.D: 0.3,
}

# Rank ordering for "best tier" comparisons: lower = better
_TIER_RANK: dict[TierLevel, int] = {
    TierLevel.S: 0, TierLevel.A: 1, TierLevel.B: 2, TierLevel.C: 3, TierLevel.D: 4,
}


@dataclass
class WeaponTier:
    tier: TierLevel
    multiplier: float


# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

_meta_tiers: dict[str, WeaponTier] | None = None
_incarnon_weapons: set[str] | None = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Disk cache helpers
# ---------------------------------------------------------------------------

def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, f"{name}.json")


def _read_json_cache(name: str) -> tuple[dict | None, datetime | None]:
    """Read a JSON cache file. Returns (data_dict, fetched_at) or (None, None)."""
    path = _cache_path(name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
        fetched_key = "fetched_at" if "fetched_at" in blob else "last_updated"
        fetched_at = datetime.fromisoformat(blob[fetched_key])
        return blob, fetched_at
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
        return None, None


def _write_json_cache(name: str, data: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _is_stale(fetched_at: datetime | None) -> bool:
    if fetched_at is None:
        return True
    now = datetime.now(timezone.utc)
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return (now - fetched_at) > CACHE_TTL


# ---------------------------------------------------------------------------
# Weapon name normalization
# ---------------------------------------------------------------------------

class NameNormalizer:
    """Normalize weapon names between warframe.market, Overframe, and wiki."""

    @staticmethod
    def to_base_name(name: str) -> str:
        """Convert any weapon name to its base form for cache lookup.

        'Soma Prime' -> 'soma', 'soma_prime' -> 'soma', 'Torid' -> 'torid'
        """
        result = name.replace("_", " ").lower().strip()
        for suffix in _WEAPON_SUFFIXES:
            if result.endswith(suffix):
                result = result[: -len(suffix)].strip()
                break
        return result



# ---------------------------------------------------------------------------
# Incarnon weapons — Wiki API fetch
# ---------------------------------------------------------------------------

class IncarnonFetcher:
    """Fetch Incarnon-eligible weapon list from Warframe Wiki MediaWiki API."""

    _PATTERN = re.compile(r"\{\{Resource\|(.+?) Incarnon Genesis\}\}")

    @staticmethod
    def fetch() -> set[str]:
        """Fetch all Incarnon weapon base names from wiki sections 4, 5, 6."""
        weapons: set[str] = set()
        for section_id in INCARNON_SECTIONS:
            params = {
                "action": "parse",
                "page": INCARNON_WIKI_PAGE,
                "format": "json",
                "prop": "wikitext",
                "section": str(section_id),
            }
            try:
                resp = requests.get(WIKI_API_URL, params=params, timeout=15)
                resp.raise_for_status()
                wikitext = resp.json().get("parse", {}).get("wikitext", {}).get("*", "")
                matches = IncarnonFetcher._PATTERN.findall(wikitext)
                for name in matches:
                    weapons.add(name.strip().lower())
                logger.debug("Wiki section %d: found %d Incarnon weapons", section_id, len(matches))
            except Exception as e:
                logger.warning("Failed to fetch wiki section %d: %s", section_id, e)
        logger.info("Total Incarnon weapons from wiki: %d", len(weapons))
        return weapons

    @staticmethod
    def load_cache() -> tuple[set[str] | None, datetime | None]:
        blob, fetched_at = _read_json_cache("incarnon_weapons")
        if blob and "weapons" in blob:
            return set(blob["weapons"]), fetched_at
        return None, None

    @staticmethod
    def save_cache(weapons: set[str]) -> None:
        _write_json_cache("incarnon_weapons", {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "warframe.fandom.com/wiki/Incarnon",
            "weapons": sorted(weapons),
        })


# ---------------------------------------------------------------------------
# Overframe tier scraping — Playwright
# ---------------------------------------------------------------------------

class OverframeScraper:
    """Scrape weapon tier rankings from Overframe.gg using Playwright.

    DOM structure (discovered via inspection):
    - Tier sections: div.TierList_tierContainer__psIt4
    - Tier title h1: "S Tier - Prime Time", "A Tier - Strong Picks", etc.
      → extract first word before " Tier" to get tier letter
    - Weapon links: <a> inside each tier container, text = weapon name
    """

    # Map h1 prefix to TierLevel
    _TIER_LETTER_MAP = {"S": TierLevel.S, "A": TierLevel.A, "B": TierLevel.B, "C": TierLevel.C, "D": TierLevel.D}

    @staticmethod
    def scrape_category(page, category: str) -> dict[str, TierLevel]:
        """Scrape one Overframe tier list category. `page` is a Playwright Page."""
        url = f"{OVERFRAME_BASE_URL}{category}/"
        weapons: dict[str, TierLevel] = {}

        try:
            page.goto(url, timeout=FETCH_TIMEOUT_MS)
            page.wait_for_timeout(4000)  # let JS render

            # Extract all tier containers with their weapons via JS evaluation
            data = page.evaluate("""() => {
                const containers = document.querySelectorAll('[class*="TierList_tierContainer"]');
                const result = [];
                containers.forEach(container => {
                    const h1 = container.querySelector('h1');
                    if (!h1) return;
                    const tierText = h1.textContent.trim();
                    const links = container.querySelectorAll('a');
                    const names = [];
                    links.forEach(a => {
                        const name = a.textContent.trim();
                        if (name) names.push(name);
                    });
                    result.push({ tierText, weapons: names });
                });
                return result;
            }""")

            for section in data:
                tier_text = section.get("tierText", "")
                # Extract tier letter: "S Tier - Prime Time" -> "S"
                tier_letter = tier_text.split(" ")[0].upper() if tier_text else ""
                tier = OverframeScraper._TIER_LETTER_MAP.get(tier_letter)
                if tier is None:
                    continue
                for name in section.get("weapons", []):
                    if name:
                        weapons[name.lower()] = tier

            logger.info("Overframe %s: scraped %d weapons", category, len(weapons))

        except Exception as e:
            logger.warning("Failed to scrape Overframe %s: %s", category, e)

        return weapons

    @staticmethod
    def scrape_all() -> dict[str, TierLevel]:
        """Scrape all 3 Overframe categories. Returns {weapon_name_lower: TierLevel}."""
        from playwright.sync_api import sync_playwright

        all_weapons: dict[str, TierLevel] = {}

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                for category in OVERFRAME_CATEGORIES:
                    result = OverframeScraper.scrape_category(page, category)
                    all_weapons.update(result)
                browser.close()
        except Exception as e:
            logger.error("Playwright launch failed: %s", e)

        logger.info("Overframe total: scraped %d weapons across all categories", len(all_weapons))
        return all_weapons

    @staticmethod
    def load_cache() -> tuple[dict[str, TierLevel] | None, datetime | None]:
        blob, fetched_at = _read_json_cache("overframe_tiers")
        if blob and "weapons" in blob:
            tier_map = {}
            for name, tier_str in blob["weapons"].items():
                try:
                    tier_map[name] = TierLevel(tier_str)
                except ValueError:
                    continue
            return tier_map, fetched_at
        return None, None

    @staticmethod
    def save_cache(weapons: dict[str, TierLevel]) -> None:
        _write_json_cache("overframe_tiers", {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "overframe.gg",
            "weapons": {name: tier.value for name, tier in weapons.items()},
        })


# ---------------------------------------------------------------------------
# Cross-reference + combined cache
# ---------------------------------------------------------------------------

class MetaTierService:
    """Build and serve meta tier multipliers for Incarnon-eligible weapons."""

    @staticmethod
    def build(
        incarnon_weapons: set[str],
        overframe_tiers: dict[str, TierLevel],
    ) -> dict[str, WeaponTier]:
        """Cross-reference Incarnon list with Overframe tiers.

        For each Incarnon weapon, search Overframe tiers for:
        1. base name (e.g., "soma")
        2. "{name} prime" (e.g., "soma prime") — Overframe often lists the Prime variant
        3. "{name} incarnon" — some may be listed this way

        Takes the best (highest) tier found. If no match, defaults to B tier.
        """
        result: dict[str, WeaponTier] = {}

        for base_name in incarnon_weapons:
            candidates = [base_name, f"{base_name} prime", f"{base_name} incarnon"]
            best_tier: TierLevel | None = None

            for candidate in candidates:
                tier = overframe_tiers.get(candidate)
                if tier is not None:
                    if best_tier is None or _TIER_RANK[tier] < _TIER_RANK[best_tier]:
                        best_tier = tier

            if best_tier is None:
                # No Overframe data — default to B (neutral multiplier area)
                logger.debug("No Overframe tier for Incarnon weapon '%s', defaulting to B", base_name)
                best_tier = TierLevel.B

            result[base_name] = WeaponTier(
                tier=best_tier,
                multiplier=TIER_MULTIPLIERS[best_tier],
            )

        logger.info("Built meta tiers for %d Incarnon weapons", len(result))
        return result

    @staticmethod
    def load_cache() -> tuple[dict[str, WeaponTier] | None, datetime | None]:
        blob, fetched_at = _read_json_cache("meta_tiers")
        if blob and "weapons" in blob:
            result = {}
            for name, data in blob["weapons"].items():
                try:
                    tier = TierLevel(data["tier"])
                    result[name] = WeaponTier(tier=tier, multiplier=data["multiplier"])
                except (ValueError, KeyError):
                    continue
            return result if result else None, fetched_at
        return None, None

    @staticmethod
    def save_cache(tiers: dict[str, WeaponTier]) -> None:
        _write_json_cache("meta_tiers", {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "sources": ["overframe.gg", "warframe.fandom.com"],
            "_note": "Only Incarnon-eligible weapons. Keys are base weapon names for riven lookup. Prime-only weapons excluded.",
            "weapons": {
                name: {"tier": wt.tier.value, "multiplier": wt.multiplier}
                for name, wt in sorted(tiers.items())
            },
        })


# ---------------------------------------------------------------------------
# Refresh pipeline
# ---------------------------------------------------------------------------

def _full_refresh() -> None:
    """Run the full fetch → cross-reference → cache pipeline."""
    global _meta_tiers, _incarnon_weapons

    try:
        # 1. Incarnon weapons from wiki
        incarnon = IncarnonFetcher.fetch()
        if not incarnon:
            logger.warning("No Incarnon weapons fetched from wiki — aborting refresh")
            return
        IncarnonFetcher.save_cache(incarnon)

        # 2. Overframe tiers via Playwright
        overframe = OverframeScraper.scrape_all()
        if not overframe:
            logger.warning("No Overframe tiers scraped — aborting refresh")
            return
        OverframeScraper.save_cache(overframe)

        # 3. Cross-reference
        tiers = MetaTierService.build(incarnon, overframe)
        MetaTierService.save_cache(tiers)

        with _lock:
            _meta_tiers = tiers
            _incarnon_weapons = incarnon

        logger.info("Meta tier refresh complete — %d weapons", len(tiers))

    except Exception as e:
        logger.error("Meta tier refresh failed: %s", e)


def refresh(force: bool = False) -> None:
    """Refresh meta tier data if stale or forced."""
    _, fetched_at = MetaTierService.load_cache()
    if not force and not _is_stale(fetched_at):
        logger.debug("Meta tier cache is fresh — skipping refresh")
        return
    _full_refresh()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init() -> None:
    """Load meta tier data from disk on startup. Refresh in background if stale."""
    global _meta_tiers, _incarnon_weapons

    # Load combined cache from disk
    tiers, fetched_at = MetaTierService.load_cache()
    if tiers:
        with _lock:
            _meta_tiers = tiers
        logger.info("Loaded %d meta tiers from disk cache", len(tiers))

    if _is_stale(fetched_at):
        logger.info("Meta tier cache is stale — refreshing in background")
        threading.Thread(target=_full_refresh, daemon=True).start()


def get_meta_tier(weapon_name: str) -> float | None:
    """Get the meta tier multiplier for a weapon.

    Args:
        weapon_name: Display name from warframe.market (e.g., 'Soma Prime', 'Torid').

    Returns:
        Multiplier float (e.g. 1.3 for S-tier) or None if weapon has no Incarnon adapter.
    """
    with _lock:
        tiers = _meta_tiers
    if not tiers:
        return None

    base_name = NameNormalizer.to_base_name(weapon_name)
    weapon_tier = tiers.get(base_name)
    if weapon_tier is None:
        return None
    return weapon_tier.multiplier


def get_weapon_tier(weapon_name: str) -> WeaponTier | None:
    """Get full tier info for a weapon. Returns None if not Incarnon-eligible."""
    with _lock:
        tiers = _meta_tiers
    if not tiers:
        return None

    base_name = NameNormalizer.to_base_name(weapon_name)
    return tiers.get(base_name)


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    logger.info("Running full meta tier refresh...")
    _full_refresh()
    logger.info("Results:")
    with _lock:
        if _meta_tiers:
            for name, wt in sorted(_meta_tiers.items()):
                logger.info("  %s  %s-tier  x%s", f"{name:25s}", wt.tier.value, wt.multiplier)
        else:
            logger.info("  No tiers built.")
