import httpx

from pokewatch.config import get_settings
from pokewatch.config import DEFAULT_RUNTIME
from pokewatch.connectors.bestbuy import BestBuyConnector, map_state
from pokewatch.connectors.pokemontcg_io import CuratedReleaseSource, PokemonTCGIOSource
from pokewatch.connectors.shopify import ShopifyConnector, parse_store_config
from pokewatch.domain import CheckStatus, StockState as S
from tests.conftest import load, nosleep


def bb(settings, router):
    return BestBuyConnector(settings, DEFAULT_RUNTIME, transport=router.transport, sleep=nosleep)


def test_bestbuy_state_mapping():
    assert map_state({"orderable": "Available", "onlineAvailability": True, "inStoreAvailability": True})[:3] == (S.IN_STOCK, True, True)
    assert map_state({"orderable": "Available", "onlineAvailability": False, "inStoreAvailability": True})[:3] == (S.IN_STOCK, False, True)
    assert map_state({"orderable": "SoldOut", "onlineAvailability": False, "inStoreAvailability": False})[0] == S.OUT_OF_STOCK
    assert map_state({"orderable": "PreOrder", "onlineAvailability": True})[0] == S.PREORDER
    assert map_state({"orderable": "ComingSoon"})[0] == S.COMING_SOON
    assert map_state({})[0] == S.UNKNOWN  # missing fields are never "out of stock"


def test_bestbuy_not_configured(db):
    c = BestBuyConnector(get_settings(), DEFAULT_RUNTIME)
    r = c.discover(["pokemon"])
    assert r.fatal.status == CheckStatus.NOT_CONFIGURED


def test_bestbuy_discover(settings, router):
    router.add("api.bestbuy.com/v1/products(", httpx.Response(200, json=load("bestbuy_search.json")))
    r = bb(settings, router).discover(["pokemon elite trainer box"])
    assert r.ok and len(r.snapshots) == 4
    etb = r.snapshots[0]
    assert etb.state == S.IN_STOCK and str(etb.price) == "49.99" and etb.ship_available is True
    assert etb.url == "https://www.bestbuy.com/site/6606082.p?skuId=6606082"
    assert etb.upc == "820650859571" and etb.image_url.startswith("https://")
    req = router.calls[0]
    assert "search=pokemon&search=elite" in str(req.url) and req.url.params["apiKey"] == "test-key"


def test_bestbuy_check_marks_missing_sku_unknown(settings, router):
    data = load("bestbuy_search.json")
    data["products"] = data["products"][:1]
    router.add("sku%20in(", httpx.Response(200, json=data))
    router.add("sku in(", httpx.Response(200, json=data))
    r = bb(settings, router).check(["6606082", "999"])
    assert [s.retailer_product_id for s in r.snapshots] == ["6606082"]
    assert r.failures[0].retailer_product_id == "999" and r.failures[0].status == CheckStatus.NOT_FOUND


def test_bestbuy_quota_and_bad_key(settings, router):
    router.add("api.bestbuy.com", httpx.Response(403, json={"errorMessage": "The provided API Key has reached the per second limit"}))
    assert bb(settings, router).discover(["x"]).fatal.status == CheckStatus.RATE_LIMITED
    router.add("api.bestbuy.com", httpx.Response(403, json={"errorMessage": "Invalid API key"}))
    assert bb(settings, router).discover(["x"]).fatal.status == CheckStatus.NOT_CONFIGURED


def test_bestbuy_timeout_is_failure_not_oos(settings, router):
    def boom(r):
        raise httpx.ConnectTimeout("t", request=r)
    router.add("api.bestbuy.com", boom)
    r = bb(settings, router).check(["6606082"])
    assert r.fatal.status == CheckStatus.TIMEOUT and r.snapshots == []


def test_bestbuy_malformed_response(settings, router):
    router.add("api.bestbuy.com", httpx.Response(200, json={"unexpected": True}))
    assert bb(settings, router).discover(["x"]).fatal.status == CheckStatus.INCOMPLETE


def shop(settings, router):
    return ShopifyConnector("Test Cards", "shop.test", "pokemon", settings, DEFAULT_RUNTIME,
                            transport=router.transport, sleep=nosleep)


def test_shopify_config_parse():
    assert parse_store_config("A Store|https://a.com/|pokemon; B|b.com") == [("A Store", "a.com", "pokemon"), ("B", "b.com", "all")]


def test_shopify_discover(settings, router):
    router.add("shop.test/robots.txt", httpx.Response(200, text="User-agent: *\nDisallow: /cart\n"))
    router.add("shop.test/collections/pokemon/products.json", httpx.Response(200, json=load("shopify_products.json")))
    r = shop(settings, router).discover([])
    by = {s.retailer_product_id: s for s in r.snapshots}
    assert by["111"].state == S.IN_STOCK and str(by["111"].price) == "54.99"
    assert by["222"].state == S.PREORDER
    assert by["444"].state == S.OUT_OF_STOCK
    assert by["111"].url == "https://shop.test/products/phantasmal-flames-etb?variant=111"


def test_shopify_blocked_by_bot_wall(settings, router):
    router.add("shop.test/robots.txt", httpx.Response(200, text=""))
    router.add("products.json", httpx.Response(200, headers={"content-type": "text/html"}, text="<title>Just a moment...</title><script src='/cdn-cgi/challenge-platform/x'>"))
    r = shop(settings, router).check(["111"])
    assert r.fatal.status == CheckStatus.BLOCKED


def test_shopify_respects_robots(settings, router):
    router.add("shop.test/robots.txt", httpx.Response(200, text="User-agent: *\nDisallow: /collections\n"))
    r = shop(settings, router).discover([])
    assert r.fatal.status == CheckStatus.DISALLOWED
    assert not any("products.json" in str(c.url) for c in router.calls)


def test_pokemontcg_sets(settings, router):
    router.add("api.pokemontcg.io/v2/sets", httpx.Response(200, json=load("pokemontcg_sets.json")))
    rel = PokemonTCGIOSource(settings, DEFAULT_RUNTIME, transport=router.transport, sleep=nosleep).fetch()
    assert rel[0].name == "Phantasmal Flames" and str(rel[0].release_date) == "2025-11-14"
    assert rel[0].status == "confirmed"


def test_curated_requires_source_for_confirmed(settings, tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("releases:\n - name: A\n   status: confirmed\n   release_date: 2026-03-01\n"
                 " - name: B\n   status: confirmed\n   source_url: https://press.pokemon.com/x\n")
    rel = CuratedReleaseSource(settings, DEFAULT_RUNTIME, path=p).fetch()
    assert rel[0].status == "rumored" and rel[1].status == "confirmed"
