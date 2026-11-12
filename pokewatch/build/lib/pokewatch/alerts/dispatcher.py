"""Deliver pending alerts. Runs after the DB transaction that created them commits."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db.models import Alert
from ..domain import utcnow
from ..settings_store import log_event
from .channels import ChannelError, build_channels
from .formatting import text_body

log = logging.getLogger(__name__)


def dispatch_pending(session: Session, settings: Settings, transport=None, limit: int = 50) -> int:
    channels = build_channels(settings, transport)
    pending = session.scalars(select(Alert).where(Alert.status == "pending").order_by(Alert.created_at).limit(limit)).all()
    sent = 0
    for alert in pending:
        wanted = alert.payload.get("channels") or list(channels)
        usable = [channels[c] for c in wanted if c in channels and channels[c].configured()]
        if settings.alerts_dry_run or not usable:
            alert.status = "dry_run" if settings.alerts_dry_run else "undelivered"
            alert.deliveries = {"note": "ALERTS_DRY_RUN=true" if settings.alerts_dry_run else "no notification channel configured"}
            log.info("alert not delivered", extra={"alert_id": alert.id, "status": alert.status, "body": text_body(alert.payload)})
            continue
        results = {}
        for ch in usable:
            try:
                results[ch.name] = ch.send(alert.payload)
            except ChannelError as e:
                results[ch.name] = f"failed: {e}"
                log_event(session, f"alerts.{ch.name}", "delivery_failed", str(e), level="ERROR", alert_id=alert.id)
        ok = [k for k, v in results.items() if v == "sent"]
        alert.deliveries = results
        alert.status = "sent" if len(ok) == len(results) else ("partial" if ok else "failed")
        if ok:
            alert.delivered_at = utcnow()
            sent += 1
    session.flush()
    return sent
