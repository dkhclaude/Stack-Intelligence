"""pokewatch command line."""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select

from .config import get_settings
from .logging_setup import setup_logging


def _init():
    from .alerts import seed_default_rules
    from .db.session import init_db, session_scope
    init_db()
    with session_scope() as s:
        seed_default_rules(s)


def cmd_init_db(a):
    _init()
    print(f"Database ready: {get_settings().database_url.split('@')[-1]}")


def cmd_worker(a):
    from .scheduler import run_worker
    run_worker()


def cmd_run(a):
    _init()
    from .jobs import Runner
    ids = Runner().run(a.job)
    _print_jobs(ids)


def _print_jobs(ids):
    from .db.models import MonitoringJob
    from .db.session import session_scope
    with session_scope() as s:
        for j in s.scalars(select(MonitoringJob).where(MonitoringJob.id.in_(ids))):
            print(f"{j.job_name:16} {j.connector or '-':22} {j.status:9} checked={j.items_checked} failed={j.items_failed} "
                  f"new={j.new_listings} events={j.events_created} alerts={j.alerts_created} req={j.requests_made} "
                  f"{j.error or ''}")


def cmd_connectors(a):
    _init()
    from .jobs import Runner
    from .db.models import RetailerConnector
    from .db.session import session_scope
    Runner().connectors(Runner()._runtime())
    with session_scope() as s:
        for rc in s.scalars(select(RetailerConnector).order_by(RetailerConnector.priority_tier, RetailerConnector.code)):
            live = "LIVE-VERIFIED" if rc.verified_live else "not live-verified"
            print(f"[P{rc.priority_tier}] {rc.name:18} {rc.support_level:18} configured={rc.configured!s:5} "
                  f"circuit={rc.circuit_state:6} {live}\n      {rc.status_note}")


def cmd_verify(a):
    """Make one real request through a connector and report exactly what came back."""
    _init()
    from .connectors import build_connectors
    from .db.models import RetailerConnector
    from .db.session import session_scope
    from .domain import utcnow
    from .jobs import Runner
    rt = Runner()._runtime()
    conns = {c.code: c for c in build_connectors(get_settings(), rt)}
    c = conns.get(a.connector)
    if c is None:
        sys.exit(f"unknown connector {a.connector}; known: {', '.join(conns)}")
    ok, why = c.configured()
    if not ok:
        sys.exit(f"NOT VERIFIED — {c.name}: {why}")
    res = c.discover([a.query])
    if res.fatal:
        sys.exit(f"NOT VERIFIED — {c.name}: {res.fatal.status}: {res.fatal.message}")
    print(f"{c.name}: {len(res.snapshots)} listings returned, {res.requests_made} requests")
    for snap in res.snapshots[:8]:
        print(f"  {snap.state:12} {snap.price or '-':>8} {snap.title[:80]}  [{snap.evidence}]")
    if res.snapshots:
        with session_scope() as s:
            rc = s.get(RetailerConnector, c.code)
            if rc:
                rc.verified_live = True
                rc.status_note = f"{c.status_note} Live-verified {utcnow():%Y-%m-%d %H:%M} UTC ({len(res.snapshots)} listings)."
        print("VERIFIED LIVE")
    else:
        print("Request succeeded but returned 0 listings — not marked verified.")


def cmd_watch(a):
    """Add a known product by retailer product ID (fetched live — never typed-in data)."""
    _init()
    from .connectors import build_connectors
    from .db.models import RetailerListing
    from .db.session import session_scope
    from .jobs import Runner
    from .pipeline import ingest, sync_connectors
    rt = Runner()._runtime()
    conns = {c.code: c for c in build_connectors(get_settings(), rt)}
    c = conns.get(a.retailer)
    if c is None or not c.configured()[0]:
        sys.exit(f"connector {a.retailer} not available/configured")
    res = c.check([a.product_id])
    with session_scope() as s:
        sync_connectors(s, list(conns.values()))
        ingest(s, c, res, rt)
        l = s.scalar(select(RetailerListing).where(RetailerListing.retailer == c.code,
                                                   RetailerListing.retailer_product_id == a.product_id))
        if l is None:
            sys.exit(f"could not add: {res.fatal or res.failures}")
        l.priority, l.watch = a.priority, True
        print(f"Watching [{l.priority}] {l.title} — {l.current_state} {l.current_price or ''}")


def cmd_test_alert(a):
    from .alerts.channels import ChannelError, send_test
    try:
        print(send_test(get_settings(), a.channel))
    except ChannelError as e:
        sys.exit(f"FAILED: {e}")


def cmd_health(a):
    from .scheduler import worker_heartbeat_age_s
    age = worker_heartbeat_age_s()
    status = {"worker_heartbeat_age_s": age, "healthy": age is not None and age < 240}
    print(json.dumps(status))
    sys.exit(0 if status["healthy"] else 1)


