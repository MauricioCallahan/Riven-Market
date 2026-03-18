from statistics import mean, median
from core.models import Auction, FieldStats, PriceStats


def _field_stats(values: list[int | float]) -> FieldStats | None:
    if not values:
        return None
    return FieldStats(
        min=min(values),
        max=max(values),
        mean=round(mean(values), 1),
        median=round(median(values), 1),
    )


def compute_stats(auctions: list[Auction]) -> PriceStats:
    buyouts = [a.buyout_price for a in auctions if a.buyout_price is not None]
    start_bids = [a.starting_price for a in auctions if a.starting_price is not None]
    top_bids = [a.top_bid for a in auctions if a.top_bid is not None]

    return PriceStats(
        count=len(auctions),
        buyout=_field_stats(buyouts),
        start_bid=_field_stats(start_bids),
        top_bid=_field_stats(top_bids),
    )
