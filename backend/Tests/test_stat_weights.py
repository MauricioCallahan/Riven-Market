import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from backend.evaluation.stat_weights import (
        compute_stat_weights, ELEMENTAL_PREFERENCE, _apply_elemental_preference,
    )
    from backend.core.models import Auction, RivenAttribute
except ImportError:
    from evaluation.stat_weights import (
        compute_stat_weights, ELEMENTAL_PREFERENCE, _apply_elemental_preference,
    )
    from core.models import Auction, AuctionOwner, RivenAttribute

from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_auction(
    pos_attrs: list[tuple[str, float]],
    buyout: int = 100,
) -> Auction:
    """Minimal auction for stat weight tests."""
    attributes = [
        RivenAttribute(url_name=name, value=val, positive=True)
        for name, val in pos_attrs
    ]
    now = datetime.now(timezone.utc)
    return Auction(
        id="test",
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
        created=now,
        updated=now,
        url="https://warframe.market/auction/test",
    )


# ---------------------------------------------------------------------------
# _apply_elemental_preference unit tests
# ---------------------------------------------------------------------------

class TestApplyElementalPreference:
    def test_elemental_ordering(self):
        """Toxin > Heat > Cold == Electric after preference applied."""
        weights = {
            "toxin_damage": 0.25,
            "heat_damage": 0.25,
            "cold_damage": 0.25,
            "electric_damage": 0.25,
        }
        result = _apply_elemental_preference(dict(weights))
        assert result["toxin_damage"] > result["heat_damage"]
        assert result["heat_damage"] > result["cold_damage"]
        assert abs(result["cold_damage"] - result["electric_damage"]) < 1e-9

    def test_preserves_sum(self):
        """Weights still sum to ~1.0 after elemental preference."""
        weights = {
            "toxin_damage": 0.2,
            "heat_damage": 0.2,
            "cold_damage": 0.2,
            "electric_damage": 0.2,
            "critical_chance": 0.2,
        }
        result = _apply_elemental_preference(dict(weights))
        assert abs(sum(result.values()) - 1.0) < 1e-9

    def test_non_elemental_only_changes_via_renormalization(self):
        """Non-elemental stats are only affected by renormalization, not boosted."""
        weights = {
            "critical_chance": 0.5,
            "toxin_damage": 0.25,
            "cold_damage": 0.25,
        }
        result = _apply_elemental_preference(dict(weights))
        # Toxin gets boosted, so crit_chance's share shrinks via renormalization
        assert result["critical_chance"] < 0.5

    def test_no_elementals_no_change(self):
        """Weights with no elemental stats are unchanged."""
        weights = {"critical_chance": 0.5, "multishot": 0.5}
        result = _apply_elemental_preference(dict(weights))
        assert abs(result["critical_chance"] - 0.5) < 1e-9
        assert abs(result["multishot"] - 0.5) < 1e-9

    def test_empty_weights(self):
        """Empty dict returns empty dict."""
        result = _apply_elemental_preference({})
        assert result == {}


# ---------------------------------------------------------------------------
# compute_stat_weights integration tests
# ---------------------------------------------------------------------------

class TestComputeStatWeightsElemental:
    def test_equal_frequency_elementals_differentiated(self):
        """With equal frequency in top slice, elemental preference differentiates."""
        # All auctions have all four elementals → equal frequency in top 30%
        auctions = [
            _make_auction(
                pos_attrs=[
                    ("toxin_damage", 100.0), ("heat_damage", 80.0),
                    ("cold_damage", 60.0), ("electric_damage", 50.0),
                ],
                buyout=200,
            )
            for _ in range(20)
        ]

        weights = compute_stat_weights(auctions)
        assert weights["toxin_damage"] > weights["heat_damage"]
        assert weights["heat_damage"] > weights["cold_damage"]
        assert abs(weights["cold_damage"] - weights["electric_damage"]) < 1e-9

    def test_fallback_equal_weights_applies_preference(self):
        """With <15 auctions, equal weights still show elemental differentiation."""
        auctions = [
            _make_auction(
                pos_attrs=[("toxin_damage", 100.0), ("heat_damage", 80.0),
                           ("cold_damage", 60.0), ("electric_damage", 50.0)],
            )
            for _ in range(5)
        ]
        weights = compute_stat_weights(auctions)
        assert weights["toxin_damage"] > weights["heat_damage"]
        assert weights["heat_damage"] > weights["cold_damage"]
        assert abs(weights["cold_damage"] - weights["electric_damage"]) < 1e-9