def cmd_check_store(a):
    """Check whether a store can be monitored; optionally add it to .env."""
    from .config import PROJECT_ROOT
    from .store_finder import add_to_env, check_store
    for url in a.urls:
        r = check_store(url, get_settings())
        print(f"\n{r.domain}")
        if r.collections:
            print("  Pokémon collections: " + ", ".join(f"{h} ({n if n is not None else '?'})" for h, _, n in r.collections))
        for line in r.samples:
            print("   ", line)
        if not r.ok:
            print(f"  NOT USABLE: {r.problem}")
            continue
        print(f"  USABLE: {r.tcg_listings} Pokémon TCG listings visible, {r.in_stock} available now "
              f"(collection: {r.chosen_collection or 'all'})")
        if a.add:
            value = add_to_env(r.config_line, PROJECT_ROOT / ".env")
            print(f"  Added to .env -> SHOPIFY_STORES={value}")
        else:
            print(f"  To monitor it, re-run with --add (or put this in SHOPIFY_STORES): {r.config_line}")
    if a.add:
        print("\nRestart the worker to pick up new stores:  launchctl kickstart -k gui/$(id -u)/com.pokewatch.worker")


def cmd_telegram_setup(a):
    """Interactive Telegram setup: token -> detect chat -> save to .env -> test message."""
    import getpass

    from .config import PROJECT_ROOT
    from .telegram_setup import SetupError, TelegramSetup, set_env_values
    print("Telegram setup\n"
          "  1. In Telegram, open a chat with @BotFather and send:  /newbot\n"
          "  2. Give it any name, then a username ending in 'bot' (e.g. pokewatch_alerts_bot)\n"
          "  3. BotFather replies with a token like 123456789:AAH...  Copy it.\n")
    token = a.token or getpass.getpass("Paste the token and press Enter (it stays hidden while you paste): ")
    try:
        ts = TelegramSetup(token)
        username = ts.bot_username()
        print(f"\nFound your bot: @{username}")
        print(f"Now on your iPhone open  https://t.me/{username}  and tap START (or send 'hi').")
        print("Waiting for your message (up to 2 minutes)...")
        chat_id, name = ts.find_chat(wait_s=a.wait)
        set_env_values(PROJECT_ROOT / ".env", {"TELEGRAM_BOT_TOKEN": ts.token, "TELEGRAM_CHAT_ID": chat_id})
        ts.send_test(chat_id)
    except SetupError as e:
        sys.exit(f"\nSetup not finished: {e}")
    print(f"\nConnected to {name}'s chat and saved to .env. A test message was sent to your phone.\n"
          "Restart the worker so it uses Telegram:  launchctl kickstart -k gui/$(id -u)/com.pokewatch.worker")


def cmd_demo(a):
    from .demo import build_demo
    path = build_demo(a.path)
    print(f"Demo database written to {path} (SIMULATED data, no alerts sent).\n"
          f"View it: DATABASE_URL=sqlite:///{path} streamlit run dashboard/app.py")


def main(argv=None):
    p = argparse.ArgumentParser(prog="pokewatch", description="Pokémon TCG release & restock monitor")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)
    sub.add_parser("worker", help="run the scheduler (long-running)").set_defaults(fn=cmd_worker)
    r = sub.add_parser("run", help="run one job now")
    r.add_argument("job", choices=["priority_check", "upcoming_check", "discovery", "catalog_refresh", "release_sync"])
    r.set_defaults(fn=cmd_run)
    sub.add_parser("connectors", help="list connector support/health").set_defaults(fn=cmd_connectors)
    v = sub.add_parser("verify", help="live-test one connector")
    v.add_argument("connector")
    v.add_argument("--query", default="pokemon elite trainer box")
    v.set_defaults(fn=cmd_verify)
    w = sub.add_parser("watch", help="add a product by retailer id")
    w.add_argument("retailer")
    w.add_argument("product_id")
    w.add_argument("--priority", type=int, default=3, choices=[0, 1, 2, 3])
    w.set_defaults(fn=cmd_watch)
    t = sub.add_parser("test-alert", help="send a test message")
    t.add_argument("channel", choices=["discord", "telegram", "email"])
    t.set_defaults(fn=cmd_test_alert)
    sub.add_parser("health", help="exit 0 if worker heartbeat is fresh").set_defaults(fn=cmd_health)
    cs = sub.add_parser("check-store", help="check whether online stores can be monitored (Shopify, robots.txt allowed)")
    cs.add_argument("urls", nargs="+", help="store website(s), e.g. https://example-cards.com")
    cs.add_argument("--add", action="store_true", help="add usable stores to .env")
    cs.set_defaults(fn=cmd_check_store)
    tg = sub.add_parser("telegram-setup", help="guided Telegram setup (finds your chat id automatically)")
    tg.add_argument("--token", help=argparse.SUPPRESS)
    tg.add_argument("--wait", type=int, default=120, help=argparse.SUPPRESS)
    tg.set_defaults(fn=cmd_telegram_setup)
    d = sub.add_parser("demo", help="build a simulated-data DB to preview the dashboard")
    d.add_argument("--path", default="data/demo.db")
    d.set_defaults(fn=cmd_demo)
    a = p.parse_args(argv)
    s = get_settings()
    setup_logging(s.log_level, s.json_logs)
    a.fn(a)


if __name__ == "__main__":
    main()
