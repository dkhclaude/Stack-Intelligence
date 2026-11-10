"""Runtime settings stored in the DB (editable from the dashboard)."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from .config import DEFAULT_RUNTIME
from .db.models import Setting, SystemEvent


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def get_runtime(session: Session) -> dict[str, Any]:
    row = session.get(Setting, "runtime")
    return _deep_merge(DEFAULT_RUNTIME, row.value if row and isinstance(row.value, dict) else {})


def save_runtime_override(session: Session, override: dict[str, Any]) -> None:
    row = session.get(Setting, "runtime")
    current = row.value if row and isinstance(row.value, dict) else {}
    merged = _deep_merge(current, override)
    if row:
        row.value = merged
    else:
        session.add(Setting(key="runtime", value=merged))


def get_value(session: Session, key: str, default: Any = None) -> Any:
    row = session.get(Setting, key)
    return row.value if row else default


def set_value(session: Session, key: str, value: Any) -> None:
    row = session.get(Setting, key)
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))


def log_event(session: Session, component: str, event: str, message: str = "", level: str = "INFO", **context: Any) -> None:
    session.add(SystemEvent(component=component, event=event, message=message[:4000], level=level,
                            context={k: (v if isinstance(v, (str, int, float, bool, type(None))) else str(v)) for k, v in context.items()}))
