"""Monitoring jobs. Each is safe to run from the scheduler, CLI, or tests."""

from __future__ import annotations

import logging
import os
import socket
import time
from datetime import timedelta

from sqlalchemy import or_, select, update

from . import __version__, circuit, locks
from .alerts import create_alerts, dispatch_pending
from .config import Settings, get_settings
from .connectors import build_connectors, build_release_sources
from .connectors.base import Connector, UnsupportedConnector
from .db.models import MonitoringJob, RetailerListing
from .db.session import session_scope
from .domain import CheckFailure, CheckResult, CheckStatus, StockState, utcnow
from .pipeline import ingest, sync_connectors, upsert_releases
from .settings_store import get_runtime, log_event, set_value

log = logging.getLogger(__name__)

JOB_NAMES = ("priority_check", "upcoming_check", "discovery", "catalog_refresh")


class Runner:
    """Holds connector instances; tests inject an httpx transport."""

    def __init__(self, settings: Settings | None = None, transport=None, alert_transport=None, sleep=time.sleep):
        self.settings = settings or get_settings()
        self.transport, self.alert_transport, self.sleep = transport, alert_transport, sleep

    def _runtime(self):
        with session_scope() as s:
            return get_runtime(s)

    def connectors(self, runtime) -> list[Connector]:
        conns = build_connectors(self.settings, runtime, transport=self.transport, sleep=self.sleep)
        with session_scope() as s:
            sync_connectors(s, conns)
        return conns

    # -- selection ------------------------------------------------------
    @staticmethod
    def _select(s, job: str, connector: str) -> list[RetailerListing]:
        q = select(RetailerListing).where(RetailerListing.connector == connector, RetailerListing.active.is_(True),
                                          RetailerListing.watch.is_(True))
        today = utcnow().date()
        upcoming = or_(RetailerListing.last_confirmed_state.in_([StockState.PREORDER.value, StockState.COMING_SOON.value]),
                       RetailerListing.release_date >= today)
        if job == "priority_check":
            q = q.where(RetailerListing.priority >= 2)
        elif job == "upcoming_check":
            q = q.where(RetailerListing.priority < 2, upcoming)
        return list(s.scalars(q).all())

    def _due(self, s, job: str, conn: Connector, runtime) -> bool:
        min_iv = int(conn.conf.get("min_interval_s", 0))
        if not min_iv:
            return True
        last = s.scalar(select(MonitoringJob.started_at).where(
            MonitoringJob.job_name == job, MonitoringJob.connector == conn.code,
            MonitoringJob.status.in_(["ok", "partial", "failed"])).order_by(MonitoringJob.started_at.desc()).limit(1))
        return last is None or utcnow() - last >= timedelta(seconds=min_iv * 0.9)

    # -- jobs -----------------------------------------------------------
    def run(self, job: str) -> list[int]:
        if job == "release_sync":
            return [self.release_sync()]
        if job == "catalog_refresh":
            self.release_sync()
        lock = f"job:{job}"
        if not locks.acquire(lock, ttl_s=1800):
            with session_scope() as s:
                s.add(MonitoringJob(job_name=job, status="skipped", finished_at=utcnow(), error="already running (lock held)"))
            log.info("job skipped, lock held", extra={"job": job})
            return []
        ids = []
        try:
            runtime = self._runtime()
            for conn in self.connectors(runtime):
                if isinstance(conn, UnsupportedConnector) or not conn.configured()[0]:
                    continue
                if not conn.conf.get("enabled", True):
                    continue
                ids.append(self._run_connector(job, conn, runtime))
        finally:
            locks.release(lock)
        self.dispatch()
        return ids

    def _run_connector(self, job: str, conn: Connector, runtime) -> int:
        with session_scope() as s:
            ok, why = circuit.can_run(s, conn.code)
            mj = MonitoringJob(job_name=job, connector=conn.code, status="running")
            s.add(mj)
            s.flush()
            job_id = mj.id
            if not ok:
                mj.status, mj.error, mj.finished_at = "skipped", why, utcnow()
                return job_id
            if not self._due(s, job, conn, runtime):
                mj.status, mj.error, mj.finished_at = "skipped", "connector min_interval not elapsed", utcnow()
                return job_id
            listings = [] if job == "discovery" else self._select(s, job, conn.code)
            pids = [l.retailer_product_id for l in listings]

        if job != "discovery" and not pids:
            with session_scope() as s:
                mj = s.get(MonitoringJob, job_id)
                mj.status, mj.finished_at, mj.error = "ok", utcnow(), "nothing to check"
            return job_id

        t0 = time.monotonic()
        try:
            result = conn.discover(runtime["discovery_queries"]) if job == "discovery" else conn.check(pids)
        except Exception as e:  # connector bug: never crash the scheduler
            log.exception("connector crashed", extra={"connector": conn.code, "job": job})
            result = CheckResult(conn.code, fatal=CheckFailure(None, CheckStatus.ERROR, f"{type(e).__name__}: {e}"))

        with session_scope() as s:
            requested = [s.get(RetailerListing, l.id) for l in listings]
            stats = ingest(s, conn, result, runtime, job_id=job_id, requested=requested)
            alerts = 0
            for listing, events in stats.events:
                if create_alerts(s, listing, events, runtime):
                    alerts += 1
            mj = s.get(MonitoringJob, job_id)
            mj.finished_at = utcnow()
            mj.items_checked, mj.items_failed = stats.checked, stats.failed
            mj.new_listings, mj.events_created, mj.alerts_created = stats.new_listings, stats.event_count, alerts
            mj.requests_made = result.requests_made
            if result.fatal:
                mj.status, mj.error = "failed", f"{result.fatal.status}: {result.fatal.message}"
            else:
                mj.status = "partial" if stats.failed else "ok"
            log.info("job finished", extra={"job": job, "connector": conn.code, "status": mj.status,
                                            "checked": stats.checked, "failed": stats.failed, "new": stats.new_listings,
                                            "events": stats.event_count, "alerts": alerts,
                                            "skipped_non_tcg": stats.skipped_non_tcg,
                                            "secs": round(time.monotonic() - t0, 2)})
        return job_id

    def release_sync(self) -> int:
        runtime = self._runtime()
        total, errors = 0, []
        with session_scope() as s:
            mj = MonitoringJob(job_name="release_sync", connector="releases", status="running")
            s.add(mj)
            s.flush()
            job_id = mj.id
        for src in build_release_sources(self.settings, runtime, transport=self.transport, sleep=self.sleep):
            try:
                releases = src.fetch()
                with session_scope() as s:
                    total += upsert_releases(s, releases)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{src.code}: {e}")
                with session_scope() as s:
                    log_event(s, src.code, "release_fetch_failed", str(e), level="WARNING")
        with session_scope() as s:
            mj = s.get(MonitoringJob, job_id)
            mj.finished_at, mj.new_listings = utcnow(), total
            mj.status = "partial" if errors else "ok"
            mj.error = "; ".join(errors) or None
        return job_id

    def dispatch(self) -> int:
        with session_scope() as s:
            return dispatch_pending(s, self.settings, transport=self.alert_transport)


def heartbeat() -> None:
    with session_scope() as s:
        set_value(s, "worker_heartbeat", {"ts": utcnow().isoformat(), "host": socket.gethostname(),
                                          "pid": os.getpid(), "version": __version__})


def recover_stale_jobs(max_age_minutes: int = 60) -> int:
    with session_scope() as s:
        res = s.execute(update(MonitoringJob).where(MonitoringJob.status == "running",
                                                    MonitoringJob.started_at < utcnow() - timedelta(minutes=max_age_minutes))
                        .values(status="abandoned", finished_at=utcnow(), error="worker restarted / job abandoned"))
        if res.rowcount:
            log_event(s, "scheduler", "recovered_stale_jobs", f"{res.rowcount} stale jobs marked abandoned", level="WARNING")
        return res.rowcount
