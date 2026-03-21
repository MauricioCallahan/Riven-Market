import logging
from typing import Any
from urllib.parse import urlencode

from core.config import API_BASE_URL, DROPDOWN_OPTIONS, VALID_PLATFORMS
from services.warframe_client import search_auctions_raw
from core.models import Auction
from evaluation.stats import compute_stats
from services import cache_service as cache

logger = logging.getLogger(__name__)

VALID_SORT_BY = set(DROPDOWN_OPTIONS["sort_by"])
VALID_BUYOUT_POLICY = set(DROPDOWN_OPTIONS["buyout_policy"])
VALID_POLARITY = set(DROPDOWN_OPTIONS["polarity"])


# ---------------------------------------------------------------------------
# Normalization — clean raw filter input before validation
# ---------------------------------------------------------------------------

def _normalize_attribute_input(raw: str | None) -> str | None:
    # Accepts a raw attribute string that may contain spaces, mixed separators, etc.
    # Returns a clean comma-separated string of url_names the API expects.
    # e.g. "critical chance, multishot" → "critical_chance,multishot"
    if not raw:
        return None
    parts = [part.strip().lower().replace(" ", "_") for part in raw.split(",")]
    parts = [p for p in parts if p]  # drop empty segments
    return ",".join(parts) if parts else None


def normalize_filters(filters: dict[str, Any]) -> dict[str, Any]:
    # Defaults re_rolls_min to 0 when unset (API needs an explicit value).
    # Strips polarity "any" — omitting the param means "no preference", sending "any" filters incorrectly.
    # Normalizes attribute inputs: replaces spaces with underscores, strips whitespace around commas.
    # Call this before validate_filters().
    normalized = dict(filters)
    # Defaults
    if normalized.get("re_rolls_min") is None:
        normalized["re_rolls_min"] = 0
    if normalized.get("polarity") == "any":
        normalized["polarity"] = None
    if not normalized.get("platform"):
        normalized["platform"] = "pc"
    # Normalize attribute strings: "critical chance, multishot" → "critical_chance,multishot"
    normalized["positive_attributes"] = _normalize_attribute_input(normalized.get("positive_attributes"))
    normalized["negative_attributes"] = _normalize_attribute_input(normalized.get("negative_attributes"))
    # Normalize weapon name: "arca plasmor" → "arca_plasmor"
    weapon = normalized.get("weapon_url_name")
    if weapon:
        normalized["weapon_url_name"] = weapon.strip().lower().replace(" ", "_")
    return normalized


# ---------------------------------------------------------------------------
# Validation — reject values the API will not accept
# ---------------------------------------------------------------------------

def validate_filters(filters: dict[str, Any]) -> list[str]:
    # Checks a normalized filter dict for values the API will reject.
    # Returns a list of human-readable error strings — empty means valid.
    errors = []

    mr_min = filters.get("mastery_rank_min")
    mr_max = filters.get("mastery_rank_max")
    rr_min = filters.get("re_rolls_min")
    rr_max = filters.get("re_rolls_max")

    # --- Weapon is required — the API returns 400 without it ---
    if not filters.get("weapon_url_name"):
        errors.append("Weapon name is required.")

    # --- Input length bounds ---
    weapon = filters.get("weapon_url_name")
    if weapon and len(weapon) > 100:
        errors.append("Weapon name must be 100 characters or fewer.")

    pos_raw = filters.get("positive_attributes")
    if pos_raw and len(pos_raw) > 200:
        errors.append("Positive attributes string must be 200 characters or fewer.")

    neg_raw = filters.get("negative_attributes")
    if neg_raw and len(neg_raw) > 200:
        errors.append("Negative attributes string must be 200 characters or fewer.")

    # --- Mastery rank ---
    if mr_min is not None and (mr_min < 8 or mr_min > 16):
        errors.append(f"Mastery rank minimum must be between 8 and 16 (rivens require MR 8; got {mr_min}).")
    if mr_max is not None and (mr_max < 1 or mr_max > 16):
        errors.append(f"Mastery rank maximum must be between 1 and 16 (got {mr_max}).")
    if mr_min is not None and mr_max is not None and mr_min > mr_max:
        errors.append(f"Mastery rank minimum ({mr_min}) cannot exceed maximum ({mr_max}).")

    # --- Re-rolls ---
    if rr_min is not None and rr_min < 0:
        errors.append(f"Re-rolls minimum must be at least 0 (got {rr_min}).")
    if rr_max is not None and rr_max < 0:
        errors.append(f"Re-rolls maximum must be at least 0 (got {rr_max}).")
    if rr_min is not None and rr_max is not None and rr_min > rr_max:
        errors.append(f"Re-rolls minimum ({rr_min}) cannot exceed maximum ({rr_max}).")

    # --- Sort / buyout / polarity ---
    sort_by = filters.get("sort_by")
    if sort_by is not None and sort_by not in VALID_SORT_BY:
        errors.append(f'Sort option "{sort_by}" is not valid. Must be one of: {", ".join(sorted(VALID_SORT_BY))}.')

    buyout = filters.get("buyout_policy")
    if buyout is not None and buyout not in VALID_BUYOUT_POLICY:
        errors.append(f'Buyout policy "{buyout}" is not valid. Must be one of: {", ".join(sorted(VALID_BUYOUT_POLICY))}.')

    polarity = filters.get("polarity")
    if polarity is not None and polarity not in VALID_POLARITY:
        errors.append(f'Polarity "{polarity}" is not valid. Must be one of: {", ".join(sorted(VALID_POLARITY))}.')

    # --- Validate positive attribute names (uses cached API data) ---
    valid_pos = cache.get_positive_attribute_names()
    valid_neg = cache.get_negative_attribute_names()

    pos_val = filters.get("positive_attributes")
    if pos_val and valid_pos:
        for attr in pos_val.split(","):
            if attr and attr not in valid_pos:
                errors.append(f'Positive attributes: "{attr}" is not a recognized attribute.')

    # --- Validate negative attribute names (only non-positive_only attributes) ---
    neg_val = filters.get("negative_attributes")
    if neg_val and valid_neg:
        for attr in neg_val.split(","):
            if attr and attr not in valid_neg:
                if valid_pos and attr in valid_pos:
                    errors.append(f'Negative attributes: "{attr}" can only be a positive attribute.')
                else:
                    errors.append(f'Negative attributes: "{attr}" is not a recognized attribute.')

    # --- Mod rank ---
    mod_rank = filters.get("mod_rank")
    if mod_rank is not None and mod_rank != "maxed":
        errors.append(f"Mod rank must be 'maxed' or empty (got '{mod_rank}').")

    # --- Platform ---
    platform = filters.get("platform")
    if platform is not None and platform not in VALID_PLATFORMS:
        errors.append(
            f'Platform "{platform}" is not valid. Must be one of: {", ".join(sorted(VALID_PLATFORMS))}.'
        )

    return errors


