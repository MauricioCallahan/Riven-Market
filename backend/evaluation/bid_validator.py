"""
Bid validation engine for the tiered confidence system.

Classifies auction bid histories into confidence tiers:
  Tier 1 (HIGH)   — 2+ validated bids from distinct reputable users
  Tier 2 (MEDIUM) — exactly 1 validated bid from a reputable user
  Tier 3 (LOW)    — no validated bids; caller falls back to buyout prices
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum

from core.models import Auction, Bid


# ---------------------------------------------------------------------------
# Enums & Constants
# ---------------------------------------------------------------------------

class BidConfidenceTier(IntEnum):
    """Confidence tier based on bid validation quality."""
    HIGH = 1
    MEDIUM = 2
    LOW = 3


# Bidders must have reputation strictly greater than this value.
MIN_BIDDER_REPUTATION = 0

# All bids placed within this window are flagged as suspicious.
MIN_BID_TIMESTAMP_SPREAD_SECONDS = 30

# A single bid jump exceeding this ratio over the previous bid is suspicious.
MAX_BID_JUMP_RATIO = 5.0


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ValidatedBid:
    """A bid that passed all validation filters."""
    auction_id: str
    bid_value: int
    bidder_id: str
    bidder_reputation: int
    bidder_name: str
    created: datetime | None


@dataclass
class AuctionBidValidation:
    """Validation result for a single auction's bid history."""
    auction_id: str
    tier: BidConfidenceTier
    validated_bids: list[ValidatedBid]
    raw_bid_count: int
    rejection_reasons: list[str] = field(default_factory=list)


@dataclass
class BidValidationSummary:
    """Aggregate validation across all comparable auctions."""
    overall_tier: BidConfidenceTier
    auctions_analyzed: int
    total_validated_bids: int
    bid_values_used: list[int]
    price_low: float
    price_high: float
    auction_validations: list[AuctionBidValidation] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

