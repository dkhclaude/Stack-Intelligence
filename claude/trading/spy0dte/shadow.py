"""Phase A shadow twin (playbook v6): paper-trade a 1DTE twin of each live 0DTE entry.

Never places orders. Sizes the twin with engine.size (same factors, structural stop, account
state as the live trade) and walks the same stop ladder over 1-minute option bars:
  * stop checked against the bar low first (fill = min(stop, bar open) on a gap),
  * peak mark = highest 1-minute close (v4),
  * +50% scale-out on the close (engine.scale_out),
  * forced exit at the close of the bar at/after `exit_by_utc` (the live out-by/flat rule).
If the bars end before an exit, the twin is reported open and marked at the last close.
`next_open` (optional): the twin's price at the next session open, recorded as an overnight-hold
observation only (v6: overnight budget is $0, no live overnight holds).
`time_stop` (optional, low-delta paper test, 2026-11-22): {"minutes": 10, "min_gain": 0.30}. If no
1-minute close has reached entry x (1 + min_gain) by the close of bar number `minutes`, exit at that close.

    python3 shadow.py '{"entry_premium":0.92,"delta":0.23,"entry_underlying":760.87,
      "stop_underlying":759.93,"factors":{...},"account_value":896,"realized_pnl":0,
      "consecutive_losses":0,"side":"call","exit_by_utc":"2026-11-16T18:30:00Z",
      "bars":[["2026-11-16T16:09:00Z",0.95,0.90,0.94], ...]}'   # [begins_at, high, low, close]
"""
from __future__ import annotations

import json
import sys

import engine


def run(p: dict) -> dict:
    sz = engine.size(p)
    out = {"tier": sz["tier"], "score": sz["score"], "fits": sz["contracts"] > 0,
           "risk_per_contract": sz.get("risk_per_contract"), "contracts": sz["contracts"],
           "why": sz["reason"], "events": []}
    if not out["fits"]:
        out.update(pnl=0.0, exit=None)
        return out
    entry, n = p["entry_premium"], sz["contracts"]
    stop, peak, held, pnl, scaled = sz["option_stop"], entry, n, 0.0, False
    exit_by = p.get("exit_by_utc")
    out["initial_stop"] = stop
    ts_cfg = p.get("time_stop")
    for i, (ts, high, low, close) in enumerate(p["bars"]):
        o = p.get("opens", {}).get(ts, high)  # bar open if supplied; else assume no gap
        if low <= stop:
            px = round(min(stop, o), 2)
            pnl += (px - entry) * 100 * held
            out["events"].append([ts, "stop", px]); held = 0
            out["exit"] = {"ts": ts, "price": px, "reason": f"stop {stop:.2f}"}
            break
        peak = max(peak, close)
        k = engine.scale_out(held, entry, close, scaled)
        if k:
            pnl += (close - entry) * 100 * k; held -= k; scaled = True
            out["events"].append([ts, f"scale {k}", close])
        ns = engine.next_stop(entry, peak, stop)
        if ns["stop"] > stop:
            stop = ns["stop"]; out["events"].append([ts, "stop->", stop])
        if ts_cfg and held and i + 1 == ts_cfg["minutes"] and peak < entry * (1 + ts_cfg["min_gain"]):
            pnl += (close - entry) * 100 * held; held = 0
            out["exit"] = {"ts": ts, "price": close, "reason": f"time stop ({ts_cfg['minutes']} min, < +{int(ts_cfg['min_gain']*100)}%)"}
            break
        if exit_by and ts >= exit_by:
            pnl += (close - entry) * 100 * held; held = 0
            out["exit"] = {"ts": ts, "price": close, "reason": "time exit"}
            break
    if held:
        last = p["bars"][-1][3] if p["bars"] else entry
        pnl += (last - entry) * 100 * held
        out["exit"] = {"ts": None, "price": last, "reason": "still open (marked)"}
    out.update(pnl=round(pnl, 2), peak=peak, final_stop=stop)
    if "next_open" in p:
        out["overnight_obs"] = round((p["next_open"] - entry) * 100 * n, 2)
    return out


if __name__ == "__main__":
    print(json.dumps(run(json.loads(sys.argv[1])), indent=2))
