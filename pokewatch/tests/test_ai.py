"""AI classification hook — uses a fake client; no API calls in tests."""

from types import SimpleNamespace

import httpx
from sqlalchemy import func, select

from pokewatch.ai import AIClassification, AIClassifier
from pokewatch.config import DEFAULT_RUNTIME, get_settings
from pokewatch.connectors.shopify import ShopifyConnector
from pokewatch.db.models import AIClassificationCache, RetailerConnector, RetailerListing
from pokewatch.db.session import session_scope
from pokewatch.pipeline import ingest, sync_connectors
from tests.conftest import nosleep


class FakeMessages:
    def __init__(self, verdict):
        self.verdict, self.calls = verdict, []

    def parse(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=self.verdict)


def fake_client(verdict):
    return SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(verdict)))


def test_ambiguous_title_uses_ai_once_and_caches(settings, router):
    data = {"products": [{"id": 9, "title": "Pikachu Holiday Calendar 2026", "handle": "cal", "tags": [], "images": [],
                          "variants": [{"id": 999, "title": "Default Title", "price": "39.99", "available": True}]}]}
    router.add("robots.txt", httpx.Response(200, text=""))
    router.add("products.json", httpx.Response(200, json=data))
    conn = ShopifyConnector("Shop", "shop.test", "pokemon", get_settings(), DEFAULT_RUNTIME,
                            transport=router.transport, sleep=nosleep)
    client = fake_client(AIClassification(is_pokemon_tcg_sealed=True, category="Collection Box", set_name=None,
                                          pack_count=None, confidence=0.8, reason="Pokémon TCG advent calendar with packs"))
    ai = AIClassifier(get_settings(), max_calls=5, client=client)
    with session_scope() as s:
        sync_connectors(s, [conn])
        res = conn.discover([])
        # "Pikachu" only -> deterministic says not TCG (no 'pokemon') -> would be skipped without AI band match
        stats = ingest(s, conn, res, DEFAULT_RUNTIME | {"ai": {"enabled": True, "min_conf": 0.0, "max_conf": 0.6}}, ai=ai)
        assert stats.ai_classified == 1 and stats.new_listings == 1
        l = s.scalar(select(RetailerListing))
        assert l.category == "Collection Box" and l.tcg_confidence == 0.8
        assert s.scalar(select(func.count()).select_from(AIClassificationCache)) == 1
    call = client.beta.messages.calls[0]
    assert call["output_format"] is AIClassification and call["fallbacks"] == "default"
    assert call["output_config"] == {"effort": "low"}
    # second classification of same title hits the cache
    with session_scope() as s:
        assert ai.classify(s, "Pikachu Holiday Calendar 2026") is not None
    assert len(client.beta.messages.calls) == 1


def test_ai_not_used_without_key_or_for_confident_titles(db):
    ai = AIClassifier(get_settings())
    assert not ai.available
    with session_scope() as s:
        assert ai.classify(s, "anything") is None
