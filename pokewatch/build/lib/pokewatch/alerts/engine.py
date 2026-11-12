"""Alert rules, deduplication and cooldowns."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Alert, AlertRule, ListingEvent, RetailerConnector, RetailerListing
from ..domain import EVENT_PRIORITY, EventType, StockState, utcnow
from .formatting import status_label, validate

ALERTABLE = {EventType.NEW_LISTING, EventType.PREORDER_AVAILABLE, EventType.NOW_AVAILABLE,
             EventType.RESTOCKED, EventType.PRICE_DROP}

DEFAULT_RULES = [
    {"name": "Availability (restock / release / preorder)",
     "event_types": ["RESTOCKED", "NOW_AVAILABLE", "PREORDER_AVAILABLE"]},
    {"name": "New Pokémon TCG listings", "event_types": ["NEW_LISTING"]},
    {"name": "Price drops on available items", "event_types": ["PRICE_DROP"]},
]


def seed_default_rules(session: Session) -> None:
    if session.scalar(select(AlertRule.id).limit(1)) is None:
        for r in DEFAULT_RULES:
            session.add(AlertRule(name=r["name"], event_types=r["event_types"]))
        session.flush()


def _rule_matches(rule: AlertRule, listing: RetailerListing, et: EventType) -> bool:
    if rule.event_types and str(et) not in rule.event_types:
        return False
    if rule.retailers and listing.retailer not in rule.retailers:
        return False
    if rule.categories and (listing.category or "") not in rule.categories:
        return False
    if rule.product_ids and listing.product_id not in rule.product_ids:
        return False
    if rule.keywords and not any(k.lower() in listing.title.lower() for k in rule.keywords):
        return False
    if (listing.priority or 0) < (rule.min_priority or 0):
        return False
    if rule.max_price is not None and listing.current_price is not None and listing.current_price > rule.max_price:
        return False
    if listing.is_marketplace and not rule.include_marketplace:
        return False
    return True


def _reason(ev: ListingEvent) -> str:
    et = EventType(ev.event_type)
    if et == EventType.RESTOCKED:
        return f"Back in stock (was {ev.from_state})"
    if et == EventType.NOW_AVAILABLE:
        return "Available for the first time" + (f" (was {ev.from_state})" if ev.from_state else "")
    if et == EventType.PREORDER_AVAILABLE:
        return "Preorder opened"
    if et == EventType.NEW_LISTING:
        return "New listing discovered"
    if et == EventType.PRICE_DROP and ev.old_price and ev.new_price:
        pct = (ev.old_price - ev.new_price) / ev.old_price * 100
        return f"Price dropped {pct:.0f}% (${ev.old_price} → ${ev.new_price})"
    return et.value


def build_payload(session: Session, listing: RetailerListing, primary: EventType, reasons: list[str]) -> dict:
    rc = session.get(RetailerConnector, listing.retailer)
    conf_parts = []
    if listing.tcg_confidence is not None:
        conf_parts.append(f"TCG {listing.tcg_confidence:.0%}")
    if listing.match_confidence is not None:
        conf_parts.append(f"match {listing.match_confidence:.0%}")
    verified = listing.last_success_at
    p = {
        "event_type": str(primary),
        "product": listing.title,
        "retailer": rc.name if rc else listing.retailer,
        "retailer_code": listing.retailer,
        "status": status_label(listing.current_state, listing.ship_available, listing.pickup_available, listing.is_marketplace),
        "price": str(listing.current_price) if listing.current_price is not None else None,
        "previous_price": str(listing.previous_price) if primary == EventType.PRICE_DROP and listing.previous_price else None,
        "category": listing.category,
        "image_url": listing.image_url,
        "url": listing.url,
        "last_verified": verified.strftime("%Y-%m-%d %H:%M:%S") if verified else None,
        "last_verified_iso": verified.isoformat() if verified else None,
        "confidence": " · ".join(conf_parts) or "—",
        "reasons": reasons,
        "price_flag": listing.price_flag,
        "seller": listing.seller_name,
    }
    validate(p)
    return p


def create_alerts(session: Session, listing: RetailerListing, events: list[ListingEvent], runtime: dict) -> Alert | None:
    """At most one alert per listing per scan; headline = most important event."""
    cfg = runtime["alerts"]
    state = StockState(listing.current_state)
    candidates: list[ListingEvent] = []
    for ev in events:
        et = EventType(ev.event_type)
        if et not in ALERTABLE:
            continue
        if et == EventType.PRICE_DROP:
            if not (ev.old_price and ev.new_price):
                continue
            pct = float((ev.old_price - ev.new_price) / ev.old_price * 100)
            if pct < float(cfg["min_price_drop_pct"]):
                continue
            if cfg["price_drop_requires_availability"] and not state.is_available:
                continue
        candidates.append(ev)
    if not candidates:
        return None

    rules = session.scalars(select(AlertRule).where(AlertRule.enabled.is_(True))).all()
    matched: list[tuple[ListingEvent, AlertRule]] = []
    for ev in candidates:
        for r in rules:
            if _rule_matches(r, listing, EventType(ev.event_type)):
                matched.append((ev, r))
                break
    if not matched:
        return None
    matched.sort(key=lambda er: EVENT_PRIORITY[EventType(er[0].event_type)])
    primary_ev, primary_rule = matched[0]
    primary = EventType(primary_ev.event_type)
    dedup_key = f"L{listing.id}:{primary}:E{primary_ev.id}"
    if session.scalar(select(Alert.id).where(Alert.dedup_key == dedup_key)):
        return None

    reasons = [_reason(ev) for ev, _ in matched]
    channels = sorted({c for _, r in matched for c in (r.channels or [])}) or list(cfg["channels"])
    payload = build_payload(session, listing, primary, reasons)
    payload["channels"] = channels

    alert = Alert(dedup_key=dedup_key, listing_id=listing.id, product_id=listing.product_id, event_id=primary_ev.id,
                  event_type=str(primary), reasons=reasons, payload=payload, status="pending")
    cooldown = timedelta(minutes=int(cfg["cooldown_minutes"]))
    recent = session.scalar(select(Alert.id).where(
        Alert.listing_id == listing.id, Alert.event_type == str(primary),
        Alert.status.in_(["sent", "partial", "pending", "dry_run"]),
        Alert.created_at >= utcnow() - cooldown))
    if recent:
        alert.status = "suppressed"
        alert.suppressed_reason = f"cooldown {cfg['cooldown_minutes']}m (alert #{recent})"
    session.add(alert)
    session.flush()
    return alert
