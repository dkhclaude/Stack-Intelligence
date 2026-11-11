"""Turn connector results into observations, events, prices and canonical products."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import circuit
from .classify import classify
from .connectors.base import Connector
from .db.models import (
    InventoryObservation,
    ListingEvent,
    PriceHistory,
    Product,
    ReleaseCalendar,
    RetailerConnector,
    RetailerListing,
)
from .domain import CheckResult, CheckStatus, EventType, ListingSnapshot, ReleaseInfo, StockState, utcnow
from .normalize import link_listing
from .pricing import market_median, price_flag
from .settings_store import log_event
from .state import DetectedEvent, PriorState, detect_events

log = logging.getLogger(__name__)
HARD_FAILURES = {CheckStatus.BLOCKED, CheckStatus.NOT_CONFIGURED, CheckStatus.DISALLOWED}
PRICE_HEARTBEAT = timedelta(hours=6)


@dataclass
class IngestStats:
    checked: int = 0
    failed: int = 0
    new_listings: int = 0
    skipped_non_tcg: int = 0
    ai_classified: int = 0
    events: list[tuple[RetailerListing, list[ListingEvent]]] = field(default_factory=list)

    @property
    def event_count(self) -> int:
        return sum(len(e) for _, e in self.events)


def sync_connectors(session: Session, connectors: list[Connector]) -> None:
    for c in connectors:
        ok, why = c.configured()
        row = session.get(RetailerConnector, c.code)
        if row is None:
            row = RetailerConnector(code=c.code, name=c.name, support_level=str(c.support_level), enabled=True)
            session.add(row)
        row.name, row.priority_tier = c.name, c.tier
        row.support_level = str(c.support_level)
        row.configured = ok
        row.status_note = c.status_note if ok else why
    session.flush()


def _unknown_observation(session: Session, listing: RetailerListing, status: CheckStatus, msg: str, job_id: int | None) -> None:
    now = utcnow()
    session.add(InventoryObservation(listing_id=listing.id, observed_at=now, check_status=str(status),
                                     state=str(StockState.UNKNOWN), evidence=msg[:1000], job_id=job_id))
    listing.current_state = str(StockState.UNKNOWN)  # last_confirmed_state is deliberately untouched
    listing.last_checked_at = now
    listing.last_check_status = str(status)


def _apply_snapshot(session: Session, listing: RetailerListing, snap: ListingSnapshot, job_id: int | None,
                    runtime: dict, is_new: bool, baseline: bool = False) -> list[ListingEvent]:
    now = snap.observed_at
    prior = None if is_new else PriorState(
        StockState(listing.last_confirmed_state) if listing.last_confirmed_state else None,
        bool(listing.ever_in_stock), listing.current_price)
    detected: list[DetectedEvent] = detect_events(prior, snap.state, snap.price)
    if baseline and is_new:
        # first scan of a store: existing stock is not "now available" news
        detected = [d for d in detected if d.type == EventType.NEW_LISTING]

    # descriptive fields (retailers edit titles/images over time)
    listing.title, listing.url = snap.title, snap.url
    listing.image_url = snap.image_url or listing.image_url
    listing.upc = snap.upc or listing.upc
    listing.sku = snap.sku or listing.sku
    listing.seller_name, listing.is_marketplace = snap.seller_name, snap.is_marketplace
    listing.release_date = snap.release_date or listing.release_date
    listing.ship_available, listing.pickup_available = snap.ship_available, snap.pickup_available
    listing.evidence = snap.evidence[:1000]
    listing.last_checked_at = listing.last_success_at = now
    listing.last_check_status = str(CheckStatus.OK if snap.state != StockState.UNKNOWN else CheckStatus.INCOMPLETE)
    listing.current_state = str(snap.state)
    if snap.state != StockState.UNKNOWN:
        if listing.last_confirmed_state != str(snap.state):
            listing.state_changed_at = now
        listing.last_confirmed_state = str(snap.state)
        if snap.state == StockState.IN_STOCK:
            listing.ever_in_stock = True

    obs = InventoryObservation(listing_id=listing.id, observed_at=now, check_status=listing.last_check_status,
                               state=str(snap.state), ship_available=snap.ship_available,
                               pickup_available=snap.pickup_available, price=snap.price,
                               evidence=snap.evidence[:1000], job_id=job_id)
    session.add(obs)

    if snap.price is not None:
        changed = listing.current_price is None or listing.current_price != snap.price
        if changed and listing.current_price is not None:
            listing.previous_price = listing.current_price
        listing.current_price = snap.price
        listing.lowest_price = min(filter(None, [listing.lowest_price, snap.price]))
        listing.highest_price = max(filter(None, [listing.highest_price, snap.price]))
        last = session.scalar(select(PriceHistory.observed_at).where(PriceHistory.listing_id == listing.id)
                              .order_by(PriceHistory.observed_at.desc()).limit(1))
        if changed or last is None or now - last >= PRICE_HEARTBEAT:
            session.add(PriceHistory(listing_id=listing.id, product_id=listing.product_id, retailer=listing.retailer,
                                     observed_at=now, price=snap.price, regular_price=snap.regular_price,
                                     currency=snap.currency, seller_name=snap.seller_name,
                                     is_marketplace=snap.is_marketplace, ship_available=snap.ship_available))
    session.flush()

    rows = []
    for d in detected:
        ev = ListingEvent(listing_id=listing.id, event_type=str(d.type),
                          from_state=str(d.from_state) if d.from_state else None, to_state=str(d.to_state),
                          old_price=d.old_price, new_price=d.new_price, occurred_at=now, observation_id=obs.id)
        session.add(ev)
        rows.append(ev)
    session.flush()
    return rows


def ingest(session: Session, connector: Connector, result: CheckResult, runtime: dict,
           job_id: int | None = None, requested: list[RetailerListing] | None = None, ai=None,
           baseline: bool = False) -> IngestStats:
    stats = IngestStats()
    ai_cfg = runtime.get("ai", {})
    if ai is None and ai_cfg.get("enabled"):
        from .ai import AIClassifier
        ai = AIClassifier(connector.settings, int(ai_cfg.get("max_calls_per_scan", 10)))
    circuit.count_requests(session, connector.code, result.requests_made)

    if result.fatal:
        f = result.fatal
        circuit.record_failure(session, connector.code, f"{f.status}: {f.message}", hard=f.status in HARD_FAILURES)
        log_event(session, connector.code, "check_failed", f.message, level="WARNING", status=str(f.status))
        for listing in requested or []:
            _unknown_observation(session, listing, f.status, f.message, job_id)
            stats.failed += 1
        return stats

    circuit.record_success(session, connector.code)

    min_conf = float(runtime["alerts"]["min_tcg_confidence"])
    match_cfg = runtime["matching"]
    pricing_cfg = runtime["pricing"]
    for snap in result.snapshots:
        listing = session.scalar(select(RetailerListing).where(
            RetailerListing.retailer == snap.retailer, RetailerListing.retailer_product_id == snap.retailer_product_id))
        is_new = listing is None
        if is_new:
            feats = classify(snap.title, snap.category_hint)
            category, conf = feats.category.value, feats.tcg_confidence
            if ai is not None and ai.available and ai_cfg.get("min_conf", 0.3) <= conf < ai_cfg.get("max_conf", 0.6):
                verdict = ai.classify(session, snap.title, snap.category_hint)
                if verdict is not None:
                    conf = min(verdict.confidence, 0.9) if verdict.is_pokemon_tcg_sealed else 0.0
                    category = verdict.category if verdict.is_pokemon_tcg_sealed else category
                    stats.ai_classified += 1
            if conf < min_conf:
                stats.skipped_non_tcg += 1
                continue
            listing = RetailerListing(
                retailer=snap.retailer, connector=connector.code, retailer_product_id=snap.retailer_product_id,
                title=snap.title, url=snap.url, category=category, tcg_confidence=conf,
                first_seen_at=snap.observed_at, priority=1,
            )
            session.add(listing)
            session.flush()
            stats.new_listings += 1
        events = _apply_snapshot(session, listing, snap, job_id, runtime, is_new, baseline)
        stats.checked += 1

        product = session.get(Product, listing.product_id) if listing.product_id else None
        if product is None:
            product = link_listing(session, listing, match_cfg["auto_link_threshold"], match_cfg["review_threshold"])
            if product is not None:
                for ph in session.scalars(select(PriceHistory).where(PriceHistory.listing_id == listing.id,
                                                                     PriceHistory.product_id.is_(None))):
                    ph.product_id = product.id
                listing.priority = max(listing.priority, product.priority)
        listing.price_flag = price_flag(listing, product, market_median(session, listing.product_id, listing.id),
                                        pricing_cfg["inflated_vs_msrp_ratio"], pricing_cfg["inflated_vs_market_ratio"])
        if events:
            stats.events.append((listing, events))

    for f in result.failures:
        listing = session.scalar(select(RetailerListing).where(
            RetailerListing.connector == connector.code, RetailerListing.retailer_product_id == f.retailer_product_id))
        if listing:
            _unknown_observation(session, listing, f.status, f.message, job_id)
        stats.failed += 1
    session.flush()
    return stats


def upsert_releases(session: Session, releases: list[ReleaseInfo]) -> int:
    n = 0
    for r in releases:
        row = session.scalar(select(ReleaseCalendar).where(ReleaseCalendar.source_name == r.source_name,
                                                           ReleaseCalendar.external_id == r.external_id))
        if row is None:
            row = ReleaseCalendar(source_name=r.source_name, external_id=r.external_id, name=r.name)
            session.add(row)
            n += 1
        row.name, row.release_date, row.series = r.name, r.release_date, r.series
        row.date_confidence, row.status, row.source_url = r.date_confidence, r.status, r.source_url
        row.product_type, row.image_url, row.notes = r.product_type, r.image_url, r.notes
    session.flush()
    return n
