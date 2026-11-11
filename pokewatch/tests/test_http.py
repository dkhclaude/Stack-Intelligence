import httpx
import pytest

from pokewatch.http import BlockedError, DisallowedError, PoliteClient, RateLimitedError, TimeoutFetchError
from tests.conftest import nosleep


def client(router, robots=False, retries=3):
    return PoliteClient("t", "PokeWatchTest", 600, 5, max_retries=retries, respect_robots=robots,
                        transport=router.transport, sleep=nosleep)


def test_retries_5xx_then_succeeds(router):
    seq = iter([httpx.Response(503, json={}), httpx.Response(502, json={}), httpx.Response(200, json={"ok": 1})])
    router.add("example.com/api", lambda r: next(seq))
    with client(router) as c:
        assert c.get("https://example.com/api").json() == {"ok": 1}
        assert c.requests_made == 3


def test_timeout_exhausts_retries(router):
    def boom(r):
        raise httpx.ReadTimeout("slow", request=r)
    router.add("example.com", boom)
    with client(router, retries=2) as c, pytest.raises(TimeoutFetchError):
        c.get("https://example.com/x")
    assert len(router.calls) == 3


def test_captcha_page_is_blocked_not_retried(router):
    router.add("example.com", httpx.Response(200, headers={"content-type": "text/html"},
                                             text="<html><div id='px-captcha'>Press & Hold</div></html>"))
    with client(router) as c, pytest.raises(BlockedError):
        c.get("https://example.com/p")
    assert len(router.calls) == 1


def test_html_403_is_blocked(router):
    router.add("example.com", httpx.Response(403, headers={"content-type": "text/html"}, text="Access Denied"))
    with client(router) as c, pytest.raises(BlockedError):
        c.get("https://example.com/p")


def test_429_honours_retry_after_then_gives_up(router):
    router.add("example.com", httpx.Response(429, headers={"Retry-After": "1", "content-type": "application/json"}, json={}))
    with client(router, retries=1) as c, pytest.raises(RateLimitedError):
        c.get("https://example.com/p")


def test_robots_disallow(router):
    router.add("shop.test/robots.txt", httpx.Response(200, text="User-agent: *\nDisallow: /collections/\n"))
    with client(router, robots=True) as c, pytest.raises(DisallowedError):
        c.get("https://shop.test/collections/pokemon/products.json")


def test_robots_unreadable_is_conservative(router):
    router.add("shop.test/robots.txt", httpx.Response(500, text="err"))
    with client(router, robots=True, retries=0) as c, pytest.raises(DisallowedError):
        c.get("https://shop.test/collections/x/products.json")
