import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from backend.services.meta_tiers import (
        TierLevel, TIER_MULTIPLIERS, WeaponTier,
        NameNormalizer, MetaTierService, _is_stale,
    )
    from backend.evaluation.price_estimator import estimate_price, PriceEstimate
except ImportError:
    from services.meta_tiers import (
        TierLevel, TIER_MULTIPLIERS, WeaponTier,
        NameNormalizer, MetaTierService, _is_stale,
    )
    from evaluation.price_estimator import estimate_price, PriceEstimate

from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# TierLevel and TIER_MULTIPLIERS
# ---------------------------------------------------------------------------

class TestTierMultipliers:
    def test_all_tiers_have_multipliers(self):
        for tier in TierLevel:
            assert tier in TIER_MULTIPLIERS, f"Missing multiplier for {tier}"

    def test_multiplier_values(self):
        assert TIER_MULTIPLIERS[TierLevel.S] == 1.3
        assert TIER_MULTIPLIERS[TierLevel.A] == 1.0
        assert TIER_MULTIPLIERS[TierLevel.B] == 0.8
        assert TIER_MULTIPLIERS[TierLevel.C] == 0.5
        assert TIER_MULTIPLIERS[TierLevel.D] == 0.3

    def test_s_tier_highest(self):
        values = list(TIER_MULTIPLIERS.values())
        assert TIER_MULTIPLIERS[TierLevel.S] == max(values)

    def test_d_tier_lowest(self):
        values = list(TIER_MULTIPLIERS.values())
        assert TIER_MULTIPLIERS[TierLevel.D] == min(values)


# ---------------------------------------------------------------------------
# NameNormalizer
# ---------------------------------------------------------------------------

class TestNameNormalizer:
    def test_base_name_from_url_name(self):
        assert NameNormalizer.to_base_name("soma_prime") == "soma"

    def test_base_name_lowercase(self):
        assert NameNormalizer.to_base_name("Torid") == "torid"

    def test_base_name_multi_word(self):
        assert NameNormalizer.to_base_name("Ack & Brunt") == "ack & brunt"

    def test_base_name_vandal(self):
        assert NameNormalizer.to_base_name("ignis_wraith") == "ignis"

    def test_base_name_prisma(self):
        assert NameNormalizer.to_base_name("Gorgon Prisma") == "gorgon"

    def test_base_name_already_base(self):
        assert NameNormalizer.to_base_name("soma") == "soma"

    def test_base_name_underscores(self):
        assert NameNormalizer.to_base_name("dual_toxocyst") == "dual toxocyst"

    def test_base_name_with_spaces(self):
        assert NameNormalizer.to_base_name("Nami Solo") == "nami solo"

    def test_overframe_name_normalization(self):
        assert NameNormalizer.to_base_name("Soma Prime") == "soma"
        assert NameNormalizer.to_base_name("Torid") == "torid"


# ---------------------------------------------------------------------------
# Cache staleness
# ---------------------------------------------------------------------------

class TestCacheStaleness:
    def test_none_is_stale(self):
        assert _is_stale(None) is True

    def test_fresh_cache(self):
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        assert _is_stale(recent) is False

    def test_stale_cache(self):
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        assert _is_stale(old) is True

    def test_exactly_24h_is_stale(self):
        boundary = datetime.now(timezone.utc) - timedelta(hours=24, seconds=1)
        assert _is_stale(boundary) is True

    def test_naive_datetime_treated_as_utc(self):
        recent = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        # Should treat as UTC and not be stale
        assert _is_stale(recent) is False


# ---------------------------------------------------------------------------
# MetaTierService.build
# ---------------------------------------------------------------------------

class TestMetaTierBuild:
    def test_basic_crossref(self):
        incarnon = {"soma", "torid"}
        overframe = {"soma prime": TierLevel.A, "torid": TierLevel.S}
        result = MetaTierService.build(incarnon, overframe)

        assert "soma" in result
        assert result["soma"].tier == TierLevel.A
        assert result["soma"].multiplier == 1.0

        assert "torid" in result
        assert result["torid"].tier == TierLevel.S
        assert result["torid"].multiplier == 1.3

    def test_best_tier_picked(self):
        """When both base and prime exist, pick the better tier."""
        incarnon = {"soma"}
        overframe = {"soma": TierLevel.C, "soma prime": TierLevel.S}
        result = MetaTierService.build(incarnon, overframe)
        assert result["soma"].tier == TierLevel.S

    def test_no_overframe_match_defaults_b(self):
        incarnon = {"obscure weapon"}
        overframe = {}
        result = MetaTierService.build(incarnon, overframe)
        assert result["obscure weapon"].tier == TierLevel.B
        assert result["obscure weapon"].multiplier == 0.8

    def test_non_incarnon_excluded(self):
        """Weapons not in the Incarnon set should not appear in output."""
        incarnon = {"soma"}
        overframe = {"soma prime": TierLevel.A, "reaper prime": TierLevel.S}
        result = MetaTierService.build(incarnon, overframe)
        assert "reaper" not in result
        assert "reaper prime" not in result

    def test_empty_incarnon(self):
        incarnon: set[str] = set()
        overframe = {"soma prime": TierLevel.S}
        result = MetaTierService.build(incarnon, overframe)
        assert len(result) == 0

    def test_all_tiers_produce_valid_weapon_tier(self):
        incarnon = {"wep_s", "wep_a", "wep_b", "wep_c", "wep_d"}
        overframe = {
            "wep_s": TierLevel.S,
            "wep_a": TierLevel.A,
            "wep_b": TierLevel.B,
            "wep_c": TierLevel.C,
            "wep_d": TierLevel.D,
        }
        result = MetaTierService.build(incarnon, overframe)
        assert result["wep_s"].multiplier == 1.3
        assert result["wep_a"].multiplier == 1.0
        assert result["wep_b"].multiplier == 0.8
        assert result["wep_c"].multiplier == 0.5
        assert result["wep_d"].multiplier == 0.3


# ---------------------------------------------------------------------------
# estimate_price meta_multiplier integration
# ---------------------------------------------------------------------------

class TestEstimatePriceMetaMultiplier:
    def test_meta_multiplier_in_result(self):
        """PriceEstimate.to_dict() includes metaMultiplier field."""
        pe = PriceEstimate(
            estimated_price=100.0,
            confidence="low",
            comparable_count=0,
            archetype="other",
            meta_multiplier=1.3,
        )
        d = pe.to_dict()
        assert d["metaMultiplier"] == 1.3

    def test_meta_multiplier_none_in_result(self):
        """metaMultiplier is None when weapon has no Incarnon adapter."""
        pe = PriceEstimate(
            estimated_price=100.0,
            confidence="low",
            comparable_count=0,
            archetype="other",
        )
        d = pe.to_dict()
        assert d["metaMultiplier"] is None
