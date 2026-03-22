import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from backend.evaluation.similarity import (
        _negative_adjustment, _cosine_similarity, _reroll_penalty,
        _roll_quality_multiplier,
        compute_similarity, NEGATIVE_QUALITY, _DEFAULT_NEGATIVE_QUALITY,
    )
    from backend.core.models import Auction, RivenAttribute
except ImportError:
    from evaluation.similarity import (
        _negative_adjustment, _cosine_similarity, _reroll_penalty,
        _roll_quality_multiplier,
        compute_similarity, NEGATIVE_QUALITY, _DEFAULT_NEGATIVE_QUALITY,
    )
    from core.models import Auction, AuctionOwner, RivenAttribute

from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# _negative_adjustment unit tests
# ---------------------------------------------------------------------------

class TestNegativeAdjustment:
    def test_shared_desirable_zoom(self):
        """Shared -zoom gives the full zoom bonus."""
        result = _negative_adjustment({"zoom"}, {"zoom"})
        assert result == NEGATIVE_QUALITY["zoom"]  # +0.08

    def test_shared_desirable_recoil(self):
        """Shared -recoil gives the recoil bonus."""
        result = _negative_adjustment({"recoil"}, {"recoil"})
        assert result == NEGATIVE_QUALITY["recoil"]  # +0.06

    def test_shared_undesirable_crit_chance(self):
        """Shared -crit_chance applies the full penalty."""
        result = _negative_adjustment({"critical_chance"}, {"critical_chance"})
        assert result == NEGATIVE_QUALITY["critical_chance"]  # -0.15

    def test_shared_undesirable_damage(self):
        """Shared -base_damage applies the full penalty."""
        result = _negative_adjustment(
            {"base_damage_/_melee_damage"}, {"base_damage_/_melee_damage"}
        )
        assert result == NEGATIVE_QUALITY["base_damage_/_melee_damage"]  # -0.12

    def test_candidate_only_bad_negative(self):
        """Candidate has -damage, target doesn't → full penalty."""
        result = _negative_adjustment(set(), {"base_damage_/_melee_damage"})
        assert result == NEGATIVE_QUALITY["base_damage_/_melee_damage"]  # -0.12

    def test_candidate_only_good_negative_clamped(self):
        """Candidate has -zoom, target doesn't → clamped to 0 (no unearned bonus)."""
        result = _negative_adjustment(set(), {"zoom"})
        assert result == 0.0

    def test_target_only_negative_no_effect(self):
        """Target has -zoom but candidate doesn't → no adjustment."""
        result = _negative_adjustment({"zoom"}, set())
        assert result == 0.0

    def test_unknown_stat_default_penalty(self):
        """Unknown negative stat falls back to _DEFAULT_NEGATIVE_QUALITY."""
        result = _negative_adjustment(set(), {"some_unknown_stat"})
        assert result == _DEFAULT_NEGATIVE_QUALITY  # -0.03

    def test_unknown_stat_shared(self):
        """Shared unknown negative also uses default."""
        result = _negative_adjustment({"some_unknown_stat"}, {"some_unknown_stat"})
        assert result == _DEFAULT_NEGATIVE_QUALITY

    def test_empty_negatives(self):
        """No negatives on either side → 0.0."""
        result = _negative_adjustment(set(), set())
        assert result == 0.0

    def test_neutral_negative_shared(self):
        """Shared neutral negative (magazine_capacity = 0.0) → 0.0."""
        result = _negative_adjustment({"magazine_capacity"}, {"magazine_capacity"})
        assert result == 0.0

    def test_neutral_negative_candidate_only(self):
        """Candidate-only neutral negative → clamped to 0.0."""
        result = _negative_adjustment(set(), {"magazine_capacity"})
        assert result == 0.0

    def test_multiple_negatives_mixed(self):
        """Multiple negatives with different qualities combine correctly."""
        target = {"zoom"}
        candidate = {"zoom", "critical_chance"}
        result = _negative_adjustment(target, candidate)
        # zoom is shared: +0.08, crit_chance is candidate-only bad: -0.15
        expected = NEGATIVE_QUALITY["zoom"] + NEGATIVE_QUALITY["critical_chance"]
        assert abs(result - expected) < 1e-9

    def test_graduated_ordering(self):
        """Desirable negatives produce higher adjustments than undesirable ones."""
        zoom_adj = _negative_adjustment({"zoom"}, {"zoom"})
        recoil_adj = _negative_adjustment({"recoil"}, {"recoil"})
        damage_adj = _negative_adjustment(
            {"base_damage_/_melee_damage"}, {"base_damage_/_melee_damage"}
        )
        crit_adj = _negative_adjustment({"critical_chance"}, {"critical_chance"})
        assert zoom_adj > recoil_adj > 0 > damage_adj > crit_adj


