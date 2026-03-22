"""Tests for the bid validation engine (evaluation/bid_validator.py)."""

import sys
import os
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.models import Auction, AuctionOwner, Bid, RivenAttribute
from evaluation.bid_validator import (
    BidConfidenceTier,
    BidValidator,
    MIN_BID_TIMESTAMP_SPREAD_SECONDS,
    MAX_BID_JUMP_RATIO,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SELLER = AuctionOwner(id="seller_001", reputation=10, ingame_name="TestSeller")
NOW = datetime.now(timezone.utc)


def _make_auction(auction_id: str = "auc_001", owner: AuctionOwner = SELLER) -> Auction:
    """Minimal auction for bid validation tests."""
    return Auction(
        id=auction_id,
        weapon_url_name="braton_prime",
        weapon_display="Braton Prime",
        riven_name="Braton Crita-gelitis",
        starting_price=100,
        buyout_price=500,
        top_bid=None,
        mastery_level=8,
        mod_rank=8,
        re_rolls=0,
        polarity="madurai",
        attributes=[
            RivenAttribute(url_name="critical_chance", value=180.0, positive=True),
            RivenAttribute(url_name="multishot", value=110.0, positive=True),
        ],
        owner=owner,
        created=NOW,
        updated=NOW,
        url="https://warframe.market/auction/auc_001",
    )


def _make_bid(
    bid_id: str = "bid_001",
    value: int = 200,
    user_id: str = "bidder_001",
    reputation: int = 5,
    name: str = "Bidder1",
    created: datetime | None = None,
) -> Bid:
    """Minimal bid for validation tests."""
    return Bid(
        id=bid_id,
        value=value,
        user_id=user_id,
        user_reputation=reputation,
        user_ingame_name=name,
        created=created or NOW,
        updated=created or NOW,
    )


# ---------------------------------------------------------------------------
# validate_auction_bids — single auction classification
# ---------------------------------------------------------------------------

class TestValidateAuctionBids:
    """Tests for BidValidator.validate_auction_bids()."""

    def test_no_bids_returns_tier_3(self):
        auction = _make_auction()
        result = BidValidator.validate_auction_bids(auction, [])

        assert result.tier == BidConfidenceTier.LOW
        assert result.raw_bid_count == 0
        assert result.validated_bids == []

    def test_self_bid_rejected(self):
        """Bid from the seller's own account should be rejected."""
        auction = _make_auction()
        bid = _make_bid(user_id=SELLER.id)  # bidder == seller

        result = BidValidator.validate_auction_bids(auction, [bid])

        assert result.tier == BidConfidenceTier.LOW
        assert result.validated_bids == []
        assert any("self-bid" in r for r in result.rejection_reasons)

    def test_zero_reputation_rejected(self):
        """Bidder with reputation == 0 should be rejected (spec says > 0)."""
        auction = _make_auction()
        bid = _make_bid(reputation=0)

        result = BidValidator.validate_auction_bids(auction, [bid])

        assert result.tier == BidConfidenceTier.LOW
        assert result.validated_bids == []
        assert any("low reputation" in r for r in result.rejection_reasons)

    def test_single_reputable_bid_tier_2(self):
        """One valid bid from a reputable non-seller user → Tier 2."""
        auction = _make_auction()
        bid = _make_bid(value=300, reputation=5)

        result = BidValidator.validate_auction_bids(auction, [bid])

        assert result.tier == BidConfidenceTier.MEDIUM
        assert len(result.validated_bids) == 1
        assert result.validated_bids[0].bid_value == 300

    def test_two_distinct_reputable_bids_tier_1(self):
        """Two bids from distinct reputable users → Tier 1."""
        auction = _make_auction()
        bid1 = _make_bid(
            bid_id="b1", value=200, user_id="u1", reputation=5,
            created=NOW - timedelta(hours=2),
        )
        bid2 = _make_bid(
            bid_id="b2", value=250, user_id="u2", reputation=3,
            created=NOW - timedelta(hours=1),
        )

        result = BidValidator.validate_auction_bids(auction, [bid1, bid2])

        assert result.tier == BidConfidenceTier.HIGH
        assert len(result.validated_bids) == 2

    def test_two_bids_same_user_tier_2(self):
        """Two bids from the same user → only 1 distinct, Tier 2."""
        auction = _make_auction()
        bid1 = _make_bid(bid_id="b1", value=200, user_id="u1")
        bid2 = _make_bid(bid_id="b2", value=250, user_id="u1")

        result = BidValidator.validate_auction_bids(auction, [bid1, bid2])

        assert result.tier == BidConfidenceTier.MEDIUM
        assert len(result.validated_bids) == 1
        # Should keep the highest bid
        assert result.validated_bids[0].bid_value == 250

    def test_non_competitive_jump_downgrades_to_tier_2(self):
        """A massive price jump (>5x) flags as non-competitive → Tier 2."""
        auction = _make_auction()
        bid1 = _make_bid(
            bid_id="b1", value=10, user_id="u1", reputation=5,
            created=NOW - timedelta(hours=2),
        )
        bid2 = _make_bid(
            bid_id="b2", value=100, user_id="u2", reputation=5,
            created=NOW - timedelta(hours=1),
        )
        # 100 / 10 = 10x > MAX_BID_JUMP_RATIO (5.0)

        result = BidValidator.validate_auction_bids(auction, [bid1, bid2])

        assert result.tier == BidConfidenceTier.MEDIUM
        assert any("non-competitive" in r for r in result.rejection_reasons)

    def test_suspicious_timing_downgrades_to_tier_2(self):
        """All bids within 30s of each other → flagged as suspicious → Tier 2."""
        auction = _make_auction()
        bid1 = _make_bid(
            bid_id="b1", value=200, user_id="u1", reputation=5,
            created=NOW,
        )
        bid2 = _make_bid(
            bid_id="b2", value=220, user_id="u2", reputation=5,
            created=NOW + timedelta(seconds=5),
        )

        result = BidValidator.validate_auction_bids(auction, [bid1, bid2])

        assert result.tier == BidConfidenceTier.MEDIUM
        assert any("suspicious timing" in r for r in result.rejection_reasons)

    def test_mixed_valid_and_invalid_bids(self):
        """3 bids: 1 from seller, 1 zero-rep, 1 reputable → Tier 2."""
        auction = _make_auction()
        bids = [
            _make_bid(bid_id="b1", user_id=SELLER.id, value=100, reputation=10),
            _make_bid(bid_id="b2", user_id="u2", value=200, reputation=0),
            _make_bid(bid_id="b3", user_id="u3", value=300, reputation=5),
        ]

        result = BidValidator.validate_auction_bids(auction, bids)

        assert result.tier == BidConfidenceTier.MEDIUM
        assert len(result.validated_bids) == 1
        assert result.validated_bids[0].bid_value == 300
        assert result.raw_bid_count == 3

    def test_competitive_bids_within_ratio(self):
        """Bids within the 5x ratio should pass the competitive check."""
        auction = _make_auction()
        bid1 = _make_bid(
            bid_id="b1", value=100, user_id="u1", reputation=5,
            created=NOW - timedelta(hours=2),
        )
        bid2 = _make_bid(
            bid_id="b2", value=400, user_id="u2", reputation=5,
            created=NOW - timedelta(hours=1),
        )
        # 400 / 100 = 4.0 < MAX_BID_JUMP_RATIO (5.0) → passes

        result = BidValidator.validate_auction_bids(auction, [bid1, bid2])

        assert result.tier == BidConfidenceTier.HIGH

    def test_negative_reputation_rejected(self):
        """Bidder with negative reputation should be rejected."""
        auction = _make_auction()
        bid = _make_bid(reputation=-1)

        result = BidValidator.validate_auction_bids(auction, [bid])

        assert result.tier == BidConfidenceTier.LOW


# ---------------------------------------------------------------------------
# summarize_validations — aggregate across auctions
# ---------------------------------------------------------------------------

class TestSummarizeValidations:
    """Tests for BidValidator.summarize_validations()."""

    def test_empty_validations(self):
        summary = BidValidator.summarize_validations([])

        assert summary.overall_tier == BidConfidenceTier.LOW
        assert summary.auctions_analyzed == 0
        assert summary.total_validated_bids == 0
        assert summary.price_low == 0.0
        assert summary.price_high == 0.0

    def test_all_tier_3_overall_tier_3(self):
        auction = _make_auction()
        v1 = BidValidator.validate_auction_bids(auction, [])
        v2 = BidValidator.validate_auction_bids(auction, [])

        summary = BidValidator.summarize_validations([v1, v2])

        assert summary.overall_tier == BidConfidenceTier.LOW
        assert summary.price_low == 0.0
        assert summary.price_high == 0.0

    def test_best_tier_wins(self):
        """Mix of Tier 1 and Tier 3 → overall Tier 1."""
        auction = _make_auction()

        # Tier 1 auction
        bid1 = _make_bid(
            bid_id="b1", value=200, user_id="u1", reputation=5,
            created=NOW - timedelta(hours=2),
        )
        bid2 = _make_bid(
            bid_id="b2", value=250, user_id="u2", reputation=3,
            created=NOW - timedelta(hours=1),
        )
        v1 = BidValidator.validate_auction_bids(auction, [bid1, bid2])

        # Tier 3 auction (no bids)
        v2 = BidValidator.validate_auction_bids(auction, [])

        summary = BidValidator.summarize_validations([v1, v2])

        assert summary.overall_tier == BidConfidenceTier.HIGH
        assert summary.total_validated_bids == 2

    def test_tier_1_price_range(self):
        """Tier 1: price range = min/max of bid values."""
        auction = _make_auction()
        bid1 = _make_bid(
            bid_id="b1", value=200, user_id="u1", reputation=5,
            created=NOW - timedelta(hours=2),
        )
        bid2 = _make_bid(
            bid_id="b2", value=400, user_id="u2", reputation=3,
            created=NOW - timedelta(hours=1),
        )
        v = BidValidator.validate_auction_bids(auction, [bid1, bid2])
        summary = BidValidator.summarize_validations([v])

        assert summary.price_low == 200.0
        assert summary.price_high == 400.0

    def test_tier_1_identical_bids_widened(self):
        """Tier 1 with identical bid values → ±10% widening."""
        auction = _make_auction()
        bid1 = _make_bid(
            bid_id="b1", value=300, user_id="u1", reputation=5,
            created=NOW - timedelta(hours=2),
        )
        bid2 = _make_bid(
            bid_id="b2", value=300, user_id="u2", reputation=3,
            created=NOW - timedelta(hours=1),
        )
        v = BidValidator.validate_auction_bids(auction, [bid1, bid2])
        summary = BidValidator.summarize_validations([v])

        assert summary.price_low == pytest.approx(270.0)
        assert summary.price_high == pytest.approx(330.0)

    def test_tier_2_price_range(self):
        """Tier 2: bid × 0.8 to bid × 1.3."""
        auction = _make_auction()
        bid = _make_bid(value=500, reputation=5)
        v = BidValidator.validate_auction_bids(auction, [bid])
        summary = BidValidator.summarize_validations([v])

        assert summary.overall_tier == BidConfidenceTier.MEDIUM
        assert summary.price_low == pytest.approx(400.0)
        assert summary.price_high == pytest.approx(650.0)

    def test_bid_values_sorted(self):
        """bid_values_used should be sorted ascending."""
        auction = _make_auction()
        bid1 = _make_bid(
            bid_id="b1", value=400, user_id="u1", reputation=5,
            created=NOW - timedelta(hours=2),
        )
        bid2 = _make_bid(
            bid_id="b2", value=200, user_id="u2", reputation=3,
            created=NOW - timedelta(hours=1),
        )
        v = BidValidator.validate_auction_bids(auction, [bid1, bid2])
        summary = BidValidator.summarize_validations([v])

        assert summary.bid_values_used == [200, 400]
