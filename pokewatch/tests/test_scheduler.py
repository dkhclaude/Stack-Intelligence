from datetime import timedelta

from sqlalchemy import select

from pokewatch import locks
from pokewatch.db.models import JobLock, MonitoringJob
from pokewatch.db.session import session_scope
from pokewatch.domain import utcnow
from pokewatch.jobs import Runner, recover_stale_jobs
from pokewatch.scheduler import build_scheduler
from pokewatch.settings_store import get_runtime, save_runtime_override


def test_lock_prevents_duplicate_jobs(db):
    assert locks.acquire("job:x", 60, owner="a")
    assert not locks.acquire("job:x", 60, owner="b")
    assert locks.acquire("job:x", 60, owner="a")  # re-entrant for same owner
    locks.release("job:x", owner="a")
    assert locks.acquire("job:x", 60, owner="b")


def test_expired_lock_is_taken_over(db):
    with session_scope() as s:
        s.add(JobLock(name="job:y", owner="dead", acquired_at=utcnow() - timedelta(hours=2),
                      expires_at=utcnow() - timedelta(hours=1)))
    assert locks.acquire("job:y", 60, owner="new")


def test_job_skipped_when_locked(db):
    assert locks.acquire("job:discovery", 600, owner="other-worker")
    assert Runner().run("discovery") == []
    with session_scope() as s:
        j = s.scalars(select(MonitoringJob)).one()
        assert j.status == "skipped" and "lock" in j.error


def test_stale_running_jobs_recovered(db):
    with session_scope() as s:
        s.add(MonitoringJob(job_name="discovery", status="running", started_at=utcnow() - timedelta(hours=3)))
        s.add(MonitoringJob(job_name="discovery", status="running", started_at=utcnow()))
    assert recover_stale_jobs() == 1


def test_unconfigured_connectors_are_not_called(db, router):
    Runner(transport=router.transport).run("discovery")
    assert router.calls == []  # no Best Buy key, no Shopify stores, everything else unsupported


def test_scheduler_builds_jobs_from_runtime_settings(db):
    with session_scope() as s:
        save_runtime_override(s, {"intervals_s": {"priority_check": 120}})
    with session_scope() as s:
        assert get_runtime(s)["intervals_s"]["priority_check"] == 120
        assert get_runtime(s)["intervals_s"]["discovery"] == 1800
    sched = build_scheduler(Runner())
    ids = {j.id for j in sched.get_jobs()}
    assert {"priority_check", "upcoming_check", "discovery", "catalog_refresh", "health", "config_reload"} <= ids
    trig = sched.get_job("priority_check").trigger
    assert trig.interval.total_seconds() == 120 and trig.jitter == 45
    # defaults are applied to every job when the scheduler starts
    assert sched._job_defaults["max_instances"] == 1 and sched._job_defaults["coalesce"] is True


def test_connector_crash_does_not_kill_job(settings, router, monkeypatch):
    from pokewatch.connectors.bestbuy import BestBuyConnector

    def explode(self, q):
        raise RuntimeError("parser bug")
    monkeypatch.setattr(BestBuyConnector, "discover", explode)
    ids = Runner(transport=router.transport).run("discovery")
    with session_scope() as s:
        j = s.get(MonitoringJob, ids[0])
        assert j.status == "failed" and "parser bug" in j.error
