"""Relational schema. History tables are append-only; nothing is overwritten."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ..domain import utcnow

Money = Numeric(10, 2)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Product(TimestampMixin, Base):
    """Canonical product (one physical SKU regardless of retailer)."""

    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(400), nullable=False)
    set_name: Mapped[str | None] = mapped_column(String(120), index=True)
    category: Mapped[str | None] = mapped_column(String(60), index=True)
    pack_count: Mapped[int | None] = mapped_column(Integer)
    variant_tokens: Mapped[str | None] = mapped_column(String(300))  # distinguishing words, e.g. "charizard"
    exclusive_to: Mapped[str | None] = mapped_column(String(60))  # e.g. "pokemon_center", "costco"
    upc: Mapped[str | None] = mapped_column(String(20), unique=True)
    release_date: Mapped[date | None] = mapped_column(Date)
    msrp: Mapped[Decimal | None] = mapped_column(Money)
    msrp_source: Mapped[str | None] = mapped_column(String(300))  # URL/name of verified source
    msrp_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    image_url: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 0 ignore .. 3 top
    release_status: Mapped[str] = mapped_column(String(20), default="confirmed")  # confirmed|rumored
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    listings: Mapped[list[RetailerListing]] = relationship(back_populates="product")


class RetailerConnector(TimestampMixin, Base):
    __tablename__ = "retailer_connectors"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    priority_tier: Mapped[int] = mapped_column(Integer, default=1)
    support_level: Mapped[str] = mapped_column(String(30), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    configured: Mapped[bool] = mapped_column(Boolean, default=False)
    status_note: Mapped[str | None] = mapped_column(Text)
    # circuit breaker
    circuit_state: Mapped[str] = mapped_column(String(12), default="closed")  # closed|open|half_open
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    circuit_open_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    requests_today: Mapped[int] = mapped_column(Integer, default=0)
    requests_day: Mapped[date | None] = mapped_column(Date)
    verified_live: Mapped[bool] = mapped_column(Boolean, default=False)  # set only after a real successful call


class RetailerListing(TimestampMixin, Base):
    __tablename__ = "retailer_listings"
    __table_args__ = (
        UniqueConstraint("retailer", "retailer_product_id", name="uq_listing_retailer_pid"),
        Index("ix_listing_state", "current_state"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    retailer: Mapped[str] = mapped_column(ForeignKey("retailer_connectors.code"), nullable=False, index=True)
    connector: Mapped[str] = mapped_column(String(40), nullable=False)  # connector that owns checks
    retailer_product_id: Mapped[str] = mapped_column(String(120), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    match_confidence: Mapped[float | None] = mapped_column(Float)
    match_method: Mapped[str | None] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    upc: Mapped[str | None] = mapped_column(String(20), index=True)
    sku: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(60))
    tcg_confidence: Mapped[float | None] = mapped_column(Float)
    seller_name: Mapped[str | None] = mapped_column(String(200))
    is_marketplace: Mapped[bool] = mapped_column(Boolean, default=False)
    release_date: Mapped[date | None] = mapped_column(Date)
    watch: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # current-state cache (history lives in inventory_observations / listing_events)
    current_state: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    last_confirmed_state: Mapped[str | None] = mapped_column(String(20))
    state_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    ever_in_stock: Mapped[bool] = mapped_column(Boolean, default=False)
    ship_available: Mapped[bool | None] = mapped_column(Boolean)
    pickup_available: Mapped[bool | None] = mapped_column(Boolean)
    evidence: Mapped[str | None] = mapped_column(Text)
    current_price: Mapped[Decimal | None] = mapped_column(Money)
    previous_price: Mapped[Decimal | None] = mapped_column(Money)
    lowest_price: Mapped[Decimal | None] = mapped_column(Money)
    highest_price: Mapped[Decimal | None] = mapped_column(Money)
    price_flag: Mapped[str | None] = mapped_column(String(120))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_check_status: Mapped[str | None] = mapped_column(String(20))

    product: Mapped[Product | None] = relationship(back_populates="listings")


class InventoryObservation(Base):
    __tablename__ = "inventory_observations"
    __table_args__ = (Index("ix_obs_listing_time", "listing_id", "observed_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("retailer_listings.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    check_status: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    ship_available: Mapped[bool | None] = mapped_column(Boolean)
    pickup_available: Mapped[bool | None] = mapped_column(Boolean)
    price: Mapped[Decimal | None] = mapped_column(Money)
    evidence: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("monitoring_jobs.id"))


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (Index("ix_price_listing_time", "listing_id", "observed_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("retailer_listings.id"), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    retailer: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    regular_price: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    seller_name: Mapped[str | None] = mapped_column(String(200))
    is_marketplace: Mapped[bool] = mapped_column(Boolean, default=False)
    ship_available: Mapped[bool | None] = mapped_column(Boolean)


class ListingEvent(Base):
    """Confirmed transitions (restock, sold out, price drop...). Drives alerts + history."""

    __tablename__ = "listing_events"
    __table_args__ = (Index("ix_event_time", "occurred_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("retailer_listings.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(20))
    to_state: Mapped[str | None] = mapped_column(String(20))
    old_price: Mapped[Decimal | None] = mapped_column(Money)
    new_price: Mapped[Decimal | None] = mapped_column(Money)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    observation_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_observations.id"))


class ReleaseCalendar(TimestampMixin, Base):
    __tablename__ = "release_calendar"
    __table_args__ = (UniqueConstraint("source_name", "external_id", name="uq_release_source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(60), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    series: Mapped[str | None] = mapped_column(String(120))
    product_type: Mapped[str | None] = mapped_column(String(60))
    release_date: Mapped[date | None] = mapped_column(Date, index=True)
    date_confidence: Mapped[str] = mapped_column(String(20), default="unconfirmed")
    status: Mapped[str] = mapped_column(String(20), default="rumored")  # confirmed|rumored
    source_url: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))


class MonitoringJob(Base):
    __tablename__ = "monitoring_jobs"
    __table_args__ = (Index("ix_job_started", "started_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(60), nullable=False)
    connector: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|ok|partial|failed|skipped|abandoned
    items_checked: Mapped[int] = mapped_column(Integer, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, default=0)
    new_listings: Mapped[int] = mapped_column(Integer, default=0)
    events_created: Mapped[int] = mapped_column(Integer, default=0)
    alerts_created: Mapped[int] = mapped_column(Integer, default=0)
    requests_made: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class JobLock(Base):
    """Cross-process duplicate-job prevention (works on SQLite and Postgres)."""

    __tablename__ = "job_locks"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner: Mapped[str] = mapped_column(String(120), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_listing_type_time", "listing_id", "event_type", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    listing_id: Mapped[int] = mapped_column(ForeignKey("retailer_listings.id"), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("listing_events.id"))
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|sent|partial|failed|suppressed|dry_run
    suppressed_reason: Mapped[str | None] = mapped_column(String(200))
    deliveries: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)


class AlertRule(TimestampMixin, Base):
    __tablename__ = "alert_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    event_types: Mapped[list] = mapped_column(JSON, default=list)  # empty = all alertable
    retailers: Mapped[list] = mapped_column(JSON, default=list)  # empty = all
    categories: Mapped[list] = mapped_column(JSON, default=list)
    product_ids: Mapped[list] = mapped_column(JSON, default=list)
    keywords: Mapped[list] = mapped_column(JSON, default=list)  # any must appear in title
    min_priority: Mapped[int] = mapped_column(Integer, default=0)
    max_price: Mapped[Decimal | None] = mapped_column(Money)
    include_marketplace: Mapped[bool] = mapped_column(Boolean, default=False)
    channels: Mapped[list] = mapped_column(JSON, default=list)  # empty = all configured


class SystemEvent(Base):
    __tablename__ = "system_events"
    __table_args__ = (Index("ix_sysevent_time", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    level: Mapped[str] = mapped_column(String(10), default="INFO")
    component: Mapped[str] = mapped_column(String(60), nullable=False)
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSON, default=dict)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AIClassificationCache(Base):
    __tablename__ = "ai_classification_cache"
    title_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
