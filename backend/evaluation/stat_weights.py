"""
Weapon-aware stat weights derived from auction data.

For a given weapon, we look at the top 30% highest-priced auctions and
count how frequently each stat appears.  High-frequency stats in expensive
rivens are assumed to be more desirable, so they get higher weight.

Falls back to equal weights when fewer than 15 auctions are available.
"""

from models import Auction


def get_effective_price(auction: Auction) -> float | None:
    """Return buyout_price, fallback to starting_price. None if neither exists."""
    if auction.buyout_price is not None:
        return float(auction.buyout_price)
    if auction.starting_price is not None:
        return float(auction.starting_price)
    return None


def _equal_weights(stat_names: set[str]) -> dict[str, float]:
    """Fallback: equal weight for every stat seen."""
    if not stat_names:
        return {}
    w = 1.0 / len(stat_names)
    return {name: w for name in stat_names}


def compute_stat_weights(
    auctions: list[Auction],
    top_fraction: float = 0.30,
    min_auctions: int = 15,
) -> dict[str, float]:
    """Derive stat importance weights from auction data.

    1. Collect all positive stat url_names across auctions
    2. If fewer than min_auctions, return equal weights
    3. Sort auctions by price descending, take the top fraction
    4. Count how often each stat appears in the top subset
    5. Normalize counts so weights sum to 1.0

    Returns {url_name: weight} where 0 < weight <= 1.0 and sum ≈ 1.0.
    """
    # Gather every positive stat that appears in any auction
    all_stats: set[str] = set()
    for a in auctions:
        for attr in a.positive_attributes:
            all_stats.add(attr.url_name)

    if not all_stats:
        return {}

    if len(auctions) < min_auctions:
        return _equal_weights(all_stats)

    # Sort by price descending, take top slice
    sorted_auctions = sorted(auctions, key=lambda a: get_effective_price(a) or 0.0, reverse=True)
    top_count = max(1, int(len(sorted_auctions) * top_fraction))
    top_auctions = sorted_auctions[:top_count]

    # Count stat frequency in the top slice
    freq: dict[str, int] = {}
    for a in top_auctions:
        for attr in a.positive_attributes:
            freq[attr.url_name] = freq.get(attr.url_name, 0) + 1

    total = sum(freq.values())
    if total == 0:
        return _equal_weights(all_stats)

    # Normalize to sum=1.0, ensure every known stat has an entry
    weights: dict[str, float] = {}
    for name in all_stats:
        weights[name] = freq.get(name, 0) / total

    return weights
