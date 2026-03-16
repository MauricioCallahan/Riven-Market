"""
Archetype classification for Riven mods.

Categorizes rivens as Crit, Status, Hybrid, or Other based on their
positive attributes.  The similarity engine uses archetypes to ensure
only comparable rivens are matched against each other.
"""

from models import Auction


# ---------------------------------------------------------------------------
# Archetype definitions
# ---------------------------------------------------------------------------

CRIT = "crit"
STATUS = "status"
HYBRID = "hybrid"
OTHER = "other"

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
COMPATIBLE: dict[str, set[str]] = {
    CRIT:   {CRIT, HYBRID},
    STATUS: {STATUS, HYBRID},
    HYBRID: {CRIT, STATUS, HYBRID},
    OTHER:  {CRIT, STATUS, HYBRID, OTHER},  # compare broadly
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_attributes(positive_url_names: list[str] | set[str]) -> str:
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
        return HYBRID
    if has_crit:
        return CRIT
    if has_status:
        return STATUS
    return OTHER


def classify_auction(auction: Auction) -> str:
    """Classify an auction's riven based on its positive attributes."""
    pos_names = [a.url_name for a in auction.positive_attributes()]
    return classify_attributes(pos_names)


def is_compatible(target_archetype: str, candidate_archetype: str) -> bool:
    """Check whether a candidate's archetype is comparable to the target's."""
    allowed = COMPATIBLE.get(target_archetype, COMPATIBLE[OTHER])
    return candidate_archetype in allowed
