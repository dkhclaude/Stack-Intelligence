# Architecture

```
                ┌──────────────────────────── worker process (pokewatch worker) ────────────────────────────┐
                │  APScheduler (UTC, jitter, max_instances=1, coalesce)   + DB job locks (cross-process)    │
                │                                                                                            │
 priority 5m ──►│  Runner.run(job) ─► for each enabled+configured connector:                                │
 upcoming 10m ─►│     circuit.can_run?  min_interval elapsed?                                                │
 discovery 30m ►│     connector.discover(queries) | connector.check(ids)                                    │
 catalog 6h ───►│        └─ PoliteClient: token bucket · robots.txt · backoff+jitter · block detection       │
                │     pipeline.ingest(result)                                                               │
                │        ├─ classify (deterministic; Claude only for ambiguous titles, cached)              │
                │        ├─ inventory_observations (append-only, UNKNOWN on failures)                        │
                │        ├─ state.detect_events (pure)  → listing_events                                    │
                │        ├─ price_history (on change / 6h heartbeat), price flags                           │
                │        └─ normalize.link_listing → canonical products (UPC → key → fuzzy w/ vetoes)        │
                │     alerts.create_alerts (rules · dedup key per event · cooldown)                         │
                │  dispatch_pending → Discord / Telegram / Email (after the DB commit)                       │
                │  heartbeat every 60s → settings.worker_heartbeat  (`pokewatch health`)                     │
                └────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                             │  SQLite (dev) / PostgreSQL (prod)
                ┌────────────────────────────────────────────┴──────────────┐
                │ Streamlit dashboard (read + settings writes only)         │
                └───────────────────────────────────────────────────────────┘
```

The worker and the dashboard are **separate processes**. Closing the dashboard, your laptop's browser, or this
Claude conversation never stops monitoring.

## Key rules

| Concern | Rule (where) |
|---|---|
| Never fabricate availability | A state comes only from retailer fields, recorded verbatim in `evidence` (connectors). Missing fields → `UNKNOWN` |
| Failures ≠ out of stock | Timeout, block, CAPTCHA, 4xx/5xx, or a missing SKU → `UNKNOWN` observation; `last_confirmed_state` is untouched (`pipeline._unknown_observation`) |
| Restock definition | Confirmed IN_STOCK earlier → confirmed OUT_OF_STOCK → IN_STOCK. A gap of UNKNOWN checks in between is fine (`state.py`) |
| History preserved | `inventory_observations`, `price_history`, `listing_events`, `alerts`, `monitoring_jobs` are append-only |
| No duplicate products | `UNIQUE(retailer, retailer_product_id)` on listings; `UNIQUE(canonical_key)` and `UNIQUE(upc)` on products |
| No duplicate alerts | `alerts.dedup_key` = listing + event type + event id (unique), plus a per-listing/per-type cooldown |
| Wrong merges avoided | Hard vetoes: different UPC, category, pack count, exclusivity (e.g. Pokémon Center), set, or featured Pokémon (`normalize.py`) |
| Placeholder-free alerts | `formatting.validate` rejects missing observed fields and placeholder text |
| Mock ≠ live | `verified_live` is set only by `pokewatch verify` after a real successful response |
| Politeness | Per-retailer request budgets, robots.txt for web endpoints, Retry-After honoured, circuit breaker opens at once on blocks |
| LLM cost | Claude classifies only titles the deterministic classifier is unsure about, capped per scan, cached forever per title. Never on the stock-check path |

## Database tables

`products`, `retailer_listings`, `inventory_observations`, `price_history`, `listing_events`, `release_calendar`,
`alerts`, `alert_rules`, `retailer_connectors`, `monitoring_jobs`, `job_locks`, `system_events`, `settings`,
`ai_classification_cache`. Definitions: `src/pokewatch/db/models.py`.

## Code map

| Path | Purpose |
|---|---|
| `src/pokewatch/domain.py` | States, events, categories, snapshot dataclasses |
| `src/pokewatch/http.py`, `circuit.py`, `locks.py` | Polite client, circuit breaker, job locks |
| `src/pokewatch/connectors/` | `bestbuy.py`, `shopify.py`, `pokemontcg_io.py` (releases), `registry.py` (incl. unsupported) |
| `src/pokewatch/classify.py`, `normalize.py`, `ai.py` | Classification and canonical matching |
| `src/pokewatch/state.py`, `pipeline.py`, `pricing.py` | Transition detection, ingestion, price intelligence |
| `src/pokewatch/alerts/` | Rules engine, formatting, channels, dispatcher |
| `src/pokewatch/jobs.py`, `scheduler.py`, `cli.py` | Job runner, long-running worker, CLI |
| `dashboard/` | Streamlit app (7 pages) |
| `tests/` | 72 tests with mocked retailer responses |