# ---------------------------------------------------------------------------
# Param building — convert validated filters into API query params
# ---------------------------------------------------------------------------

def build_params(filters: dict[str, Any]) -> dict[str, Any]:
    # Converts a validated filter dict into the query params the API expects.
    # None values are stripped so they don't get sent as literal "None" strings.
    params = {
        "type": "riven",
        "weapon_url_name": filters.get("weapon_url_name"),
        "positive_stats": filters.get("positive_attributes"),
        "negative_stats": filters.get("negative_attributes"),
        "sort_by": filters.get("sort_by") or "price_asc",
        "buyout_policy": filters.get("buyout_policy"),
        "polarity": filters.get("polarity"),
        "mastery_rank_min": filters.get("mastery_rank_min"),
        "mastery_rank_max": filters.get("mastery_rank_max"),
        "re_rolls_min": filters.get("re_rolls_min"),
        "re_rolls_max": filters.get("re_rolls_max"),
        "mod_rank": filters.get("mod_rank"),
    }

    # Remove None values so they are not included in the API request
    return {k: v for k, v in params.items() if v is not None}


# ---------------------------------------------------------------------------
# Search — orchestrate the full search pipeline
# ---------------------------------------------------------------------------

def _execute_search(filters: dict) -> tuple[list[Auction] | None, list[str] | None]:
    """Shared pipeline: normalize → validate → build params → call API → parse.

    Returns (auctions, None) on success or (None, errors) on failure.
    """
    filters = normalize_filters(filters)
    errors = validate_filters(filters)
    if errors:
        return None, errors

    params = build_params(filters)
    logger.debug("Search params: %s", params)

    platform = filters.get("platform", "pc")
    crossplay = "false" if filters.get("crossplay") == "false" else "true"

    try:
        raw = search_auctions_raw(params, platform, crossplay)
    except Exception as e:
        logger.error("Upstream API request failed: %s", e, exc_info=True)
        return None, ["Request failed. Please try again later."]

    return [Auction.from_api(a) for a in raw], None


def fetch_weapon_auctions(
    weapon_url_name: str,
    platform: str = "pc",
    crossplay: str = "true",
    sort_by: str = "price_desc",
) -> tuple[list[Auction] | None, list[str] | None]:
    """Fetch all auctions for a weapon. No stat filters applied."""
    return _execute_search({
        "weapon_url_name": weapon_url_name,
        "sort_by": sort_by,
        "platform": platform,
        "crossplay": crossplay,
    })


def search_auctions(filters: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str] | None]:
    """Main entry point: search + compute stats + format for frontend."""
    auctions, errors = _execute_search(filters)
    if errors:
        return None, errors

    stats = compute_stats(auctions)
    return {
        "auctions": [a.to_frontend_dict() for a in auctions],
        "stats": stats.to_dict(),
    }, None