# ---------------------------------------------------------------------------
# _cosine_similarity sanity checks
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors(self):
        vec = {"a": 1.0, "b": 2.0}
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-9

    def test_orthogonal_vectors(self):
        vec_a = {"a": 1.0}
        vec_b = {"b": 1.0}
        assert _cosine_similarity(vec_a, vec_b) == 0.0

    def test_empty_vector(self):
        assert _cosine_similarity({}, {"a": 1.0}) == 0.0


# ---------------------------------------------------------------------------
# _reroll_penalty sanity checks
# ---------------------------------------------------------------------------

class TestRerollPenalty:
    def test_same_rerolls(self):
        assert _reroll_penalty(5, 5) == 1.0

    def test_distant_rerolls_decays(self):
        penalty = _reroll_penalty(0, 20)
        assert 0.3 < penalty < 0.4  # e^(-1) ≈ 0.368


# ---------------------------------------------------------------------------
# compute_similarity integration test
# ---------------------------------------------------------------------------

def _make_auction(
    pos_attrs: list[tuple[str, float]],
    neg_attrs: list[tuple[str, float]],
    re_rolls: int = 0,
    buyout: int = 100,
) -> Auction:
    """Helper to create a minimal Auction for testing."""
    attributes = [
        RivenAttribute(url_name=name, value=val, positive=True)
        for name, val in pos_attrs
    ] + [
        RivenAttribute(url_name=name, value=val, positive=False)
        for name, val in neg_attrs
    ]
    now = datetime.now(timezone.utc)
    return Auction(
        id="test",
        weapon_url_name="braton_prime",
        weapon_display="Braton Prime",
        riven_name="Braton Crita-gelitis",
        starting_price=None,
        buyout_price=buyout,
        top_bid=None,
        mastery_level=8,
        mod_rank=8,
        re_rolls=re_rolls,
        polarity="madurai",
        attributes=attributes,
        owner=AuctionOwner(id="seller1", reputation=5, ingame_name="TestSeller"),
        created=now,
        updated=now,
        url="https://warframe.market/auction/test",
    )


