from statistics import mean, median
from core.models import Auction, Confidence, FieldStats, PriceStats

_CONFIDENCE_THRESHOLD_LOW = 5
_CONFIDENCE_THRESHOLD_HIGH = 15


def _field_stats(values: list[int | float]) -> FieldStats | None:
    if not values:
        return None
    return FieldStats(
        min=min(values),
        max=max(values),
        mean=round(mean(values), 1),
        median=round(median(values), 1),
    )


class StatsCalculator:
    @staticmethod
    def _determine_confidence(sample_size: int) -> Confidence:
        if sample_size > _CONFIDENCE_THRESHOLD_HIGH:
            return Confidence.HIGH
        if sample_size >= _CONFIDENCE_THRESHOLD_LOW:
            return Confidence.MEDIUM
        return Confidence.LOW

    @staticmethod
    def compute_stats(auctions: list[Auction]) -> PriceStats:
        buyouts = [a.buyout_price for a in auctions if a.buyout_price is not None]
        start_bids = [a.starting_price for a in auctions if a.starting_price is not None]
        top_bids = [a.top_bid for a in auctions if a.top_bid is not None]

        sample_size = len(auctions)
        return PriceStats(
            count=sample_size,
            buyout=_field_stats(buyouts),
            start_bid=_field_stats(start_bids),
            top_bid=_field_stats(top_bids),
            sample_size=sample_size,
            confidence=StatsCalculator._determine_confidence(sample_size),
        )


# Module-level alias for backward-compatible imports
compute_stats = StatsCalculator.compute_stats
