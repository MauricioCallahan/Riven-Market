"""
Cosine similarity engine for Riven mod comparison.

Builds weighted, normalized stat vectors from riven attributes and computes
similarity scores with adjustments for negative stats and reroll distance.
"""

import math
from core.models import Auction, AttributeInput, RivenAttribute
from evaluation.riven_math import normalize_roll, NEGATIVE_QUALITY, _DEFAULT_NEGATIVE_QUALITY

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
    positive_attrs: list[AttributeInput],
    negative_attr: AttributeInput | None,
    stat_weights: dict[str, float],
    disposition: int,
) -> dict[str, float]:
    """Build a stat vector from AttributeInput objects (for the target riven)."""
    num_positives = len(positive_attrs)
    has_negative = negative_attr is not None
    default_weight = 1.0 / max(len(stat_weights), 1)

    vector: dict[str, float] = {}

    for attr in positive_attrs:
        norm = normalize_roll(
            url_name=attr.url_name,
            actual_value=attr.value,
            disposition=disposition,
            num_positives=num_positives,
            has_negative=has_negative,
            is_positive_stat=True,
        )
        weight = stat_weights.get(attr.url_name, default_weight)
        vector[attr.url_name] = norm * weight

    if negative_attr:
        norm = normalize_roll(
            url_name=negative_attr.url_name,
            actual_value=negative_attr.value,
            disposition=disposition,
            num_positives=num_positives,
            has_negative=True,
            is_positive_stat=False,
        )
        weight = stat_weights.get(negative_attr.url_name, default_weight)
        vector[negative_attr.url_name] = -(norm * weight)

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

    Each negative stat has a per-stat quality score from NEGATIVE_QUALITY.
    - Shared negatives: apply the candidate's full quality score
    - Candidate-only negatives: only penalize if the negative is harmful
    - Target-only negatives: no adjustment
    """
    adjustment = 0.0
    for neg in candidate_neg_names:
        score = NEGATIVE_QUALITY.get(neg, _DEFAULT_NEGATIVE_QUALITY)
        if neg in target_neg_names:
            adjustment += score
        else:
            # Candidate has a negative the target doesn't — only penalize if bad
            adjustment += min(0.0, score)
    return adjustment


# ---------------------------------------------------------------------------
# Reroll penalty
# ---------------------------------------------------------------------------

def _reroll_penalty(target_rerolls: int, candidate_rerolls: int) -> float:
    """Exponential decay based on reroll distance: e^(-|diff| / 20)."""
    diff = abs(target_rerolls - candidate_rerolls)
    return math.exp(-diff / _REROLL_DIVISOR)


# ---------------------------------------------------------------------------
# Roll quality multiplier
# ---------------------------------------------------------------------------

def _roll_quality_multiplier(auction: Auction, disposition: int) -> float:
    """0.7–1.1× multiplier based on auction's positive roll quality.

    Piecewise linear: [0.0→0.7, 0.5→1.0, 1.0→1.1].
    Low rolls penalized aggressively; high rolls modestly boosted.
    A typical mid-roll (50%) is neutral (1.0×).
    """
    pos_attrs = auction.positive_attributes
    if not pos_attrs:
        return 1.0

    num_pos = len(pos_attrs)
    has_neg = len(auction.negative_attributes) > 0

    norms: list[float] = []
    for attr in pos_attrs:
        n = normalize_roll(
            url_name=attr.url_name,
            actual_value=attr.value,
            disposition=disposition,
            num_positives=num_pos,
            has_negative=has_neg,
            is_positive_stat=True,
        )
        norms.append(min(n, 1.0))  # cap at 1.0 for rounding edge cases

    avg_roll = sum(norms) / len(norms)

    # Piecewise linear mapping:
    #   [0.0, 0.5] → [0.7, 1.0]  (slope 0.6 — aggressive penalty for low rolls)
    #   [0.5, 1.0] → [1.0, 1.1]  (slope 0.2 — modest boost for high rolls)
    if avg_roll <= 0.5:
        return 0.7 + avg_roll * 0.6
    return 1.0 + (avg_roll - 0.5) * 0.2


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

    # Roll quality multiplier
    roll_mult = _roll_quality_multiplier(auction, disposition)

    # Combined score
    adjusted = (cos_sim + neg_adj) * reroll_mult * roll_mult

    return max(0.0, adjusted)  # floor at 0
