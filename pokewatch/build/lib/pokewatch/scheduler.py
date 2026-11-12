"""Long-running worker process. Independent from the dashboard and from Claude."""

from __future__ import annotations

import logging
import signal

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .alerts import seed_default_rules
from .db.session import init_db, session_scope
from .jobs import JOB_NAMES, Runner, heartbeat, recover_stale_jobs
from .settings_store import get_runtime, get_value, log_event

log = logging.getLogger(__name__)


def build_scheduler(runner: Runner) -> BlockingScheduler:
    sched = BlockingScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 120})
    _schedule_all(sched, runner)
    sched.add_job(heartbeat, IntervalTrigger(seconds=60), id="health", replace_existing=True)
    sched.add_job(_reload_if_changed, IntervalTrigger(seconds=120), args=[sched, runner], id="config_reload",
                  replace_existing=True)

    def _listener(ev):
        with session_scope() as s:
            if ev.code == EVENT_JOB_ERROR:
                log_event(s, "scheduler", "job_error", repr(ev.exception), level="ERROR", job=ev.job_id)
            else:
                log_event(s, "scheduler", "job_missed", "misfire", level="WARNING", job=ev.job_id)

    sched.add_listener(_listener, EVENT_JOB_ERROR | EVENT_JOB_MISSED)
    return sched


_last_cfg: dict = {}


def _schedule_all(sched, runner: Runner) -> None:
    global _last_cfg
    with session_scope() as s:
        rt = get_runtime(s)
    iv, jitter = rt["intervals_s"], int(rt["jitter_s"])
    for name in JOB_NAMES:
        sched.add_job(runner.run, IntervalTrigger(seconds=int(iv[name]), jitter=jitter), args=[name], id=name,
                      replace_existing=True, next_run_time=None if name == "catalog_refresh" else _soon())
    _last_cfg = {"iv": dict(iv), "jitter": jitter}
    log.info("scheduled jobs", extra={"intervals": str(iv), "jitter_s": jitter})


def _soon():
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone.utc) + timedelta(seconds=5)


def _reload_if_changed(sched, runner: Runner) -> None:
    with session_scope() as s:
        rt = get_runtime(s)
    if {"iv": dict(rt["intervals_s"]), "jitter": int(rt["jitter_s"])} != _last_cfg:
        log.info("runtime settings changed; rescheduling")
        _schedule_all(sched, runner)


def run_worker() -> None:
    init_db()
    with session_scope() as s:
        seed_default_rules(s)
        log_event(s, "scheduler", "worker_start", "worker starting")
    recover_stale_jobs()
    heartbeat()
    runner = Runner()
    runner.connectors(_rt())  # register connectors so dashboard shows them immediately
    sched = build_scheduler(runner)

    def _stop(*_):
        log.info("shutdown requested")
        sched.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("worker started")
    sched.start()


def _rt():
    with session_scope() as s:
        return get_runtime(s)


def worker_heartbeat_age_s() -> float | None:
    from datetime import datetime
    from .domain import utcnow
    with session_scope() as s:
        hb = get_value(s, "worker_heartbeat")
    if not hb:
        return None
    return (utcnow() - datetime.fromisoformat(hb["ts"])).total_seconds()
