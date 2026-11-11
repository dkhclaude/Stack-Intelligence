import httpx

from pokewatch.config import get_settings
from pokewatch.store_finder import add_to_env, check_store, normalize_domain
from tests.conftest import load, nosleep


def run(router, url="https://Shop.Test/collections/x"):
    return check_store(url, get_settings(), transport=router.transport, sleep=nosleep)


def test_usable_store_picks_pokemon_sealed_collection(db, router):
    router.add("shop.test/robots.txt", httpx.Response(200, text="User-agent: *\nDisallow: /cart\n"))
    router.add("shop.test/products.json", httpx.Response(200, json={"products": []}))
    router.add("shop.test/collections.json", httpx.Response(200, json={"collections": [
        {"handle": "magic", "title": "Magic: The Gathering", "products_count": 300},
        {"handle": "pokemon-singles", "title": "Pokemon Singles", "products_count": 900},
        {"handle": "pokemon-sealed", "title": "Pokémon Sealed Product", "products_count": 40},
    ]}))
    router.add("shop.test/collections/pokemon-sealed/products.json", httpx.Response(200, json=load("shopify_products.json")))
    r = run(router)
    assert r.domain == "shop.test" and r.is_shopify and r.ok
    assert r.chosen_collection == "pokemon-sealed"
    assert r.tcg_listings == 3 and r.in_stock == 2  # card sleeves filtered out
    assert r.config_line == "Shop|shop.test|pokemon-sealed"


def test_not_shopify(db, router):
    router.add("shop.test/robots.txt", httpx.Response(200, text=""))
    router.add("shop.test/products.json", httpx.Response(404, text="not found"))
    r = run(router)
    assert not r.ok and "Not a Shopify store" in r.problem


def test_robots_disallow_respected(db, router):
    router.add("shop.test/robots.txt", httpx.Response(200, text="User-agent: *\nDisallow: /products.json\n"))
    r = run(router)
    assert not r.ok and "robots.txt" in r.problem
    assert not any("products.json" in str(c.url) for c in router.calls)


def test_bot_wall_respected(db, router):
    router.add("shop.test/robots.txt", httpx.Response(200, text=""))
    router.add("shop.test/products.json", httpx.Response(403, headers={"content-type": "text/html"}, text="captcha"))
    r = run(router)
    assert not r.ok and "bot protection" in r.problem


def test_add_to_env_appends_and_dedupes(tmp_path):
    env = tmp_path / ".env"
    env.write_text("DISCORD_WEBHOOK_URL=x\nSHOPIFY_STORES=\n")
    assert add_to_env("A|a.com|pokemon", env) == "A|a.com|pokemon"
    assert add_to_env("B|b.com|all", env) == "A|a.com|pokemon;B|b.com|all"
    assert add_to_env("A|a.com|pokemon-sealed", env) == "B|b.com|all;A|a.com|pokemon-sealed"
    assert env.read_text().startswith("DISCORD_WEBHOOK_URL=x\n")


def test_normalize_domain():
    assert normalize_domain("https://www.Example.com/collections/pokemon") == "www.example.com"
