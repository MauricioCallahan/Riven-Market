"""
Archetype classification for Riven mods.

Categorizes rivens as Crit, Status, Hybrid, or Other based on their
positive attributes.  The similarity engine uses archetypes to ensure
only comparable rivens are matched against each other.
"""

from enum import Enum
from core.models import Auction


# ---------------------------------------------------------------------------
# Archetype enum
# ---------------------------------------------------------------------------

class Archetype(str, Enum):
    CRIT   = "crit"
    STATUS = "status"
    HYBRID = "hybrid"
    OTHER  = "other"


# ---------------------------------------------------------------------------
# Archetype definitions
# ---------------------------------------------------------------------------

CRIT_STATS: set[str] = {"critical_chance", "critical_damage"}

STATUS_STATS: set[str] = {
    "status_chance",
    "status_duration",
    "heat_damage",
    "cold_damage",
    "electric_damage",
    "toxin_damage",
}

# Which archetypes can be compared against each target archetype
COMPATIBLE: dict[Archetype, set[Archetype]] = {
    Archetype.CRIT:   {Archetype.CRIT, Archetype.HYBRID},
    Archetype.STATUS: {Archetype.STATUS, Archetype.HYBRID},
    Archetype.HYBRID: {Archetype.CRIT, Archetype.STATUS, Archetype.HYBRID},
    Archetype.OTHER:  {Archetype.CRIT, Archetype.STATUS, Archetype.HYBRID, Archetype.OTHER},
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ArchetypeClassifier:
    @staticmethod
    def classify_attributes(positive_url_names: list[str] | set[str]) -> Archetype:
        """Classify a set of positive attribute url_names into an archetype.

        - CRIT:   has crit stat(s), no status stats
        - STATUS: has status/elemental stat(s), no crit stats
        - HYBRID: has both crit and status stats
        - OTHER:  neither crit nor status (damage, utility, etc.)
        """
        names = set(positive_url_names)
        has_crit = bool(names & CRIT_STATS)
        has_status = bool(names & STATUS_STATS)

        if has_crit and has_status:
            return Archetype.HYBRID
        if has_crit:
            return Archetype.CRIT
        if has_status:
            return Archetype.STATUS
        return Archetype.OTHER

    @staticmethod
    def classify_auction(auction: Auction) -> Archetype:
        """Classify an auction's riven based on its positive attributes."""
        pos_names = [a.url_name for a in auction.positive_attributes]
        return ArchetypeClassifier.classify_attributes(pos_names)

    @staticmethod
    def is_compatible(target_archetype: Archetype, candidate_archetype: Archetype) -> bool:
        """Check whether a candidate's archetype is comparable to the target's."""
        allowed = COMPATIBLE.get(target_archetype, COMPATIBLE[Archetype.OTHER])
        return candidate_archetype in allowed


# Module-level aliases for backward-compatible imports
classify_attributes = ArchetypeClassifier.classify_attributes
classify_auction    = ArchetypeClassifier.classify_auction
is_compatible       = ArchetypeClassifier.is_compatible
