"""Inventory state-transition detection (pure, deterministic, fully unit-tested).

Rules
-----
* UNKNOWN observations never produce events and never overwrite the last
  *confirmed* state. OUT -> UNKNOWN -> IN is therefore still a restock, and
  IN -> UNKNOWN -> IN is not.
* RESTOCKED requires the listing to have been confirmed in stock before and
  then confirmed out of stock. First-ever availability is NOW_AVAILABLE.
* Price events compare against the last known price only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .domain import EventType, StockState


@dataclass(frozen=True)
class PriorState:
    last_confirmed_state: StockState | None
    ever_in_stock: bool
    last_price: Decimal | None


@dataclass(frozen=True)
class DetectedEvent:
    type: EventType
    from_state: StockState | None
    to_state: StockState
    old_price: Decimal | None = None
    new_price: Decimal | None = None


def detect_events(prior: PriorState | None, state: StockState, price: Decimal | None,
                  min_price_change_pct: float = 1.0) -> list[DetectedEvent]:
    events: list[DetectedEvent] = []

    if prior is None:  # first time we see this listing
        events.append(DetectedEvent(EventType.NEW_LISTING, None, state, None, price))
        if state == StockState.PREORDER:
            events.append(DetectedEvent(EventType.PREORDER_AVAILABLE, None, state))
        elif state == StockState.IN_STOCK:
            events.append(DetectedEvent(EventType.NOW_AVAILABLE, None, state))
        return events

    if state == StockState.UNKNOWN:
        return events

    prev = prior.last_confirmed_state
    if prev != state:
        if state == StockState.IN_STOCK:
            if prior.ever_in_stock and prev in (StockState.OUT_OF_STOCK, StockState.COMING_SOON, None):
                events.append(DetectedEvent(EventType.RESTOCKED, prev, state))
            elif prev != StockState.IN_STOCK and not prior.ever_in_stock:
                events.append(DetectedEvent(EventType.NOW_AVAILABLE, prev, state))
            # PREORDER -> IN_STOCK with ever_in_stock (preorders counted) is a release, not a restock
            elif prev == StockState.PREORDER:
                events.append(DetectedEvent(EventType.NOW_AVAILABLE, prev, state))
        elif state == StockState.PREORDER:
            events.append(DetectedEvent(EventType.PREORDER_AVAILABLE, prev, state))
        elif state == StockState.OUT_OF_STOCK and prev in (StockState.IN_STOCK, StockState.PREORDER):
            events.append(DetectedEvent(EventType.SOLD_OUT, prev, state))

    if price is not None and prior.last_price is not None and prior.last_price > 0 and price != prior.last_price:
        pct = float((price - prior.last_price) / prior.last_price * 100)
        if abs(pct) >= min_price_change_pct:
            et = EventType.PRICE_DROP if pct < 0 else EventType.PRICE_INCREASE
            events.append(DetectedEvent(et, prev, state, prior.last_price, price))
    return events
