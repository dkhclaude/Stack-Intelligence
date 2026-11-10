"""Send a playbook message to Kevin via NTFY and append it to today's journal.

    python3 claude/trading/spy0dte/notify.py fill  '{"symbol":"SPY 11/09 600C", ...}'
    python3 claude/trading/spy0dte/notify.py exit  '{...}'
    python3 claude/trading/spy0dte/notify.py stop  '{...}'

Env:
    NTFY_TOPIC   required to send (e.g. kevin-spy-0dte). Without it the message is only journaled.
    NTFY_SERVER  optional, default https://ntfy.sh

Only fills, exits and stop moves are sent. Everything else stays silent.
Fill messages must carry score, factors and tier.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
JOURNAL_DIR = ROOT / "claude" / "research" / "journal" / "spy-0dte"
PT = ZoneInfo("America/Los_Angeles")
KINDS = {"fill", "exit", "stop"}


def format_message(kind: str, d: dict) -> tuple[str, str]:
    if kind == "fill":
        for k in ("score", "factors", "tier"):
            if k not in d:
                raise ValueError(f"fill message requires '{k}'")
        title = f"FILL {d.get('side', '').upper()} {d.get('symbol', '')}".strip()
        body = (f"{d.get('qty', '?')}x @ {d.get('price', '?')} | score {d['score']}/6 {d['tier']}"
                f" (max risk ${d.get('max_risk', '?')}) | factors: {', '.join(d['factors'])}"
                f" | stop {d.get('stop', '?')} ({d.get('stop_basis', 'structural')})")
    elif kind == "exit":
        title = f"EXIT {d.get('symbol', '')}"
        body = (f"{d.get('qty', '?')}x @ {d.get('price', '?')} | P&L ${d.get('pnl', '?')}"
                f" | reason: {d.get('reason', '?')} | day P&L ${d.get('day_pnl', '?')}")
    else:
        title = f"STOP {d.get('symbol', '')}"
        body = (f"{d.get('old_stop', '?')} -> {d.get('new_stop', '?')} | {d.get('rule', '')}"
                f" | mark {d.get('mark', '?')} peak {d.get('peak', '?')}")
    return title, body


def journal(kind: str, d: dict, sent: bool, now: datetime | None = None) -> Path:
    now = now or datetime.now(PT)
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    path = JOURNAL_DIR / f"{now:%Y-%m-%d}.jsonl"
    with path.open("a") as f:
        f.write(json.dumps({"ts": now.isoformat(timespec="seconds"), "event": kind,
                            "ntfy_sent": sent, **d}) + "\n")
    return path


def send(title: str, body: str) -> bool:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("NTFY_TOPIC not set; message journaled only", file=sys.stderr)
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    req = urllib.request.Request(f"{server}/{topic}", data=body.encode(), method="POST",
                                 headers={"Title": title, "Tags": "chart_with_upwards_trend"})
    # ntfy.sh rate-limits shared egress IPs (HTTP 429); back off and retry a few times.
    for attempt, wait in enumerate((0, 10, 20, 30)):
        time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return 200 <= r.status < 300
        except urllib.error.HTTPError as e:
            print(f"NTFY send failed (try {attempt + 1}): {e}", file=sys.stderr)
            if e.code != 429:
                return False
        except Exception as e:  # network policy may block ntfy; never crash the trader
            print(f"NTFY send failed: {e}", file=sys.stderr)
            return False
    return False


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] not in KINDS:
        print(__doc__)
        return 2
    kind, d = argv[1], json.loads(argv[2])
    title, body = format_message(kind, d)
    sent = send(title, body)
    path = journal(kind, {**d, "message": f"{title}: {body}"}, sent)
    print(json.dumps({"sent": sent, "title": title, "body": body, "journal": str(path)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
