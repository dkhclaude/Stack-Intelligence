"""Per-connector circuit breaker persisted on retailer_connectors (visible in dashboard)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from .db.models import RetailerConnector
from .domain import utcnow

FAILURE_THRESHOLD = 3
BASE_COOLDOWN_MIN = 5
MAX_COOLDOWN_MIN = 240


def can_run(session: Session, code: str) -> tuple[bool, str]:
    rc = session.get(RetailerConnector, code)
    if rc is None:
        return False, "connector not registered"
    if not rc.enabled:
        return False, "disabled"
    if rc.circuit_state == "open":
        if rc.circuit_open_until and utcnow() >= rc.circuit_open_until:
            rc.circuit_state = "half_open"
            return True, "half_open trial"
        return False, f"circuit open until {rc.circuit_open_until:%H:%M} UTC"
    return True, "ok"


def record_success(session: Session, code: str) -> None:
    rc = session.get(RetailerConnector, code)
    rc.circuit_state = "closed"
    rc.consecutive_failures = 0
    rc.circuit_open_until = None
    rc.last_success_at = utcnow()


def record_failure(session: Session, code: str, error: str, hard: bool = False) -> None:
    """hard=True (blocked/captcha/auth) opens the circuit immediately."""
    rc = session.get(RetailerConnector, code)
    rc.consecutive_failures = (rc.consecutive_failures or 0) + 1
    rc.last_error_at = utcnow()
    rc.last_error = error[:2000]
    if hard or rc.consecutive_failures >= FAILURE_THRESHOLD or rc.circuit_state == "half_open":
        trips = max(1, rc.consecutive_failures - FAILURE_THRESHOLD + 1)
        minutes = min(MAX_COOLDOWN_MIN, BASE_COOLDOWN_MIN * (2 ** (trips - 1)))
        rc.circuit_state = "open"
        rc.circuit_open_until = utcnow() + timedelta(minutes=minutes)


def count_requests(session: Session, code: str, n: int) -> None:
    rc = session.get(RetailerConnector, code)
    today = utcnow().date()
    if rc.requests_day != today:
        rc.requests_day, rc.requests_today = today, 0
    rc.requests_today = (rc.requests_today or 0) + n
