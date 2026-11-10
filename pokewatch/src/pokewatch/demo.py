"""Build a SIMULATED database so the dashboard can be previewed before any
retailer credentials exist. Uses the real pipeline with a fake connector whose
retailers are clearly named "(simulated)". Never sends alerts. The dashboard
shows a DEMO banner whenever settings.demo_mode is true.
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from .alerts import create_alerts, seed_default_rules
from .classify import classify
from .connectors.base import Connector
from .db import session as dbs
from .db.models import MonitoringJob, ReleaseCalendar, RetailerListing
from .domain import CheckResult, ListingSnapshot, StockState as S, SupportLevel, utcnow
from .pipeline import ingest, sync_connectors
from .settings_store import get_runtime, set_value

CATALOG = [  # (title, price, priority)
    ("Pokémon TCG: Mega Evolution—Phantasmal Flames Elite Trainer Box", "49.99", 3),
    ("Pokémon TCG: Mega Evolution—Phantasmal Flames Booster Bundle", "26.99", 2),
    ("Pokémon TCG: Prismatic Evolutions Elite Trainer Box", "49.99", 3),
    ("Pokémon TCG: Prismatic Evolutions Super-Premium Collection", "79.99", 2),
    ("Pokémon TCG: Surging Sparks Booster Display Box (36 Packs)", "143.64", 2),
    ("Pokémon TCG: Destined Rivals Elite Trainer Box", "49.99", 2),
    ("Pokémon TCG: Charizard ex Premium Collection", "39.99", 1),
    ("Pokémon TCG: Journey Together Sleeved Booster Pack", "4.49", 1),
    ("Pokémon TCG: Black Bolt Binder Collection", "29.99", 1),
    ("Pokémon TCG: White Flare Booster Bundle", "26.99", 1),
]


def _img(label: str, hue: int) -> str:
    """Inline SVG placeholder (no external requests)."""
    from urllib.parse import quote
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200'><rect width='200' height='200' "
           f"fill='hsl({hue},45%,22%)'/><rect x='40' y='30' width='120' height='140' rx='10' fill='hsl({hue},55%,38%)'/>"
           f"<text x='100' y='105' font-family='sans-serif' font-size='13' fill='#fde047' text-anchor='middle'>{label}</text>"
           f"<text x='100' y='190' font-family='sans-serif' font-size='10' fill='#c3c2b7' text-anchor='middle'>SIMULATED</text></svg>")
    return "data:image/svg+xml," + quote(svg)


class DemoConnector(Connector):
    support_level = SupportLevel.SUPPORTED
    tier = 9

    def __init__(self, code, name, settings, runtime):
        super().__init__(settings, runtime)
        self.code, self.name = code, name
        self.status_note = "SIMULATED demo data — not a real retailer."
        self.queue: list[ListingSnapshot] = []

    def discover(self, queries):
        return CheckResult(self.code, snapshots=self.queue, requests_made=1)

    check = lambda self, ids: self.discover([])  # noqa: E731


def build_demo(path: str = "data/demo.db", seed: int = 7) -> Path:
    from .config import get_settings
    rnd = random.Random(seed)
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    for f in (p, p.with_name(p.name + "-wal"), p.with_name(p.name + "-shm")):
        if f.exists():
            f.unlink()
    dbs._engine = None
    dbs.init_db(f"sqlite:///{p}")
    settings = get_settings()
    with dbs.session_scope() as s:
        seed_default_rules(s)
        set_value(s, "demo_mode", True)
        runtime = get_runtime(s)
    conns = [DemoConnector("demo_a", "Demo Store A (simulated)", settings, runtime),
             DemoConnector("demo_b", "Demo Store B (simulated)", settings, runtime)]
    with dbs.session_scope() as s:
        sync_connectors(s, conns)

    start = utcnow() - timedelta(days=7)
    state = {}
    steps = 7 * 24 // 2  # every 2h for a week
    for step in range(steps + 1):
        t = start + timedelta(hours=2 * step)
        for ci, conn in enumerate(conns):
            conn.queue = []
            for i, (title, price, prio) in enumerate(CATALOG):
                if ci == 1 and i % 3 == 0:
                    continue  # store B doesn't carry everything
                if step < (i * 5) % 40:
                    continue  # staggered discovery
                key = (conn.code, i)
                st = state.get(key, S.PREORDER if i in (0, 1) and step < 30 else S.IN_STOCK)
                r = rnd.random()
                if st == S.IN_STOCK and r < 0.08:
                    st = S.OUT_OF_STOCK
                elif st == S.OUT_OF_STOCK and r < 0.12:
                    st = S.IN_STOCK
                elif st == S.PREORDER and step >= 30 and r < 0.3:
                    st = S.IN_STOCK
                state[key] = st
                obs_state = S.UNKNOWN if rnd.random() < 0.03 else st
                base = Decimal(price) * (Decimal("1.0") if ci == 0 else Decimal("1.06"))
                if rnd.random() < 0.05:
                    base = (base * Decimal("0.85"))
                conn.queue.append(ListingSnapshot(
                    retailer=conn.code, retailer_product_id=f"{conn.code}-{i}", title=title,
                    url=f"https://example.com/demo/{conn.code}/{i}", state=obs_state, evidence="simulated",
                    price=base.quantize(Decimal("0.01")), image_url=_img(classify(title).category.value, (i * 37) % 360),
                    ship_available=obs_state == S.IN_STOCK, pickup_available=(i % 2 == 0) and obs_state == S.IN_STOCK,
                    seller_name=conn.name, observed_at=t))
            with dbs.session_scope() as s:
                mj = MonitoringJob(job_name="discovery" if step % 3 == 0 else "priority_check", connector=conn.code,
                                   started_at=t, finished_at=t + timedelta(seconds=rnd.randint(2, 9)), status="running")
                s.add(mj)
                s.flush()
                stats = ingest(s, conn, conn.discover([]), runtime, job_id=mj.id)
                alerts = 0
                for listing, events in stats.events:
                    a = create_alerts(s, listing, events, runtime)
                    if a:
                        a.created_at = t
                        if a.status == "pending":
                            a.status = "dry_run"
                            a.deliveries = {"note": "demo — not sent"}
                        alerts += 1
                if rnd.random() < 0.04:
                    mj.status, mj.error, mj.items_failed = "failed", "timeout: simulated network timeout", len(conn.queue)
                else:
                    mj.status = "ok"
                mj.items_checked, mj.new_listings = stats.checked, stats.new_listings
                mj.events_created, mj.alerts_created, mj.requests_made = stats.event_count, alerts, 1
            with dbs.session_scope() as s:
                for l in s.query(RetailerListing).filter(RetailerListing.retailer == conn.code):
                    l.priority = CATALOG[int(l.retailer_product_id.rsplit("-", 1)[1])][2]
    with dbs.session_scope() as s:
        today = utcnow().date()
        for n, (name, days, conf, status) in enumerate([
            ("DEMO: Upcoming expansion A", 12, "announced", "confirmed"),
            ("DEMO: Holiday collection box", 25, "announced", "confirmed"),
            ("DEMO: Rumored special set", 60, "unconfirmed", "rumored"),
            ("DEMO: Mini tin wave", 40, "estimated", "rumored"),
        ]):
            s.add(ReleaseCalendar(source_name="demo", external_id=str(n), name=name,
                                  release_date=today + timedelta(days=days), date_confidence=conf, status=status,
                                  source_url="https://example.com/demo-source", product_type="Sealed (simulated)"))
        set_value(s, "worker_heartbeat", {"ts": utcnow().isoformat(), "host": "demo", "pid": 0, "version": "demo"})
    return p
