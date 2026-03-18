"""
Cosine similarity engine for Riven mod comparison.

Builds weighted, normalized stat vectors from riven attributes and computes
similarity scores with adjustments for negative stats and reroll distance.
"""

import math
from core.models import Auction, RivenAttribute
from evaluation.riven_math import normalize_roll


# ---------------------------------------------------------------------------
# Negative stat classifications
# ---------------------------------------------------------------------------

# Negatives that are desirable (reducing these is good or inconsequential)
DESIRABLE_NEGATIVES: set[str] = {
    "recoil",
    "zoom",
    "impact_damage",
    "puncture_damage",
    "chance_to_gain_combo_count",
    "finisher_damage",
}

# Negatives that are undesirable (reducing these hurts most builds)
UNDESIRABLE_NEGATIVES: set[str] = {
    "critical_chance",
    "critical_damage",
    "base_damage_/_melee_damage",
    "multishot",
    "status_chance",
    "fire_rate_/_attack_speed",
}

# Adjustment values
_DESIRABLE_BONUS = 0.05
_UNDESIRABLE_PENALTY = -0.10
# Reroll penalty divisor — higher = gentler penalty
_REROLL_DIVISOR = 20.0


# ---------------------------------------------------------------------------
# Vector building
# ---------------------------------------------------------------------------

def build_stat_vector(
    attributes: list[RivenAttribute],
    stat_weights: dict[str, float],
    disposition: int,
    num_positives: int,
    has_negative: bool,
) -> dict[str, float]:
    """Build a weighted, normalized stat vector from riven attributes.

    For each attribute:
      normalized = actual_value / max_possible (via riven_math)
      score = normalized × stat_weight

    Negative attributes produce negative scores.
    Returns a sparse vector as {url_name: score}.
    """
    vector: dict[str, float] = {}
    default_weight = 1.0 / max(len(stat_weights), 1)

    for attr in attributes:
        norm = normalize_roll(
            url_name=attr.url_name,
            actual_value=attr.value,
            disposition=disposition,
            num_positives=num_positives,
            has_negative=has_negative,
            is_positive_stat=attr.positive,
        )
        weight = stat_weights.get(attr.url_name, default_weight)
        score = norm * weight

        # Negative attributes get negative scores
        if not attr.positive:
            score = -abs(score)

        vector[attr.url_name] = score

    return vector


def build_stat_vector_from_raw(
    positive_attrs: list[dict],
    negative_attr: dict | None,
    stat_weights: dict[str, float],
    disposition: int,
) -> dict[str, float]:
    """Build a stat vector from raw attribute dicts (for the target riven).

    positive_attrs: [{url_name, value}, ...]
    negative_attr:  {url_name, value} or None
    """
    num_positives = len(positive_attrs)
    has_negative = negative_attr is not None
    default_weight = 1.0 / max(len(stat_weights), 1)

    vector: dict[str, float] = {}

    for attr in positive_attrs:
        norm = normalize_roll(
            url_name=attr["url_name"],
            actual_value=attr["value"],
            disposition=disposition,
            num_positives=num_positives,
            has_negative=has_negative,
            is_positive_stat=True,
        )
        weight = stat_weights.get(attr["url_name"], default_weight)
        vector[attr["url_name"]] = norm * weight

    if negative_attr:
        norm = normalize_roll(
            url_name=negative_attr["url_name"],
            actual_value=negative_attr["value"],
            disposition=disposition,
            num_positives=num_positives,
            has_negative=True,
            is_positive_stat=False,
        )
        weight = stat_weights.get(negative_attr["url_name"], default_weight)
        vector[negative_attr["url_name"]] = -(norm * weight)

    return vector


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors (dicts).

    Returns 0.0 if either vector has zero magnitude.
    """
    # Dot product — only shared keys contribute (missing key × anything = 0)
    shared_keys = set(vec_a) & set(vec_b)
    dot = sum(vec_a[k] * vec_b[k] for k in shared_keys)

    mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
    mag_b = math.sqrt(sum(v * v for v in vec_b.values()))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Negative adjustment
# ---------------------------------------------------------------------------

def _negative_adjustment(
    target_neg_names: set[str],
    candidate_neg_names: set[str],
) -> float:
    """Compute similarity adjustment based on negative stat quality.

    +0.05 for each desirable negative shared by both.
    -0.10 for each undesirable negative in candidate but NOT in target.
    """
    adjustment = 0.0

    # Bonus for shared desirable negatives
    shared_desirable = (target_neg_names & candidate_neg_names) & DESIRABLE_NEGATIVES
    adjustment += len(shared_desirable) * _DESIRABLE_BONUS

    # Penalty for undesirable negatives that the candidate has but the target doesn't
    candidate_only_undesirable = (candidate_neg_names - target_neg_names) & UNDESIRABLE_NEGATIVES
    adjustment += len(candidate_only_undesirable) * _UNDESIRABLE_PENALTY

    return adjustment


# ---------------------------------------------------------------------------
# Reroll penalty
# ---------------------------------------------------------------------------

def _reroll_penalty(target_rerolls: int, candidate_rerolls: int) -> float:
    """Exponential decay based on reroll distance: e^(-|diff| / 20)."""
    diff = abs(target_rerolls - candidate_rerolls)
    return math.exp(-diff / _REROLL_DIVISOR)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_similarity(
    target_vector: dict[str, float],
    target_neg_names: set[str],
    target_rerolls: int,
    auction: Auction,
    stat_weights: dict[str, float],
    disposition: int,
) -> float:
    """Compute adjusted similarity between a target riven and an auction's riven.

    Steps:
    1. Build stat vector for auction's riven
    2. Cosine similarity between target and auction vectors
    3. Add negative stat adjustment
    4. Multiply by reroll penalty

    Returns a float — typically 0.0 to ~1.1 (can exceed 1.0 from bonuses).
    """
    # Build auction vector
    num_pos = len(auction.positive_attributes)
    has_neg = len(auction.negative_attributes) > 0

    auction_vector = build_stat_vector(
        attributes=auction.attributes,
        stat_weights=stat_weights,
        disposition=disposition,
        num_positives=num_pos,
        has_negative=has_neg,
    )

    # Cosine similarity
    cos_sim = _cosine_similarity(target_vector, auction_vector)

    # Negative adjustment
    candidate_neg_names = {a.url_name for a in auction.negative_attributes}
    neg_adj = _negative_adjustment(target_neg_names, candidate_neg_names)

    # Reroll penalty
    reroll_mult = _reroll_penalty(target_rerolls, auction.re_rolls or 0)

    # Combined score
    adjusted = (cos_sim + neg_adj) * reroll_mult

    return max(0.0, adjusted)  # floor at 0