class TestComputeSimilarityWithNegatives:
    """Integration tests verifying graduated negatives flow through to final score."""

    def test_good_negative_boosts_score(self):
        """A riven with -zoom should score higher than the same riven with -damage."""
        weights = {"critical_chance": 0.5, "critical_damage": 0.5}
        target_vector = {"critical_chance": 0.5, "critical_damage": 0.5}
        target_neg = {"zoom"}

        auction_zoom = _make_auction(
            pos_attrs=[("critical_chance", 100.0), ("critical_damage", 80.0)],
            neg_attrs=[("zoom", -30.0)],
        )
        auction_damage = _make_auction(
            pos_attrs=[("critical_chance", 100.0), ("critical_damage", 80.0)],
            neg_attrs=[("base_damage_/_melee_damage", -50.0)],
        )

        sim_zoom = compute_similarity(target_vector, target_neg, 0, auction_zoom, weights, 3)
        sim_damage = compute_similarity(target_vector, target_neg, 0, auction_damage, weights, 3)

        assert sim_zoom > sim_damage

    def test_no_negative_is_middle_ground(self):
        """A riven with no negative should score between -zoom and -damage."""
        weights = {"critical_chance": 0.5, "multishot": 0.5}
        target_vector = {"critical_chance": 0.4, "multishot": 0.4}
        target_neg: set[str] = set()

        auction_none = _make_auction(
            pos_attrs=[("critical_chance", 100.0), ("multishot", 80.0)],
            neg_attrs=[],
        )
        auction_zoom = _make_auction(
            pos_attrs=[("critical_chance", 100.0), ("multishot", 80.0)],
            neg_attrs=[("zoom", -30.0)],
        )
        auction_damage = _make_auction(
            pos_attrs=[("critical_chance", 100.0), ("multishot", 80.0)],
            neg_attrs=[("base_damage_/_melee_damage", -50.0)],
        )

        sim_none = compute_similarity(target_vector, target_neg, 0, auction_none, weights, 3)
        sim_zoom = compute_similarity(target_vector, target_neg, 0, auction_zoom, weights, 3)
        sim_damage = compute_similarity(target_vector, target_neg, 0, auction_damage, weights, 3)

        # -zoom candidate-only is clamped to 0 → same as no negative
        # -damage candidate-only is penalized → lower
        assert sim_none >= sim_zoom  # zoom clamped, no bonus
        assert sim_none > sim_damage  # damage penalized


# ---------------------------------------------------------------------------
# _roll_quality_multiplier unit tests
# ---------------------------------------------------------------------------

class TestRollQualityMultiplier:
    """Tests for the piecewise linear roll quality multiplier (0.7–1.1×).

    Reference: critical_chance at dispo=3, 2 positives, no negative → max = 150.0
    So value=150 → 100% roll, value=75 → 50% roll, value=15 → 10% roll.
    """

    def test_max_roll_gives_boost(self):
        """~100% rolls → multiplier ≈ 1.1."""
        auction = _make_auction(
            pos_attrs=[("critical_chance", 150.0), ("critical_damage", 120.0)],
            neg_attrs=[],
        )
        mult = _roll_quality_multiplier(auction, disposition=3)
        assert 1.08 < mult <= 1.1

    def test_min_roll_gives_penalty(self):
        """~10% rolls → multiplier ≈ 0.76."""
        auction = _make_auction(
            pos_attrs=[("critical_chance", 15.0), ("critical_damage", 12.0)],
            neg_attrs=[],
        )
        mult = _roll_quality_multiplier(auction, disposition=3)
        assert 0.7 < mult < 0.8

    def test_mid_roll_is_neutral(self):
        """50% rolls → multiplier = 1.0."""
        auction = _make_auction(
            pos_attrs=[("critical_chance", 75.0), ("critical_damage", 60.0)],
            neg_attrs=[],
        )
        mult = _roll_quality_multiplier(auction, disposition=3)
        assert abs(mult - 1.0) < 0.02

    def test_no_positive_attrs_returns_neutral(self):
        """Edge case: no positive attributes → 1.0."""
        auction = _make_auction(
            pos_attrs=[],
            neg_attrs=[("zoom", -30.0)],
        )
        mult = _roll_quality_multiplier(auction, disposition=3)
        assert mult == 1.0

    def test_high_roll_scores_higher_than_low_roll(self):
        """Integration: same stat types, different magnitudes → higher sim for better rolls."""
        weights = {"critical_chance": 0.5, "critical_damage": 0.5}
        target_vector = {"critical_chance": 0.5, "critical_damage": 0.5}

        auction_high = _make_auction(
            pos_attrs=[("critical_chance", 140.0), ("critical_damage", 110.0)],
            neg_attrs=[],
        )
        auction_low = _make_auction(
            pos_attrs=[("critical_chance", 30.0), ("critical_damage", 25.0)],
            neg_attrs=[],
        )

        sim_high = compute_similarity(target_vector, set(), 0, auction_high, weights, 3)
        sim_low = compute_similarity(target_vector, set(), 0, auction_low, weights, 3)

        assert sim_high > sim_low
