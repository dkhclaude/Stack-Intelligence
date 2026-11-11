import json
from decimal import Decimal

import httpx
import pytest

from pokewatch.alerts.channels import TelegramChannel
from pokewatch.alerts.engine import _rule_matches
from pokewatch.alerts.formatting import IncompleteAlert, discord_payload, status_label, telegram_html, validate
from pokewatch.db.models import AlertRule, RetailerListing
from pokewatch.domain import EventType


def payload(**kw):
    p = {"event_type": "RESTOCKED", "product": "Prismatic Evolutions ETB", "retailer": "Best Buy",
         "status": "IN STOCK — SHIPPING", "price": "49.99", "url": "https://www.bestbuy.com/site/1.p",
         "last_verified": "2026-11-10 12:00:00", "last_verified_iso": "2026-11-10T12:00:00",
         "reasons": ["Back in stock"], "confidence": "TCG 95%", "image_url": "https://img/x.jpg"}
    p.update(kw)
    return p


def test_status_labels():
    assert status_label("IN_STOCK", True, False, False) == "IN STOCK — SHIPPING"
    assert status_label("IN_STOCK", False, True, False) == "IN STOCK — PICKUP ONLY"
    assert status_label("PREORDER", None, None, True) == "PREORDER AVAILABLE (third-party seller)"


def test_validate_rejects_missing_and_placeholders():
    validate(payload())
    with pytest.raises(IncompleteAlert):
        validate(payload(url=None))
    with pytest.raises(IncompleteAlert):
        validate(payload(price="$XX.XX"))


def test_discord_and_telegram_format():
    d = discord_payload(payload())
    e = d["embeds"][0]
    assert e["title"] == "Prismatic Evolutions ETB" and "RESTOCK" in e["description"]
    assert e["thumbnail"]["url"] == "https://img/x.jpg"
    assert any(f["value"] == "$49.99" for f in e["fields"])
    h = telegram_html(payload(product="A & B <ETB>"))
    assert "A &amp; B &lt;ETB&gt;" in h and 'href="https://www.bestbuy.com/site/1.p"' in h


def test_telegram_falls_back_to_text_when_photo_rejected(settings, monkeypatch, router):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    from pokewatch import config
    config.reset_settings()
    router.add("sendPhoto", httpx.Response(400, json={"ok": False, "description": "wrong file identifier"}))
    router.add("sendMessage", httpx.Response(200, json={"ok": True}))
    ch = TelegramChannel(config.get_settings(), router.transport)
    assert ch.send(payload()) == "sent"
    assert [c.url.path.rsplit("/", 1)[-1] for c in router.calls] == ["sendPhoto", "sendMessage"]
    assert json.loads(router.calls[1].content)["chat_id"] == "42"


def test_rule_filters():
    l = RetailerListing(retailer="bestbuy", title="Prismatic Evolutions ETB", category="Elite Trainer Box",
                        priority=2, current_price=Decimal("49.99"), is_marketplace=False, product_id=7)
    base = dict(enabled=True, event_types=[], retailers=[], categories=[], product_ids=[], keywords=[],
                min_priority=0, max_price=None, include_marketplace=False)
    assert _rule_matches(AlertRule(**base), l, EventType.RESTOCKED)
    assert not _rule_matches(AlertRule(**{**base, "retailers": ["walmart"]}), l, EventType.RESTOCKED)
    assert not _rule_matches(AlertRule(**{**base, "max_price": Decimal("40")}), l, EventType.RESTOCKED)
    assert not _rule_matches(AlertRule(**{**base, "min_priority": 3}), l, EventType.RESTOCKED)
    assert _rule_matches(AlertRule(**{**base, "keywords": ["prismatic"]}), l, EventType.RESTOCKED)
    assert not _rule_matches(AlertRule(**{**base, "event_types": ["PRICE_DROP"]}), l, EventType.RESTOCKED)
    l.is_marketplace = True
    assert not _rule_matches(AlertRule(**base), l, EventType.RESTOCKED)
