"""
Price estimation pipeline for Riven mods.

Orchestrates stat weights, vectors, archetypes, and similarity to produce
a weighted-average price estimate from comparable auctions.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from statistics import quantiles

from core.models import Auction, AttributeInput, Bid
from evaluation.stat_weights import compute_stat_weights, get_effective_price
from evaluation.archetypes import Archetype, classify_attributes, classify_auction, is_compatible
from evaluation.similarity import (
    build_stat_vector_from_raw,
    compute_similarity,
)
from evaluation.bid_validator import (
    BidConfidenceTier,
    BidValidator,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ConfidenceLevel(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SIMILARITY_THRESHOLD = 0.35
_MAX_COMPARABLES = 20
# Age decay divisor for standard vs high-value listings
_AGE_DECAY_STANDARD = 30.0    # 30d → 0.5× weight
_AGE_DECAY_HIGH_VALUE = 120.0  # 120d → 0.5× weight (expensive rivens have smaller buyer pool)
# Volume thresholds for demand-aware confidence
_VOLUME_HIGH = 40      # >= 40 total auctions = healthy market
_VOLUME_MEDIUM = 15    # 15–39 = adequate


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SimilarityResult:
    """A candidate auction with its similarity score and archetype."""
    auction: Auction
    similarity: float
    archetype: Archetype

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
    confidence: ConfidenceLevel
    comparable_count: int
    archetype: Archetype
    comparables: list[SimilarityResult] = field(default_factory=list)
    stat_weights: dict[str, float] = field(default_factory=dict)
    meta_multiplier: float | None = None
    total_auctions: int = 0
    # Bid-validated fields
    price_low: float = 0.0
    price_high: float = 0.0
    bid_confidence_tier: int = 3
    validated_bid_count: int = 0
    auctions_with_bids: int = 0
    bid_values_used: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "estimatedPrice": round(self.estimated_price, 1),
            "priceLow": round(self.price_low, 1),
            "priceHigh": round(self.price_high, 1),
            "confidence": self.confidence,
            "bidConfidenceTier": self.bid_confidence_tier,
            "comparableCount": self.comparable_count,
            "archetype": self.archetype,
            "comparables": [c.to_dict() for c in self.comparables],
            "statWeights": self.stat_weights,
            "metaMultiplier": self.meta_multiplier,
            "totalAuctions": self.total_auctions,
            "validatedBidCount": self.validated_bid_count,
            "auctionsWithBids": self.auctions_with_bids,
            "bidValuesUsed": self.bid_values_used,
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
    Listings above the P75 price threshold get a gentler 120-day decay;
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


def _confidence_level(comparable_count: int, total_auctions: int) -> ConfidenceLevel:
    """Determine confidence from comparables and market volume.

    Volume can only LOWER confidence, never raise it.
    Even with many comparables, a thin market suggests niche weapon.
    """
    if comparable_count >= 10 and total_auctions >= _VOLUME_HIGH:
        return ConfidenceLevel.HIGH
    if comparable_count >= 5 and total_auctions >= _VOLUME_MEDIUM:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


# ---------------------------------------------------------------------------
# Shared comparables computation
# ---------------------------------------------------------------------------

def _compute_comparables(
    positive_attrs: list[AttributeInput],
    negative_attr: AttributeInput | None,
    re_rolls: int,
    auctions: list[Auction],
    disposition: int,
) -> tuple[list[SimilarityResult], dict[str, float], Archetype]:
    """Compute comparable auctions via similarity scoring.

    Returns (scored_results, stat_weights, target_archetype).
    Shared by estimate_price() and estimate_price_with_bids().
    """
    weights = compute_stat_weights(auctions)

    target_vector = build_stat_vector_from_raw(
        positive_attrs=positive_attrs,
        negative_attr=negative_attr,
        stat_weights=weights,
        disposition=disposition,
    )

    target_pos_names = [a.url_name for a in positive_attrs]
    target_archetype = classify_attributes(target_pos_names)
    target_neg_names = {negative_attr.url_name} if negative_attr else set()

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

    return scored, weights, target_archetype


def _weighted_average_price(
    scored: list[SimilarityResult],
    auctions: list[Auction],
) -> tuple[float, list[tuple[float, float, float]]]:
    """Compute weighted average price from scored comparables.

    Returns (estimated_price, filtered_tuples).
    filtered_tuples: list of (price, similarity, age_factor) after IQR removal.
    """
    price_threshold = _compute_price_threshold(auctions)

    price_tuples: list[tuple[float, float, float]] = []
    for sr in scored:
        price = get_effective_price(sr.auction)
        if price is None or price <= 0:
            continue
        af = _age_factor(sr.auction, price, price_threshold)
        price_tuples.append((price, sr.similarity, af))

    filtered = _remove_outliers(price_tuples)

    numerator = sum(p * s * a for p, s, a in filtered)
    denominator = sum(s * a for _, s, a in filtered)

    estimated = numerator / denominator if denominator > 0 else 0.0
    return estimated, filtered


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_price(
    positive_attrs: list[AttributeInput],
    negative_attr: AttributeInput | None,
    re_rolls: int,
    auctions: list[Auction],
    disposition: int,
    meta_multiplier: float | None = None,
) -> PriceEstimate:
    """Similarity-based price estimation (no bid data).

    Pipeline:
    1. Compute comparable auctions via similarity scoring
    2. Weighted average price with IQR outlier removal and age decay
    """
    scored, weights, target_archetype = _compute_comparables(
        positive_attrs, negative_attr, re_rolls, auctions, disposition,
    )

    estimated, filtered = _weighted_average_price(scored, auctions)

    if meta_multiplier is not None:
        estimated *= meta_multiplier

    scored.sort(key=lambda sr: sr.similarity, reverse=True)
    top_comparables = scored[:_MAX_COMPARABLES]

    return PriceEstimate(
        estimated_price=estimated,
        confidence=_confidence_level(len(filtered), len(auctions)),
        comparable_count=len(filtered),
        archetype=target_archetype,
        comparables=top_comparables,
        stat_weights=weights,
        meta_multiplier=meta_multiplier,
        total_auctions=len(auctions),
    )


def estimate_price_with_bids(
    positive_attrs: list[AttributeInput],
    negative_attr: AttributeInput | None,
    re_rolls: int,
    auctions: list[Auction],
    disposition: int,
    bid_data: dict[str, list[Bid]],
    meta_multiplier: float | None = None,
) -> PriceEstimate:
    """Bid-validated price estimation with tiered confidence.

    1. Compute comparable auctions via similarity scoring
    2. Validate bids for each comparable auction
    3. Determine confidence tier and price range from validated bids
    4. Tier 3 fallback: IQR-filtered weighted average from buyout prices
    """
    scored, weights, target_archetype = _compute_comparables(
        positive_attrs, negative_attr, re_rolls, auctions, disposition,
    )

    # Validate bids for comparable auctions
    validations = []
    auctions_with_bids = 0
    for sr in scored:
        bids = bid_data.get(sr.auction.id, [])
        validation = BidValidator.validate_auction_bids(sr.auction, bids)
        validations.append(validation)
        if bids:
            auctions_with_bids += 1

    summary = BidValidator.summarize_validations(validations)

    # Compute fallback price via weighted average (used for Tier 3 and as baseline)
    fallback_price, filtered = _weighted_average_price(scored, auctions)

    # Determine price range based on tier
    if summary.overall_tier <= BidConfidenceTier.MEDIUM and summary.bid_values_used:
        # Tier 1 or 2: bid-derived range
        price_low = summary.price_low
        price_high = summary.price_high
        estimated = (price_low + price_high) / 2.0
    else:
        # Tier 3: fallback to IQR bounds from comparable buyout prices
        estimated = fallback_price
        if len(filtered) >= 4:
            prices = sorted(r[0] for r in filtered)
            q1, _q2, q3 = quantiles(prices, n=4)
            price_low = q1
            price_high = q3
        elif filtered:
            price_low = min(r[0] for r in filtered)
            price_high = max(r[0] for r in filtered)
        else:
            price_low = 0.0
            price_high = 0.0

    # Apply meta tier multiplier
    if meta_multiplier is not None:
        estimated *= meta_multiplier
        price_low *= meta_multiplier
        price_high *= meta_multiplier

    # Map BidConfidenceTier to ConfidenceLevel
    tier_to_confidence = {
        BidConfidenceTier.HIGH: ConfidenceLevel.HIGH,
        BidConfidenceTier.MEDIUM: ConfidenceLevel.MEDIUM,
        BidConfidenceTier.LOW: ConfidenceLevel.LOW,
    }
    confidence = tier_to_confidence[summary.overall_tier]

    scored.sort(key=lambda sr: sr.similarity, reverse=True)
    top_comparables = scored[:_MAX_COMPARABLES]

    return PriceEstimate(
        estimated_price=estimated,
        price_low=price_low,
        price_high=price_high,
        confidence=confidence,
        bid_confidence_tier=int(summary.overall_tier),
        comparable_count=len(filtered),
        archetype=target_archetype,
        comparables=top_comparables,
        stat_weights=weights,
        meta_multiplier=meta_multiplier,
        total_auctions=len(auctions),
        validated_bid_count=summary.total_validated_bids,
        auctions_with_bids=auctions_with_bids,
        bid_values_used=summary.bid_values_used,
    )
