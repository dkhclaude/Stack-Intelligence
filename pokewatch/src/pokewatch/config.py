"""Configuration.

* Secrets and deployment settings come from environment variables (.env).
* Tunable, non-secret settings (intervals, rules, queries) have defaults here
  and can be overridden at runtime from the dashboard (stored in the
  `settings` table, see pokewatch.settings_store).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def _bool(name: str, default: bool) -> bool:
    v = _env(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'pokewatch.db'}"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    json_logs: bool = field(default_factory=lambda: _bool("JSON_LOGS", True))
    user_agent: str = field(default_factory=lambda: _env("POKEWATCH_USER_AGENT", "PokeWatch/0.2 (personal stock-alert bot; low-frequency)"))
    http_timeout_s: float = field(default_factory=lambda: float(_env("HTTP_TIMEOUT_S", "15")))

    # Retailer credentials
    bestbuy_api_key: str | None = field(default_factory=lambda: _env("BESTBUY_API_KEY"))
    pokemontcg_api_key: str | None = field(default_factory=lambda: _env("POKEMONTCG_API_KEY"))
    shopify_stores: str | None = field(default_factory=lambda: _env("SHOPIFY_STORES"))  # "Name|domain|collection,..."
    local_zip: str | None = field(default_factory=lambda: _env("LOCAL_ZIP"))

    # Notifications
    discord_webhook_url: str | None = field(default_factory=lambda: _env("DISCORD_WEBHOOK_URL"))
    telegram_bot_token: str | None = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str | None = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))
    smtp_host: str | None = field(default_factory=lambda: _env("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(_env("SMTP_PORT", "587")))
    smtp_user: str | None = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_password: str | None = field(default_factory=lambda: _env("SMTP_PASSWORD"))
    alert_email_to: str | None = field(default_factory=lambda: _env("ALERT_EMAIL_TO"))
    alerts_dry_run: bool = field(default_factory=lambda: _bool("ALERTS_DRY_RUN", False))

    # Optional AI classification for ambiguous titles
    anthropic_api_key: str | None = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    ai_model: str = field(default_factory=lambda: _env("POKEWATCH_AI_MODEL", "claude-opus-5-5"))


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None


# --------------------------------------------------------------------------
# Runtime-tunable defaults (overridable from the dashboard Settings page)
# --------------------------------------------------------------------------
DEFAULT_RUNTIME = {
    "intervals_s": {
        "priority_check": 300,  # priority watchlist products
        "upcoming_check": 600,  # known upcoming / preorder / coming soon
        "discovery": 1800,  # general product discovery
        "catalog_refresh": 21600,  # full catalog refresh + release calendar
        "health": 60,
    },
    "jitter_s": 45,
    "discovery_queries": [
        "pokemon elite trainer box",
        "pokemon booster bundle",
        "pokemon booster box",
        "pokemon premium collection",
        "pokemon trading card game",
    ],
    "connectors": {
        # per-connector overrides: enabled, request budget, min interval
        "bestbuy": {"enabled": True, "requests_per_minute": 60, "min_interval_s": 300},
        "shopify": {"enabled": True, "requests_per_minute": 10, "min_interval_s": 600},
        "pokemontcg_io": {"enabled": True, "requests_per_minute": 10, "min_interval_s": 3600},
    },
    "alerts": {
        "cooldown_minutes": 30,
        "min_price_drop_pct": 5.0,
        "price_drop_requires_availability": True,
        "include_marketplace": False,
        "min_tcg_confidence": 0.6,
        "channels": ["discord", "telegram"],
    },
    "pricing": {"inflated_vs_msrp_ratio": 1.4, "inflated_vs_market_ratio": 1.5},
    "matching": {"auto_link_threshold": 0.85, "review_threshold": 0.6},
    "local_store": {"zip": None, "max_store_distance_miles": 25},
    # Optional Claude classification, only for ambiguous titles (deterministic conf in this band)
    "ai": {"enabled": True, "min_conf": 0.3, "max_conf": 0.6, "max_calls_per_scan": 10},
}
