"""Cross-process job locks with TTL (duplicate-job prevention)."""

from __future__ import annotations

import os
import socket
from datetime import timedelta

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from .db.models import JobLock
from .db.session import session_scope
from .domain import utcnow

OWNER = f"{socket.gethostname()}:{os.getpid()}"


def acquire(name: str, ttl_s: int, owner: str = OWNER) -> bool:
    now = utcnow()
    exp = now + timedelta(seconds=ttl_s)
    try:
        with session_scope() as s:
            res = s.execute(update(JobLock).where(JobLock.name == name,
                                                  (JobLock.expires_at < now) | (JobLock.owner == owner))
                            .values(owner=owner, acquired_at=now, expires_at=exp))
            if res.rowcount == 1:
                return True
            if s.get(JobLock, name) is not None:
                return False  # held by someone else, not expired
            s.add(JobLock(name=name, owner=owner, acquired_at=now, expires_at=exp))
        return True
    except IntegrityError:
        return False


def release(name: str, owner: str = OWNER) -> None:
    with session_scope() as s:
        s.execute(delete(JobLock).where(JobLock.name == name, JobLock.owner == owner))
