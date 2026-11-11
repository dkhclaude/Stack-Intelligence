"""Core domain types shared by connectors, the pipeline and the dashboard.

Observed *states* (what a retailer currently shows) are kept separate from
*events* (confirmed changes between two observations). "NEW LISTING",
"RESTOCKED" and "PRICE DROP" are events, not states.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # stored as naive UTC


class StockState(StrEnum):
    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    PREORDER = "PREORDER"
    COMING_SOON = "COMING_SOON"
    UNKNOWN = "UNKNOWN"  # check failed / blocked / ambiguous — never treated as OOS

    @property
    def is_available(self) -> bool:
        return self in (StockState.IN_STOCK, StockState.PREORDER)


class EventType(StrEnum):
    NEW_LISTING = "NEW_LISTING"
    PREORDER_AVAILABLE = "PREORDER_AVAILABLE"
    NOW_AVAILABLE = "NOW_AVAILABLE"  # first time in stock (e.g. release day)
    RESTOCKED = "RESTOCKED"  # was in stock before, sold out, now back
    SOLD_OUT = "SOLD_OUT"
    PRICE_DROP = "PRICE_DROP"
    PRICE_INCREASE = "PRICE_INCREASE"


# Headline priority when several events fire for one listing in one scan.
EVENT_PRIORITY = {
    EventType.RESTOCKED: 0,
    EventType.NOW_AVAILABLE: 1,
    EventType.PREORDER_AVAILABLE: 2,
    EventType.NEW_LISTING: 3,
    EventType.PRICE_DROP: 4,
    EventType.SOLD_OUT: 5,
    EventType.PRICE_INCREASE: 6,
}


class CheckStatus(StrEnum):
    OK = "ok"
    BLOCKED = "blocked"  # CAPTCHA / bot wall / 403
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    ERROR = "error"
    INCOMPLETE = "incomplete"  # response parsed but required fields missing
    NOT_FOUND = "not_found"  # listing absent from response
    DISALLOWED = "disallowed"  # robots.txt / policy
    NOT_CONFIGURED = "not_configured"
    CIRCUIT_OPEN = "circuit_open"


class Category(StrEnum):
    ELITE_TRAINER_BOX = "Elite Trainer Box"
    BOOSTER_BOX = "Booster Box"
    BOOSTER_BUNDLE = "Booster Bundle"
    SLEEVED_BOOSTER = "Sleeved Booster"
    BOOSTER_PACK = "Booster Pack"
    BLISTER = "Blister Pack"
    ULTRA_PREMIUM_COLLECTION = "Ultra-Premium Collection"
    PREMIUM_COLLECTION = "Premium Collection"
    SPECIAL_COLLECTION = "Special Collection"
    COLLECTION_BOX = "Collection Box"
    TIN = "Tin"
    BUILD_AND_BATTLE = "Build & Battle"
    THEME_DECK = "Deck"
    BINDER_COLLECTION = "Binder Collection"
    OTHER_SEALED = "Other Sealed"
    NOT_TCG = "Not TCG"


class SupportLevel(StrEnum):
    SUPPORTED = "supported"  # implemented against an official/permitted source
    NEEDS_CREDENTIALS = "needs_credentials"  # implemented, waiting on API key
    NEEDS_APPROVAL = "needs_approval"  # requires affiliate/partner approval
    UNSUPPORTED = "unsupported"  # no permitted automated access


@dataclass(slots=True)
class ListingSnapshot:
    """One retailer listing as observed in a single successful check."""

    retailer: str
    retailer_product_id: str
    title: str
    url: str
    state: StockState
    evidence: str  # raw retailer signal(s) the state was derived from
    price: Decimal | None = None
    regular_price: Decimal | None = None
    currency: str = "USD"
    image_url: str | None = None
    upc: str | None = None
    sku: str | None = None
    ship_available: bool | None = None
    pickup_available: bool | None = None
    is_marketplace: bool = False
    seller_name: str | None = None
    release_date: date | None = None
    category_hint: str | None = None
    observed_at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class CheckFailure:
    retailer_product_id: str | None
    status: CheckStatus
    message: str


@dataclass(slots=True)
class CheckResult:
    """What a connector returns from discover() or check()."""

    connector: str
    snapshots: list[ListingSnapshot] = field(default_factory=list)
    failures: list[CheckFailure] = field(default_factory=list)
    requests_made: int = 0
    fatal: CheckFailure | None = None  # whole-call failure (auth, blocked, circuit)

    @property
    def ok(self) -> bool:
        return self.fatal is None


@dataclass(slots=True)
class ReleaseInfo:
    source_name: str
    external_id: str
    name: str
    release_date: date | None
    date_confidence: str  # announced | estimated | unconfirmed
    status: str  # confirmed | rumored
    source_url: str | None = None
    series: str | None = None
    product_type: str | None = None
    image_url: str | None = None
    notes: str | None = None
