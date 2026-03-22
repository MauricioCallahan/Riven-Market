from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import cached_property
from core.config import AUCTION_BASE_URL


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class AttributeInput:
    url_name: str
    value: float


@dataclass
class RivenAttribute:
    url_name: str
    value: float
    positive: bool

    def to_display(self) -> str:
        name = self.url_name.replace("_", " ")
        return f"{name} {self.value:+.1f}%"


@dataclass
class Auction:
    id: str
    weapon_url_name: str
    weapon_display: str
    riven_name: str
    starting_price: int | None
    buyout_price: int | None
    top_bid: int | None
    mastery_level: int | None
    mod_rank: int | None
    re_rolls: int | None
    polarity: str
    attributes: list[RivenAttribute]
    created: datetime | None
    updated: datetime | None
    url: str

    @classmethod
    def from_api(cls, raw: dict) -> "Auction":
        item = raw.get("item", {})
        auction_id = raw.get("id", "")
        raw_attrs = item.get("attributes", [])

        attributes = [
            RivenAttribute(
                url_name=a.get("url_name", ""),
                value=a.get("value", 0),
                positive=a.get("positive", True),
            )
            for a in raw_attrs
        ]

        return cls(
            id=auction_id,
            weapon_url_name=item.get("weapon_url_name", ""),
            weapon_display=item.get("weapon_url_name", "").replace("_", " ").title(),
            riven_name=item.get("name", ""),
            starting_price=raw.get("starting_price"),
            buyout_price=raw.get("buyout_price"),
            top_bid=raw.get("top_bid"),
            mastery_level=item.get("mastery_level"),
            mod_rank=item.get("mod_rank"),
            re_rolls=item.get("re_rolls"),
            polarity=item.get("polarity", ""),
            attributes=attributes,
            created=_parse_iso(raw.get("created")),
            updated=_parse_iso(raw.get("updated")),
            url=AUCTION_BASE_URL + auction_id,
        )

    @cached_property
    def positive_attributes(self) -> list[RivenAttribute]:
        return [a for a in self.attributes if a.positive]

    @cached_property
    def negative_attributes(self) -> list[RivenAttribute]:
        return [a for a in self.attributes if not a.positive]

    def to_frontend_dict(self) -> dict:
        return {
            "id": self.id,
            "auctionId": self.id,
            "weapon": self.weapon_display,
            "rivenName": self.riven_name,
            "startBid": self.starting_price,
            "buyout": self.buyout_price,
            "topBid": self.top_bid,
            "mr": self.mastery_level,
            "rank": self.mod_rank,
            "rerolls": self.re_rolls,
            "polarity": self.polarity,
            "listed": _format_age(self.created),
            "lastUpdated": _format_date(self.updated),
            "positiveAttributes": [a.to_display() for a in self.positive_attributes],
            "negativeAttributes": [a.to_display() for a in self.negative_attributes],
            "url": self.url,
        }


@dataclass
class FieldStats:
    min: int | float
    max: int | float
    mean: float
    median: float

    def to_dict(self) -> dict:
        return {"min": self.min, "max": self.max, "mean": self.mean, "median": self.median}


@dataclass
class PriceStats:
    count: int
    buyout: FieldStats | None
    start_bid: FieldStats | None
    top_bid: FieldStats | None
    sample_size: int = 0
    confidence: Confidence = Confidence.LOW

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "buyout": self.buyout.to_dict() if self.buyout else None,
            "startBid": self.start_bid.to_dict() if self.start_bid else None,
            "topBid": self.top_bid.to_dict() if self.top_bid else None,
            "sampleSize": self.sample_size,
            "confidence": self.confidence.value,
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _parse_iso(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _format_age(dt: datetime | None) -> str:
    if not dt:
        return "\u2014"
    try:
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        if days == 0:
            hours = delta.seconds // 3600
            return f"{hours}h ago"
        return f"{days}d ago"
    except Exception:
        return "\u2014"


def _format_date(dt: datetime | None) -> str:
    if not dt:
        return "\u2014"
    try:
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "\u2014"
