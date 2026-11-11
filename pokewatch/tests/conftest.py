import json
import os
from pathlib import Path

import httpx
import pytest

from pokewatch import config
from pokewatch.db import session as dbsession

FIX = Path(__file__).parent / "fixtures"

CRED_VARS = ["BESTBUY_API_KEY", "SHOPIFY_STORES", "DISCORD_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
             "SMTP_HOST", "ALERT_EMAIL_TO", "LOCAL_ZIP", "ALERTS_DRY_RUN", "POKEMONTCG_API_KEY", "ANTHROPIC_API_KEY"]


def load(name):
    return json.loads((FIX / name).read_text())


@pytest.fixture
def db(tmp_path, monkeypatch):
    for v in CRED_VARS:
        monkeypatch.delenv(v, raising=False)
    # POKEWATCH_TEST_DATABASE_URL lets the whole suite run against Postgres too
    pg = os.getenv("POKEWATCH_TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", pg or f"sqlite:///{tmp_path / 'test.db'}")
    config.reset_settings()
    dbsession._engine = None
    dbsession._Session = None
    if pg:
        from pokewatch.db.models import Base
        Base.metadata.drop_all(dbsession.get_engine())
    dbsession.init_db()
    from pokewatch.alerts import seed_default_rules
    with dbsession.session_scope() as s:
        seed_default_rules(s)
    yield
    config.reset_settings()


@pytest.fixture
def settings(db, monkeypatch):
    monkeypatch.setenv("BESTBUY_API_KEY", "test-key")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/abc")
    config.reset_settings()
    return config.get_settings()


class Router:
    """Tiny programmable mock transport: route by host+path substring."""

    def __init__(self):
        self.routes = []
        self.calls = []

    def add(self, match, handler):
        self.routes.append((match, handler))

    def __call__(self, request: httpx.Request):
        self.calls.append(request)
        url = str(request.url)
        for match, handler in reversed(self.routes):
            if match in url:
                return handler(request) if callable(handler) else handler
        return httpx.Response(404, text="no route")

    @property
    def transport(self):
        return httpx.MockTransport(self)


@pytest.fixture
def router():
    return Router()


def nosleep(_):
    return None
