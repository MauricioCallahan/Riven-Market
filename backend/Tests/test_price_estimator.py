import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from backend.evaluation.price_estimator import (
        _confidence_level, ConfidenceLevel, PriceEstimate,
        _VOLUME_HIGH, _VOLUME_MEDIUM,
    )
except ImportError:
    from evaluation.price_estimator import (
        _confidence_level, ConfidenceLevel, PriceEstimate,
        _VOLUME_HIGH, _VOLUME_MEDIUM,
    )


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