class BidValidator:
    """Stateless bid validation — classifies auctions into confidence tiers."""

    @staticmethod
    def validate_auction_bids(
        auction: Auction,
        bids: list[Bid],
    ) -> AuctionBidValidation:
        """Validate bids for a single auction against the tiered criteria.

        Filters applied in order:
        1. Self-bid: bidder_id != seller owner.id
        2. Reputation: bidder reputation > MIN_BIDDER_REPUTATION
        3. Distinct users: keep highest bid per user_id
        4. Competitive bidding: no single jump > MAX_BID_JUMP_RATIO × previous
        5. Timestamp spread: not all bids within MIN_BID_TIMESTAMP_SPREAD_SECONDS
        """
        reasons: list[str] = []

        if not bids:
            return AuctionBidValidation(
                auction_id=auction.id,
                tier=BidConfidenceTier.LOW,
                validated_bids=[],
                raw_bid_count=0,
                rejection_reasons=["no bids"],
            )

        seller_id = auction.owner.id

        # 1 & 2: Filter out self-bids and low-reputation bidders
        eligible: list[Bid] = []
        for bid in bids:
            if bid.user_id == seller_id:
                reasons.append(f"bid {bid.id}: self-bid (bidder == seller)")
                continue
            if bid.user_reputation <= MIN_BIDDER_REPUTATION:
                reasons.append(
                    f"bid {bid.id}: low reputation ({bid.user_reputation})"
                )
                continue
            eligible.append(bid)

        if not eligible:
            return AuctionBidValidation(
                auction_id=auction.id,
                tier=BidConfidenceTier.LOW,
                validated_bids=[],
                raw_bid_count=len(bids),
                rejection_reasons=reasons or ["all bids failed validation"],
            )

        # 3: Distinct users — keep highest bid per user_id
        best_by_user: dict[str, Bid] = {}
        for bid in eligible:
            existing = best_by_user.get(bid.user_id)
            if existing is None or bid.value > existing.value:
                best_by_user[bid.user_id] = bid
        distinct_bids = list(best_by_user.values())

        # 4: Competitive bidding check — sort by value ascending
        sorted_by_value = sorted(distinct_bids, key=lambda b: b.value)
        competitive = True
        if len(sorted_by_value) >= 2:
            for i in range(1, len(sorted_by_value)):
                prev_val = sorted_by_value[i - 1].value
                curr_val = sorted_by_value[i].value
                if prev_val > 0 and curr_val / prev_val > MAX_BID_JUMP_RATIO:
                    competitive = False
                    reasons.append(
                        f"non-competitive: {curr_val} is {curr_val / prev_val:.1f}x "
                        f"the previous bid {prev_val}"
                    )
                    break

        # 5: Timestamp spread check
        timestamps = [
            b.created for b in distinct_bids if b.created is not None
        ]
        spread_ok = True
        if len(timestamps) >= 2:
            timestamps.sort()
            total_span = (timestamps[-1] - timestamps[0]).total_seconds()
            if total_span < MIN_BID_TIMESTAMP_SPREAD_SECONDS:
                spread_ok = False
                reasons.append(
                    f"suspicious timing: all bids within {total_span:.0f}s"
                )

        # Build validated bids list
        validated = [
            ValidatedBid(
                auction_id=auction.id,
                bid_value=bid.value,
                bidder_id=bid.user_id,
                bidder_reputation=bid.user_reputation,
                bidder_name=bid.user_ingame_name,
                created=bid.created,
            )
            for bid in distinct_bids
        ]

        # Classify tier
        distinct_count = len(distinct_bids)
        if distinct_count >= 2 and competitive and spread_ok:
            tier = BidConfidenceTier.HIGH
        elif distinct_count >= 1:
            tier = BidConfidenceTier.MEDIUM
        else:
            tier = BidConfidenceTier.LOW

        return AuctionBidValidation(
            auction_id=auction.id,
            tier=tier,
            validated_bids=validated,
            raw_bid_count=len(bids),
            rejection_reasons=reasons,
        )

    @staticmethod
    def summarize_validations(
        validations: list[AuctionBidValidation],
    ) -> BidValidationSummary:
        """Aggregate per-auction validations into an overall summary.

        Overall tier = best (lowest enum value) across all auctions.
        Price range depends on tier:
          Tier 1: min/max of bid values (±10% if identical)
          Tier 2: bid × 0.8 to bid × 1.3 (wider range, less certainty)
          Tier 3: 0.0/0.0 — caller computes from buyout IQR
        """
        if not validations:
            return BidValidationSummary(
                overall_tier=BidConfidenceTier.LOW,
                auctions_analyzed=0,
                total_validated_bids=0,
                bid_values_used=[],
                price_low=0.0,
                price_high=0.0,
            )

        # Collect all validated bid values and determine best tier
        all_bid_values: list[int] = []
        best_tier = BidConfidenceTier.LOW
        for v in validations:
            if v.tier < best_tier:
                best_tier = v.tier
            for vb in v.validated_bids:
                all_bid_values.append(vb.bid_value)

        total_validated = len(all_bid_values)

        # Compute price range based on overall tier
        price_low = 0.0
        price_high = 0.0

        if best_tier == BidConfidenceTier.HIGH and all_bid_values:
            price_low = float(min(all_bid_values))
            price_high = float(max(all_bid_values))
            # Widen by ±10% if all bids are identical
            if price_low == price_high:
                price_low *= 0.9
                price_high *= 1.1
        elif best_tier == BidConfidenceTier.MEDIUM and all_bid_values:
            # Single-bid territory — wider range
            mid = float(max(all_bid_values))
            price_low = mid * 0.8
            price_high = mid * 1.3
        # Tier 3: leave at 0.0/0.0 — caller uses buyout fallback

        return BidValidationSummary(
            overall_tier=best_tier,
            auctions_analyzed=len(validations),
            total_validated_bids=total_validated,
            bid_values_used=sorted(all_bid_values),
            price_low=price_low,
            price_high=price_high,
            auction_validations=validations,
        )
