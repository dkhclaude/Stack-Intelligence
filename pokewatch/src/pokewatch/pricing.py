"""Price intelligence: stats, cross-retailer comparison and inflation flags.

Flags are descriptive ("above MSRP", "third-party seller"); nothing is ever
labelled fraudulent. MSRP is only used when it was recorded with a source.
"""

from __future__ import annotations

from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db.models import Product, RetailerListing


def market_median(session: Session, product_id: int | None, exclude_listing_id: int | None = None) -> Decimal | None:
    if product_id is None:
        return None
    q = select(RetailerListing.current_price).where(
        RetailerListing.product_id == product_id,
        RetailerListing.is_marketplace.is_(False),
        RetailerListing.current_price.is_not(None),
    )
    if exclude_listing_id:
        q = q.where(RetailerListing.id != exclude_listing_id)
    prices = [p for p in session.scalars(q).all() if p]
    return Decimal(str(median(prices))) if prices else None


def price_flag(listing: RetailerListing, product: Product | None, mkt_median: Decimal | None,
               msrp_ratio: float = 1.4, market_ratio: float = 1.5) -> str | None:
    flags = []
    if listing.is_marketplace:
        flags.append("third-party seller")
    p = listing.current_price
    if p is not None:
        if product is not None and product.msrp and product.msrp_source:
            ratio = float(p / product.msrp)
            if ratio >= msrp_ratio:
                flags.append(f"{(ratio - 1) * 100:.0f}% above verified MSRP")
        elif mkt_median and mkt_median > 0:
            ratio = float(p / mkt_median)
            if ratio >= market_ratio:
                flags.append(f"{(ratio - 1) * 100:.0f}% above retailer-direct median")
    return "; ".join(flags) or None
