import sys
import os
from datetime import datetime, timezone
from statistics import quantiles

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from backend.evaluation.price_estimator import (
        _confidence_level, ConfidenceLevel, PriceEstimate,
        _VOLUME_HIGH, _VOLUME_MEDIUM,
        estimate_price_with_bids,
    )
    from backend.core.models import Auction, AuctionOwner, AttributeInput, RivenAttribute
except ImportError:
    from evaluation.price_estimator import (
        _confidence_level, ConfidenceLevel, PriceEstimate,
        _VOLUME_HIGH, _VOLUME_MEDIUM,
        estimate_price_with_bids,
    )
    from core.models import Auction, AuctionOwner, AttributeInput, RivenAttribute


# ---------------------------------------------------------------------------
# _confidence_level unit tests (volume-aware)
# ---------------------------------------------------------------------------

class TestConfidenceLevel:
    def test_high_comparables_high_volume(self):
        """Many comparables + healthy market → HIGH."""
        assert _confidence_level(12, 50) == ConfidenceLevel.HIGH

    def test_high_comparables_low_volume(self):
        """Many comparables but thin market → volume drags to LOW."""
        assert _confidence_level(12, 4) == ConfidenceLevel.LOW

    def test_medium_comparables_medium_volume(self):
        """Moderate comparables + adequate market → MEDIUM."""
        assert _confidence_level(7, 20) == ConfidenceLevel.MEDIUM

    def test_medium_comparables_low_volume(self):
        """Moderate comparables but thin market → LOW."""
        assert _confidence_level(7, 10) == ConfidenceLevel.LOW

    def test_zero_comparables_high_volume(self):
        """No comparables regardless of volume → LOW."""
        assert _confidence_level(0, 100) == ConfidenceLevel.LOW

    def test_boundary_high(self):
        """Exact boundary values for HIGH."""
        assert _confidence_level(10, _VOLUME_HIGH) == ConfidenceLevel.HIGH

    def test_boundary_medium(self):
        """Exact boundary values for MEDIUM."""
        assert _confidence_level(5, _VOLUME_MEDIUM) == ConfidenceLevel.MEDIUM

    def test_just_below_high_threshold(self):
        """One below HIGH comparable threshold → MEDIUM."""
        assert _confidence_level(9, 50) == ConfidenceLevel.MEDIUM

    def test_volume_cannot_raise_confidence(self):
        """High volume with few comparables stays LOW."""
        assert _confidence_level(3, 200) == ConfidenceLevel.LOW


# ---------------------------------------------------------------------------
# PriceEstimate.to_dict tests
# ---------------------------------------------------------------------------

class TestPriceEstimateOutput:
    def test_total_auctions_in_to_dict(self):
        """total_auctions field appears in serialized output."""
        estimate = PriceEstimate(
            estimated_price=150.0,
            confidence=ConfidenceLevel.MEDIUM,
            comparable_count=8,
            archetype="status",
            total_auctions=42,
        )
        d = estimate.to_dict()
        assert "totalAuctions" in d
        assert d["totalAuctions"] == 42

    def test_total_auctions_default_zero(self):
        """total_auctions defaults to 0 when not set."""
        estimate = PriceEstimate(
            estimated_price=0.0,
            confidence=ConfidenceLevel.LOW,
            comparable_count=0,
            archetype="other",
        )
        assert estimate.total_auctions == 0
        assert estimate.to_dict()["totalAuctions"] == 0


# ---------------------------------------------------------------------------
# Tier 3 fallback price range (estimate_price_with_bids, no bids)
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)

# Target riven attributes used across all Tier 3 tests.
_TARGET_ATTRS = [
    AttributeInput(url_name="critical_chance", value=150.0),
    AttributeInput(url_name="multishot", value=110.0),
]


