"""End-to-end: connector (mock HTTP) -> pipeline -> events -> alerts -> Discord (mock)."""

import copy
import json

import httpx
from sqlalchemy import func, select

from pokewatch.db.models import (Alert, InventoryObservation, ListingEvent, PriceHistory, Product,
                                 RetailerConnector, RetailerListing)
from pokewatch.db.session import session_scope
from pokewatch.jobs import Runner
from tests.conftest import load, nosleep


class BB:
    """Scriptable Best Buy API + Discord webhook."""

    def __init__(self, router):
        self.data = load("bestbuy_search.json")
        self.mode = "ok"
        self.discord = []
        router.add("api.bestbuy.com", self.handle)
        router.add("discord.com/api/webhooks", self.hook)

    def handle(self, req):
        if self.mode == "timeout":
            raise httpx.ReadTimeout("t", request=req)
        if self.mode == "captcha":
            return httpx.Response(403, headers={"content-type": "text/html"}, text="captcha")
        return httpx.Response(200, json=self.data)

    def hook(self, req):
        self.discord.append(json.loads(req.content))
        return httpx.Response(204)

    def set(self, sku, **fields):
        for p in self.data["products"]:
            if p["sku"] == sku:
                p.update(fields)


def runner(router):
    from pokewatch.settings_store import save_runtime_override
    with session_scope() as s:  # tests run scans back-to-back
        save_runtime_override(s, {"connectors": {"bestbuy": {"min_interval_s": 0}},
                                  "alerts": {"quiet_first_scan": False}})
    return Runner(transport=router.transport, alert_transport=router.transport, sleep=nosleep)


def count(model, *where):
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


def test_discovery_creates_listings_products_and_alerts(settings, router):
    bb = BB(router)
    r = runner(router)
    r.run("discovery")
    assert count(RetailerListing) == 3  # Nintendo Switch game filtered out
    assert count(Product) == 3
    with session_scope() as s:
        etb = s.scalar(select(RetailerListing).where(RetailerListing.retailer_product_id == "6606082"))
        assert etb.current_state == "IN_STOCK" and etb.ever_in_stock and etb.product.upc == "00820650859571"
        rc = s.get(RetailerConnector, "bestbuy")
        assert rc.verified_live is False  # mocked data never marks a connector live
    assert count(Alert, Alert.status == "sent") == 3
    titles = [m["embeds"][0]["title"] for m in bb.discord]
    assert any("Prismatic" in t for t in titles)
    emb = bb.discord[0]["embeds"][0]
    assert emb["url"].startswith("https://www.bestbuy.com/site/")
    assert "XX" not in json.dumps(bb.discord)

    # repeated scans: no duplicate listings, products or alerts
    for _ in range(3):
        r.run("discovery")
    assert count(RetailerListing) == 3 and count(Product) == 3 and count(Alert) == 3
    assert count(InventoryObservation) == 12
    assert count(PriceHistory) == 3  # unchanged prices are not re-recorded within 6h


def test_restock_flow_with_unknown_gap(settings, router):
    bb = BB(router)
    r = runner(router)
    r.run("discovery")
    with session_scope() as s:
        for l in s.scalars(select(RetailerListing)):
            l.priority = 3
    # sold out
    bb.set(6606082, onlineAvailability=False, inStoreAvailability=False, orderable="SoldOut")
    r.run("priority_check")
    # retailer times out -> UNKNOWN, confirmed state stays OUT_OF_STOCK
    bb.mode = "timeout"
    r.run("priority_check")
    with session_scope() as s:
        etb = s.scalar(select(RetailerListing).where(RetailerListing.retailer_product_id == "6606082"))
        assert etb.current_state == "UNKNOWN" and etb.last_confirmed_state == "OUT_OF_STOCK"
    # back in stock -> exactly one RESTOCKED alert
    bb.mode = "ok"
    bb.set(6606082, onlineAvailability=True, orderable="Available")
    r.run("priority_check")
    assert count(ListingEvent, ListingEvent.event_type == "RESTOCKED") == 1
    assert count(ListingEvent, ListingEvent.event_type == "SOLD_OUT") == 1
    restock = [m for m in bb.discord if "RESTOCK" in m["embeds"][0]["description"]]
    assert len(restock) == 1
    status = [f["value"] for f in restock[0]["embeds"][0]["fields"] if f["name"] == "Status"][0]
    assert status == "IN STOCK — SHIPPING"
    # no repeat alert on next scan
    r.run("priority_check")
    assert len([m for m in bb.discord if "RESTOCK" in m["embeds"][0]["description"]]) == 1


def test_blocked_marks_unknown_and_opens_circuit(settings, router):
    bb = BB(router)
    r = runner(router)
    r.run("discovery")
    with session_scope() as s:
        for l in s.scalars(select(RetailerListing)):
            l.priority = 3
    bb.mode = "captcha"
    r.run("priority_check")
    with session_scope() as s:
        etb = s.scalar(select(RetailerListing).where(RetailerListing.retailer_product_id == "6606082"))
        assert etb.current_state == "UNKNOWN" and etb.last_confirmed_state == "IN_STOCK"
        assert s.get(RetailerConnector, "bestbuy").circuit_state == "open"
    calls = len(router.calls)
    r.run("priority_check")  # circuit open: no requests
    assert len(router.calls) == calls
    assert count(ListingEvent, ListingEvent.event_type == "SOLD_OUT") == 0


