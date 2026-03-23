"""
Base stat tables and normalization for Warframe Riven mods.

The warframe.market API provides rolled values but no stat ranges, so we
hardcode max-roll values at disposition 3 / 2 positives / no negative
(the "reference" configuration).  max_roll_value() then scales by
disposition, stat count, and negative-bonus to get the true ceiling for
any specific riven configuration.

Source: Warframe Wiki riven stat range tables.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Auction


# ---------------------------------------------------------------------------
# Base stat table — max positive roll at dispo 3, 2 positive stats, no neg
# ---------------------------------------------------------------------------
# Values are percentages except punch_through (flat) and combo_duration (seconds).

RIVEN_BASE_STATS: dict[str, float] = {
    # --- Universal stats ---
    "critical_chance":              150.0,
    "critical_damage":              120.0,
    "base_damage_/_melee_damage":   165.0,
    "multishot":                    120.0,
    "fire_rate_/_attack_speed":      75.0,
    "status_chance":                120.0,
    "status_duration":              100.0,
    # --- Elements ---
    "heat_damage":                  120.0,
    "cold_damage":                  120.0,
    "electric_damage":              120.0,
    "toxin_damage":                 120.0,
    # --- Physical ---
    "impact_damage":                120.0,
    "puncture_damage":              120.0,
    "slash_damage":                 120.0,
    # --- Utility (ranged) ---
    "magazine_capacity":             50.0,
    "ammo_maximum":                  50.0,
    "reload_speed":                  50.0,
    "projectile_speed":              90.0,
    "punch_through":                  2.7,  # flat, not %
    "recoil":                        90.0,  # positive roll = -90% recoil (reduction)
    "zoom":                          60.0,
    # --- Faction ---
    "damage_vs_corpus":              45.0,
    "damage_vs_grineer":             45.0,
    "damage_vs_infested":            45.0,
    # --- Melee ---
    "range":                        120.0,
    "combo_duration":                 5.0,  # flat seconds
    "critical_chance_on_slide_attack": 90.0,
    "finisher_damage":              120.0,
    "channeling_damage":             60.0,  # Initial Combo
    "channeling_efficiency":         60.0,  # Heavy Attack Efficiency
    "chance_to_gain_extra_combo_count": 60.0,  # positive_only
    "chance_to_gain_combo_count":    40.0,  # negative_only — stored as magnitude
}


# ---------------------------------------------------------------------------
# Multipliers
# ---------------------------------------------------------------------------

# Integer disposition (1-5) → approximate float multiplier
DISPOSITION_MULTIPLIERS: dict[int, float] = {
    1: 0.50,
    2: 0.73,
    3: 1.00,
    4: 1.25,
    5: 1.50,
}

# Number of positive stats → multiplier (more stats = each is weaker)
STAT_COUNT_MULTIPLIERS: dict[int, float] = {
    2: 1.00,
    3: 0.75,
}

# Having a negative stat boosts positive stat magnitudes by 25%
NEGATIVE_BONUS: float = 1.25

# Ratio of negative magnitude to positive magnitude
# A stat rolled as a negative is ~45% the magnitude of the positive version
NEGATIVE_RATIO: float = 0.45


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def max_roll_value(
    url_name: str,
    disposition: int,
    num_positives: int,
    has_negative: bool,
) -> float:
    """Calculate the maximum possible roll value for a stat.

    Returns the absolute magnitude (always positive).
    """
    base = RIVEN_BASE_STATS.get(url_name)
    if base is None:
        return 0.0

    dispo_mult = DISPOSITION_MULTIPLIERS.get(disposition, 1.0)
    count_mult = STAT_COUNT_MULTIPLIERS.get(num_positives, 1.0)
    neg_mult = NEGATIVE_BONUS if has_negative else 1.0

    return base * dispo_mult * count_mult * neg_mult


def max_negative_roll_value(
    url_name: str,
    disposition: int,
    num_positives: int,
    has_negative: bool,
) -> float:
    """Max magnitude of a stat when it rolls as a negative attribute."""
    return max_roll_value(url_name, disposition, num_positives, has_negative) * NEGATIVE_RATIO


def normalize_roll(
    url_name: str,
    actual_value: float,
    disposition: int,
    num_positives: int,
    has_negative: bool,
    is_positive_stat: bool,
) -> float:
    """Normalize a rolled stat value to 0.0–1.0 range.

    actual_value : the rolled value from the auction (may be negative for
                   recoil-reduction or negative attributes)
    is_positive_stat : True if this attribute is a positive stat on the riven

    Returns a ratio of actual magnitude to max possible magnitude.
    Values can exceed 1.0 slightly due to rounding in the base table.
    """
    if is_positive_stat:
        max_val = max_roll_value(url_name, disposition, num_positives, has_negative)
    else:
        max_val = max_negative_roll_value(url_name, disposition, num_positives, has_negative)

    if max_val == 0:
        return 0.0

    return abs(actual_value) / max_val


# ---------------------------------------------------------------------------
# Negative stat quality scores
# ---------------------------------------------------------------------------

# Per-stat adjustment for negative attributes.
# Positive = desirable negative (good for score), negative = harmful.
NEGATIVE_QUALITY: dict[str, float] = {
    # Desirable negatives (positive adjustment)
    "zoom":                          +0.08,
    "recoil":                        +0.06,
    "puncture_damage":               +0.05,
    "impact_damage":                 +0.05,
    "finisher_damage":               +0.04,
    "chance_to_gain_combo_count":    +0.03,
    # Neutral negatives
    "ammo_maximum":                  +0.02,
    "status_duration":               +0.01,
    "magazine_capacity":              0.00,
    "projectile_speed":               0.00,
    "reload_speed":                  -0.02,
    # Undesirable negatives (penalty)
    "fire_rate_/_attack_speed":      -0.06,
    "status_chance":                 -0.08,
    "base_damage_/_melee_damage":    -0.12,
    "multishot":                     -0.12,
    "critical_damage":               -0.14,
    "critical_chance":               -0.15,
}

_DEFAULT_NEGATIVE_QUALITY: float = -0.03  # unknown negatives get a mild penalty


# ---------------------------------------------------------------------------
# Percentile scoring
# ---------------------------------------------------------------------------

def compute_attr_percentile_score(auction: Auction, disposition: int) -> float:
    """Score an auction by how well-rolled its positive attributes are.

    Averages the normalized roll quality (0.0–1.0) of all positive stats,
    then applies a small adjustment based on the negative attribute quality.

    Returns a value roughly in [0.0, 1.0]; higher is better-rolled.
    """
    pos_attrs = [a for a in auction.attributes if a.positive]
    neg_attrs = [a for a in auction.attributes if not a.positive]
    num_positives = len(pos_attrs)
    has_negative = bool(neg_attrs)

    if not pos_attrs:
        return 0.0

    avg_pos = sum(
        min(normalize_roll(a.url_name, a.value, disposition, num_positives, has_negative, True), 1.0)
        for a in pos_attrs
    ) / num_positives

    neg_adjustment = 0.0
    if neg_attrs:
        neg = neg_attrs[0]
        severity = min(
            normalize_roll(neg.url_name, neg.value, disposition, num_positives, has_negative, False),
            1.0,
        )
        neg_adjustment = NEGATIVE_QUALITY.get(neg.url_name, _DEFAULT_NEGATIVE_QUALITY) * severity

    return avg_pos + neg_adjustment


def validate_base_stats(cached_url_names: set[str]) -> list[str]:
    """Check that RIVEN_BASE_STATS covers all API attributes and vice-versa.

    Returns a list of warning strings. Empty = fully aligned.
    """
    warnings = []
    our_names = set(RIVEN_BASE_STATS.keys())

    missing_from_table = cached_url_names - our_names
    extra_in_table = our_names - cached_url_names

    for name in sorted(missing_from_table):
        warnings.append(f"Attribute '{name}' exists in API but missing from RIVEN_BASE_STATS")
    for name in sorted(extra_in_table):
        warnings.append(f"Attribute '{name}' in RIVEN_BASE_STATS but not found in API")

    return warnings