def _make_pe_auction(
    auction_id: str,
    buyout: int,
    pos_attrs: list[tuple[str, float]] | None = None,
) -> Auction:
    """Minimal auction for price estimator pipeline tests."""
    if pos_attrs is None:
        pos_attrs = [("critical_chance", 150.0), ("multishot", 110.0)]
    attributes = [
        RivenAttribute(url_name=name, value=val, positive=True)
        for name, val in pos_attrs
    ]
    return Auction(
        id=auction_id,
        weapon_url_name="braton_prime",
        weapon_display="Braton Prime",
        riven_name="Braton Test",
        starting_price=None,
        buyout_price=buyout,
        top_bid=None,
        mastery_level=8,
        mod_rank=8,
        re_rolls=0,
        polarity="madurai",
        attributes=attributes,
        owner=AuctionOwner(id="seller1", reputation=5, ingame_name="TestSeller"),
        created=_NOW,
        updated=_NOW,
        url=f"https://warframe.market/auction/{auction_id}",
    )


class TestTier3PriceRange:
    """Tier 3 fallback: price_low/price_high must equal min/max of IQR-filtered prices.

    Tier 3 is triggered when bid_data is empty (no bids for any comparable
    auction), forcing the fallback path in estimate_price_with_bids().
    """

    def _run(
        self,
        auctions: list[Auction],
        meta_multiplier: float | None = None,
    ):
        """Run estimate with no bids to force Tier 3."""
        return estimate_price_with_bids(
            positive_attrs=_TARGET_ATTRS,
            negative_attr=None,
            re_rolls=0,
            auctions=auctions,
            disposition=3,
            bid_data={},
            meta_multiplier=meta_multiplier,
        )

    def test_range_equals_min_max_of_comparables(self):
        """price_low == min(buyouts), price_high == max(buyouts) of comparable auctions."""
        buyouts = [100, 200, 300, 400, 500]
        auctions = [_make_pe_auction(f"a{i}", b) for i, b in enumerate(buyouts)]

        result = self._run(auctions)

        assert result.price_low == pytest.approx(min(buyouts))
        assert result.price_high == pytest.approx(max(buyouts))

    def test_outlier_excluded_from_range(self):
        """An extreme price outlier removed by IQR should not appear in the range.

        Requires enough data points (~9) so the outlier shifts the IQR fence
        past itself — with only 4–5 points the fence widens too much to exclude it.
        """
        normal_prices = [100, 110, 120, 130, 140, 150, 160, 170]
        outlier_price = 1000
        auctions = [_make_pe_auction(f"a{i}", b) for i, b in enumerate(normal_prices + [outlier_price])]

        result = self._run(auctions)

        assert result.price_high < outlier_price
        assert result.price_low == pytest.approx(min(normal_prices))

    def test_single_comparable_low_equals_high(self):
        """One comparable auction → price_low == price_high == its buyout price."""
        comparable = _make_pe_auction("match", buyout=300)
        # These auctions have a completely different stat → cosine similarity = 0 → excluded
        mismatched = [
            _make_pe_auction(f"m{i}", buyout=999, pos_attrs=[("fire_rate_/_attack_speed", 10.0)])
            for i in range(3)
        ]

        result = self._run([comparable] + mismatched)

        assert result.price_low == result.price_high

    def test_no_comparables_gives_zero_range(self):
        """Empty auction list → price_low and price_high both 0.0."""
        result = self._run([])

        assert result.price_low == 0.0
        assert result.price_high == 0.0

    def test_meta_multiplier_scales_range(self):
        """meta_multiplier must scale both price_low and price_high."""
        auctions = [_make_pe_auction(f"a{i}", b) for i, b in enumerate([100, 300, 500])]
        multiplier = 1.5

        base = self._run(auctions)
        scaled = self._run(auctions, meta_multiplier=multiplier)

        assert scaled.price_low == pytest.approx(base.price_low * multiplier)
        assert scaled.price_high == pytest.approx(base.price_high * multiplier)

    def test_range_wider_than_old_q1_q3_boundaries(self):
        """Regression: range must use min/max, not Q1/Q3.

        For an evenly-spaced price series, min < Q1 and max > Q3, so if the
        old Q1/Q3 logic were still in place this test would fail.
        """
        buyouts = [100, 200, 300, 400, 500]
        auctions = [_make_pe_auction(f"a{i}", b) for i, b in enumerate(buyouts)]

        result = self._run(auctions)

        q1, _, q3 = quantiles(sorted(buyouts), n=4)
        # min/max must strictly dominate Q1/Q3
        assert result.price_low < q1    # 100 < Q1(~150)
        assert result.price_high > q3   # 500 > Q3(~450)