def test_price_drop_alert_and_cooldown(settings, router):
    bb = BB(router)
    r = runner(router)
    r.run("discovery")
    bb.set(6606082, salePrice=39.99)
    r.run("discovery")
    drops = [m for m in bb.discord if "PRICE DROP" in m["embeds"][0]["description"]]
    assert len(drops) == 1
    assert "was $49.99" in json.dumps(drops[0])
    with session_scope() as s:
        etb = s.scalar(select(RetailerListing).where(RetailerListing.retailer_product_id == "6606082"))
        assert str(etb.lowest_price) == "39.99" and str(etb.highest_price) == "49.99"
    # bounce back up and drop again within cooldown -> suppressed
    bb.set(6606082, salePrice=49.99)
    r.run("discovery")
    bb.set(6606082, salePrice=39.99)
    r.run("discovery")
    assert count(Alert, Alert.event_type == "PRICE_DROP", Alert.status == "suppressed") == 1
    assert len([m for m in bb.discord if "PRICE DROP" in m["embeds"][0]["description"]]) == 1


def test_no_channels_means_undelivered_not_faked(db, monkeypatch, router):
    monkeypatch.setenv("BESTBUY_API_KEY", "k")
    from pokewatch import config
    config.reset_settings()
    BB(router)
    runner(router).run("discovery")
    assert count(Alert, Alert.status == "undelivered") == 3


def test_min_interval_skips_back_to_back_scans(settings, router):
    BB(router)
    r = Runner(transport=router.transport, alert_transport=router.transport, sleep=nosleep)  # default 300s min interval
    r.run("discovery")
    n = len(router.calls)
    ids = r.run("discovery")
    from pokewatch.db.models import MonitoringJob
    with session_scope() as s:
        j = s.get(MonitoringJob, ids[0])
        assert j.status == "skipped" and "min_interval" in j.error
    assert len(router.calls) == n


def test_release_sync(settings, router, tmp_path):
    from pokewatch.db.models import ReleaseCalendar
    router.add("api.pokemontcg.io", httpx.Response(200, json=load("pokemontcg_sets.json")))
    runner(router).run("release_sync")
    runner(router).run("release_sync")
    assert count(ReleaseCalendar, ReleaseCalendar.source_name == "pokemontcg_io") == 2


def quiet_runner(router):
    from pokewatch.settings_store import save_runtime_override
    with session_scope() as s:
        save_runtime_override(s, {"connectors": {"bestbuy": {"min_interval_s": 0}}})  # quiet_first_scan default on
    return Runner(transport=router.transport, alert_transport=router.transport, sleep=nosleep)


def test_quiet_first_scan_sends_one_summary_then_alerts_on_changes(settings, router):
    bb = BB(router)
    r = quiet_runner(router)
    r.run("discovery")
    # everything recorded, no per-product alerts, exactly one summary message
    assert count(RetailerListing) == 3 and count(Alert) == 0
    assert len(bb.discord) == 1 and "now watching Best Buy: 3 Pokémon products" in bb.discord[0]["content"]
    assert "(2 available right now)" in bb.discord[0]["content"]  # ETB in stock + Charizard preorder
    # baseline does not count existing stock as "now available"
    assert count(ListingEvent, ListingEvent.event_type == "NOW_AVAILABLE") == 0
    assert count(ListingEvent, ListingEvent.event_type == "NEW_LISTING") == 3

    # second scan: real changes alert normally, and no second summary
    bb.data["products"].append({"sku": 6600009, "name": "Pokémon - Trading Card Game: Destined Rivals Booster Bundle",
                                "salePrice": 26.99, "onlineAvailability": True, "inStoreAvailability": False,
                                "orderable": "Available"})
    bb.set(6600001, onlineAvailability=True, orderable="Available")  # sold-out bundle comes back
    r.run("discovery")
    embeds = [m["embeds"][0] for m in bb.discord if "embeds" in m]
    assert len([m for m in bb.discord if "content" in m]) == 1
    assert any("Destined Rivals" in e["title"] for e in embeds)
    assert any("Surging Sparks" in e["title"] for e in embeds)


def test_quiet_first_scan_is_per_store(settings, router, monkeypatch):
    """A store added later gets its own quiet first scan even though another store already has listings."""
    bb = BB(router)
    r = quiet_runner(router)
    r.run("discovery")
    assert len(bb.discord) == 1
    monkeypatch.setenv("SHOPIFY_STORES", "Test Cards|shop.test|pokemon")
    from pokewatch import config
    config.reset_settings()
    router.add("shop.test/robots.txt", httpx.Response(200, text=""))
    router.add("shop.test/collections/pokemon/products.json", httpx.Response(200, json=load("shopify_products.json")))
    from pokewatch.settings_store import save_runtime_override
    with session_scope() as s:
        save_runtime_override(s, {"connectors": {"shopify": {"min_interval_s": 0}}})
    r2 = Runner(transport=router.transport, alert_transport=router.transport, sleep=nosleep)
    r2.run("discovery")
    summaries = [m["content"] for m in bb.discord if "content" in m]
    assert len(summaries) == 2 and "now watching Test Cards" in summaries[1]
    assert count(Alert) == 0
