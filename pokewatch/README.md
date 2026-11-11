# ⚡ Project PokéWatch

Autonomous Pokémon TCG release and restock **monitoring and notification** agent.
It watches permitted retailer data sources, detects new listings, preorders, restocks and price drops, and alerts you
on Discord or Telegram with a direct link to the retailer's own product page.

> **Notification only.** No auto-buy, no checkout automation, no CAPTCHA or queue bypassing, no bulk buying.

## What works today

| Area | Status |
|---|---|
| Best Buy connector (official Products API) | ✅ built and tested against mocks · 🔑 needs `BESTBUY_API_KEY` · not live-verified yet |
| Shopify hobby-store connector (public storefront JSON, robots.txt enforced) | ✅ built and tested against mocks · not live-verified yet |
| Official set release dates (Pokémon TCG API) and curated release calendar | ✅ built and tested against mocks |
| Target, Walmart, Costco, GameStop, Pokémon Center, Sam's Club | Registered as unsupported or needs-approval, with reasons — see [docs/FEASIBILITY.md](docs/FEASIBILITY.md) |
| Inventory states, restock/preorder/price-drop detection, UNKNOWN on failures | ✅ |
| Product classification and cross-retailer matching with confidence | ✅ (+ optional Claude for ambiguous titles) |
| Alerts: Discord, Telegram, email · rules · dedup · cooldown | ✅ |
| Scheduler: intervals, jitter, budgets, backoff, circuit breakers, job locks, recovery, heartbeat | ✅ |
| Streamlit dashboard (7 pages) | ✅ |
| Docker Compose (Postgres + worker + dashboard + backups), systemd unit, CI | ✅ written · Docker build not run (no Docker daemon in the dev sandbox) |
| **macOS home install** (launchd services, keep-awake, daily backup) | ✅ `deploy/macos/install.sh` · service files validated in tests; not yet run on a real Mac |
| Tests | 72 passing on SQLite **and** PostgreSQL 16 |

## Run it on your Mac at home

```bash
cd pokewatch && ./deploy/macos/install.sh
```
Details, including how to stop the Mac from sleeping: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#mac-at-home-launchd).

## Quick start (local)

```bash
cd pokewatch
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt && pip install --no-deps -e .
cp .env.example .env          # add BESTBUY_API_KEY and DISCORD_WEBHOOK_URL (or TELEGRAM_*)

pokewatch init-db
pokewatch check-store https://some-card-shop.com --add   # no API key needed (Shopify stores)
pokewatch connectors                       # what is supported / configured
pokewatch verify bestbuy                   # one REAL request; marks the connector live-verified on success
pokewatch test-alert discord               # labelled test message
pokewatch run discovery                    # one discovery scan now
pokewatch watch bestbuy <SKU> --priority 3     # add a known Best Buy SKU (fetched live, never typed-in data)
pokewatch worker                           # long-running scheduler (keep this running)
streamlit run dashboard/app.py             # dashboard at http://localhost:8501
```

**Preview the dashboard without credentials:** `pokewatch demo` builds `data/demo.db` with *simulated* stores
(clearly bannered, nothing is sent), then run `DATABASE_URL=sqlite:///data/demo.db streamlit run dashboard/app.py`.

### No Best Buy key? Use card shops instead
Many online hobby and game stores run on Shopify, which PokéWatch can monitor with no API key.
`pokewatch check-store <url> [<url> ...]` checks each one with requests the store allows. It reports
whether the store is usable, which Pokémon collection to watch, how many sealed Pokémon products it can see,
and why not if the store isn't usable. Add `--add` to save usable stores into `.env`.

### Adding stores stays quiet
The first scan of a newly added store records all its current products silently and sends one summary message
("now watching …: N products"). After that you only get alerts for changes: restocks, new listings, preorders and
price drops. To turn this off, set `alerts.quiet_first_scan` to false.

### Telegram setup
1. Message **@BotFather** → `/newbot` → copy the token into `TELEGRAM_BOT_TOKEN`.
2. Send any message to your new bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy
   `message.chat.id` into `TELEGRAM_CHAT_ID`.

### Discord setup
Server Settings → Integrations → Webhooks → New Webhook → Copy URL → `DISCORD_WEBHOOK_URL`.

## Default schedule

| Job | Default | What it checks |
|---|---|---|
| `priority_check` | 5 min | Listings with priority ≥ 2 |
| `upcoming_check` | 10 min | Preorder, coming soon, or future release date |
| `discovery` | 30 min | Search queries per connector → new listings |
| `catalog_refresh` | 6 h | Every active listing, plus release-calendar sync |

All jobs have ±45 s jitter, and each connector has its own request budget and minimum interval.
Change them in **Settings**; the worker reloads within about 2 minutes.

## Docs
* [docs/FEASIBILITY.md](docs/FEASIBILITY.md) — retailer-by-retailer feasibility matrix
* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — design, invariants, data model
* [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — 24/7 hosting comparison, Docker, backups, costs
