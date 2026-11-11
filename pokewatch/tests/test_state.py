from decimal import Decimal as D

from pokewatch.domain import EventType as E, StockState as S
from pokewatch.state import PriorState, detect_events


def types(evts):
    return [e.type for e in evts]


def test_new_listing_in_stock():
    assert types(detect_events(None, S.IN_STOCK, D("49.99"))) == [E.NEW_LISTING, E.NOW_AVAILABLE]


def test_new_listing_preorder():
    assert types(detect_events(None, S.PREORDER, None)) == [E.NEW_LISTING, E.PREORDER_AVAILABLE]


def test_restock_requires_prior_stock():
    assert types(detect_events(PriorState(S.OUT_OF_STOCK, True, None), S.IN_STOCK, None)) == [E.RESTOCKED]
    assert types(detect_events(PriorState(S.OUT_OF_STOCK, False, None), S.IN_STOCK, None)) == [E.NOW_AVAILABLE]


def test_unknown_never_creates_events():
    assert detect_events(PriorState(S.IN_STOCK, True, D("10")), S.UNKNOWN, None) == []
    assert detect_events(PriorState(S.OUT_OF_STOCK, True, D("10")), S.UNKNOWN, D("5")) == []


def test_unknown_gap_preserves_confirmed_state():
    # OUT -> UNKNOWN -> IN: prior stays OUT (pipeline never overwrites last_confirmed with UNKNOWN)
    assert types(detect_events(PriorState(S.OUT_OF_STOCK, True, None), S.IN_STOCK, None)) == [E.RESTOCKED]
    # IN -> UNKNOWN -> IN: no event
    assert detect_events(PriorState(S.IN_STOCK, True, None), S.IN_STOCK, None) == []


def test_sold_out_and_preorder_to_release():
    assert types(detect_events(PriorState(S.IN_STOCK, True, None), S.OUT_OF_STOCK, None)) == [E.SOLD_OUT]
    assert types(detect_events(PriorState(S.PREORDER, False, None), S.IN_STOCK, None)) == [E.NOW_AVAILABLE]
    assert types(detect_events(PriorState(S.COMING_SOON, False, None), S.PREORDER, None)) == [E.PREORDER_AVAILABLE]


def test_price_changes():
    ev = detect_events(PriorState(S.IN_STOCK, True, D("59.99")), S.IN_STOCK, D("49.99"))
    assert types(ev) == [E.PRICE_DROP] and ev[0].old_price == D("59.99")
    assert types(detect_events(PriorState(S.IN_STOCK, True, D("49.99")), S.IN_STOCK, D("54.99"))) == [E.PRICE_INCREASE]
    assert detect_events(PriorState(S.IN_STOCK, True, D("49.99")), S.IN_STOCK, D("49.98")) == []  # < 1%
