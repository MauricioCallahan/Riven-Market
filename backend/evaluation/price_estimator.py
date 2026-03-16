"""
Price estimation pipeline for Riven mods.

Orchestrates stat weights, vectors, archetypes, and similarity to produce
a weighted-average price estimate from comparable auctions.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import quantiles

from models import Auction
from evaluation.stat_weights import compute_stat_weights, get_effective_price
from evaluation.archetypes import classify_attributes, classify_auction, is_compatible
from evaluation.similarity import (
    build_stat_vector_from_raw,
    compute_similarity,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SIMILARITY_THRESHOLD = 0.35
_MAX_COMPARABLES = 20
# Age decay divisor for standard vs high-value listings
_AGE_DECAY_STANDARD = 30.0    # 30d → 0.5× weight
_AGE_DECAY_HIGH_VALUE = 90.0  # 90d → 0.5× weight (expensive rivens have smaller buyer pool)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SimilarityResult:
    """A candidate auction with its similarity score and archetype."""
    auction: Auction
    similarity: float
    archetype: str

    def to_dict(self) -> dict:
        return {
            "similarity": round(self.similarity, 4),
            "archetype": self.archetype,
            **self.auction.to_frontend_dict(),
        }


@dataclass
class PriceEstimate:
    """Final output of the pricing pipeline."""
    estimated_price: float
    confidence: str
    comparable_count: int
    archetype: str
    comparables: list[SimilarityResult] = field(default_factory=list)
    stat_weights: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "estimatedPrice": round(self.estimated_price, 1),
            "confidence": self.confidence,
            "comparableCount": self.comparable_count,
            "archetype": self.archetype,
            "comparables": [c.to_dict() for c in self.comparables],
            "statWeights": self.stat_weights,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_price_threshold(auctions: list[Auction]) -> float:
    """Compute the 75th percentile of buyout prices for age-penalty tiering."""
    buyouts = [
        float(a.buyout_price)
        for a in auctions
        if a.buyout_price is not None
    ]
    if len(buyouts) < 4:
        return float("inf")  # not enough data — treat all as standard
    # quantiles with n=4 gives [Q1, Q2, Q3]
    q1, _q2, q3 = quantiles(buyouts, n=4)
    return q3


def _age_factor(auction: Auction, price: float | None, price_threshold: float) -> float:
    """Compute age-based downweight factor.

    price: pre-extracted effective price (buyout or starting).
    Listings above the P75 price threshold get a gentler 90-day decay;
    lower-priced listings use the standard 30-day decay.
    """
    if auction.updated is None:
        return 1.0

    now = datetime.now(timezone.utc)
    updated = auction.updated
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)

    age_days = max(0, (now - updated).days)

    # Choose decay rate based on price tier
    if price is not None and price >= price_threshold:
        decay_rate = _AGE_DECAY_HIGH_VALUE
    else:
        decay_rate = _AGE_DECAY_STANDARD

    return 1.0 / (1.0 + age_days / decay_rate)


def _remove_outliers(
    results: list[tuple[float, float, float]],
) -> list[tuple[float, float, float]]:
    """IQR-based outlier removal on the price component.

    Input/output: list of (price, similarity, age_factor) tuples.
    """
    if len(results) < 4:
        return results

    prices = sorted(r[0] for r in results)
    q1, _q2, q3 = quantiles(prices, n=4)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    return [r for r in results if lower <= r[0] <= upper]


def _confidence_level(count: int) -> str:
    """Determine confidence based on number of comparables."""
    if count >= 10:
        return "high"
    if count >= 5:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_price(
    positive_attrs: list[dict],
    negative_attr: dict | None,
    re_rolls: int,
    auctions: list[Auction],
    disposition: int,
) -> PriceEstimate:
    """Main entry point for price estimation.

    positive_attrs: [{"url_name": str, "value": float}, ...]
    negative_attr:  {"url_name": str, "value": float} or None

    Pipeline:
    1. Compute weapon-aware stat weights from all auctions
    2. Build target stat vector
    3. Classify target archetype
    4. Score each auction by similarity (archetype-filtered)
    5. Filter by similarity threshold, remove price outliers
    6. Weighted average price with age downweighting
    """
    # 1. Stat weights
    weights = compute_stat_weights(auctions)

    # 2. Target vector
    target_vector = build_stat_vector_from_raw(
        positive_attrs=positive_attrs,
        negative_attr=negative_attr,
        stat_weights=weights,
        disposition=disposition,
    )

    # 3. Classify target
    target_pos_names = [a["url_name"] for a in positive_attrs]
    target_archetype = classify_attributes(target_pos_names)
    target_neg_names = {negative_attr["url_name"]} if negative_attr else set()

    # 4. Score each auction
    scored: list[SimilarityResult] = []
    for auction in auctions:
        candidate_archetype = classify_auction(auction)
        if not is_compatible(target_archetype, candidate_archetype):
            continue

        sim = compute_similarity(
            target_vector=target_vector,
            target_neg_names=target_neg_names,
            target_rerolls=re_rolls,
            auction=auction,
            stat_weights=weights,
            disposition=disposition,
        )

        if sim >= _SIMILARITY_THRESHOLD:
            scored.append(SimilarityResult(
                auction=auction,
                similarity=sim,
                archetype=candidate_archetype,
            ))

    # 5. Compute price threshold for age-penalty tiering
    price_threshold = _compute_price_threshold(auctions)

    # Collect (price, similarity, age_factor) for each comparable
    price_tuples: list[tuple[float, float, float]] = []
    for sr in scored:
        price = get_effective_price(sr.auction)
        if price is None or price <= 0:
            continue
        af = _age_factor(sr.auction, price, price_threshold)
        price_tuples.append((price, sr.similarity, af))

    # 6. Remove price outliers
    filtered = _remove_outliers(price_tuples)

    # Weighted average: Σ(price × similarity × age_factor) / Σ(similarity × age_factor)
    numerator = sum(p * s * a for p, s, a in filtered)
    denominator = sum(s * a for _, s, a in filtered)

    if denominator == 0:
        estimated = 0.0
    else:
        estimated = numerator / denominator

    # Sort comparables by similarity descending, cap at MAX_COMPARABLES
    scored.sort(key=lambda sr: sr.similarity, reverse=True)
    top_comparables = scored[:_MAX_COMPARABLES]

    return PriceEstimate(
        estimated_price=estimated,
        confidence=_confidence_level(len(filtered)),
        comparable_count=len(filtered),
        archetype=target_archetype,
        comparables=top_comparables,
        stat_weights=weights,
    )
