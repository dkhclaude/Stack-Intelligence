"""SPY 0DTE Momentum Playbook - deterministic risk engine.

Pure functions for scoring, tiering, sizing, daily limits and the exit-engine stop
ladder, plus a small CLI so a trading session can get the same answer every time:

    python3 claude/trading/spy0dte/engine.py score '{"trend":1,"structure":1,...}'
    python3 claude/trading/spy0dte/engine.py size '{...}'
    python3 claude/trading/spy0dte/engine.py stop '{...}'
    python3 claude/trading/spy0dte/engine.py limit '{"realized_pnl":12.5}'

Numbers come from config.json, which mirrors the newest playbook spec.
This module never places orders.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import time
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.json")
FACTORS = ("trend", "structure", "key_level", "breadth", "volume", "time")


def load_config(path: Path = CONFIG_PATH) -> dict:
    return json.loads(path.read_text())


CFG = load_config()


def _cents_down(x: float) -> float:
    return math.floor(round(x * 100, 6)) / 100


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


# ---------------------------------------------------------------- scoring
def in_time_window(now_pt: str, cfg: dict = CFG) -> bool:
    start, end = (_parse_hhmm(x) for x in cfg["time_window_pt"])
    return start <= _parse_hhmm(now_pt) <= end


def volume_factor(trigger_volume: float, prior_10: list[float], cfg: dict = CFG) -> bool:
    if len(prior_10) < 10:
        return False
    avg = sum(prior_10[-10:]) / 10
    return avg > 0 and trigger_volume >= cfg["volume_multiple"] * avg


def score(factors: dict, cfg: dict = CFG) -> dict:
    """factors: {name: bool} for the six FACTORS. Unknown keys rejected."""
    unknown = set(factors) - set(FACTORS)
    if unknown:
        raise ValueError(f"unknown factors: {sorted(unknown)}")
    hits = [f for f in FACTORS if factors.get(f)]
    s = len(hits)
    tier = cfg["tiers"].get(str(s))
    return {
        "score": s,
        "factors_hit": hits,
        "factors_missed": [f for f in FACTORS if f not in hits],
        "tier": tier["name"] if tier else None,
        "max_risk": tier["max_risk"] if tier else 0,
    }


def tier_by_name(name: str, cfg: dict = CFG) -> dict:
    for t in cfg["tiers"].values():
        if t["name"] == name:
            return t
    raise KeyError(name)


# ------------------------------------------------------------ day limits
def daily_loss_limit(realized_pnl: float, cfg: dict = CFG) -> float:
    d = cfg["daily_loss"]
    return min(d["base"] + d["profit_share"] * max(realized_pnl, 0.0), d["max"])


def effective_tier(score_result: dict, consecutive_losses: int, cfg: dict = CFG) -> dict:
    """Apply the losing-streak cap. Returns {'tier', 'max_risk', 'capped'}."""
    if score_result["tier"] is None:
        return {"tier": None, "max_risk": 0, "capped": False}
    cap = cfg["losing_streak_cap"]
    if consecutive_losses >= cap["streak"]:
        t = tier_by_name(cap["tier"], cfg)
        if t["max_risk"] < score_result["max_risk"]:
            return {"tier": t["name"], "max_risk": t["max_risk"], "capped": True}
    return {"tier": score_result["tier"], "max_risk": score_result["max_risk"], "capped": False}


# ----------------------------------------------------------------- sizing
def option_stop_price(entry_premium: float, delta: float,
                      entry_underlying: float, stop_underlying: float) -> float:
    """Structural underlying stop -> option price via delta (floor $0.01)."""
    move = abs(entry_underlying - stop_underlying)
    return max(_cents_down(entry_premium - abs(delta) * move), 0.01)


def size(p: dict, cfg: dict = CFG) -> dict:
    """Size a trade.

    p keys: factors (dict), entry_premium, delta, entry_underlying, stop_underlying,
    account_value, realized_pnl (today, net), consecutive_losses, side ('call'|'put').
    """
    sc = score(p["factors"], cfg)
    eff = effective_tier(sc, p.get("consecutive_losses", 0), cfg)
    out = {**sc, "tier": eff["tier"], "max_risk": eff["max_risk"], "streak_capped": eff["capped"]}

    def skip(reason: str) -> dict:
        return {**out, "contracts": 0, "trade": False, "reason": reason}

    if eff["tier"] is None:
        return skip(f"score {sc['score']} < 3: no trade")

    side = p.get("side", "call")
    eu, su = p["entry_underlying"], p["stop_underlying"]
    if (side == "call" and su >= eu) or (side == "put" and su <= eu):
        return skip("structural stop is on the wrong side of entry")

    realized = p.get("realized_pnl", 0.0)
    limit = daily_loss_limit(realized, cfg)
    room = limit + realized  # dollars that can still be lost today
    out["daily_loss_limit"] = round(limit, 2)
    out["daily_room"] = round(room, 2)
    if room <= 0:
        return skip("daily loss limit reached")

    prem = p["entry_premium"]
    ostop = option_stop_price(prem, p["delta"], eu, su)
    risk_per = round((prem - ostop) * 100, 2)
    out.update(option_stop=ostop, risk_per_contract=risk_per)
    if risk_per <= 0:
        return skip("non-positive risk per contract; check inputs")

    budget = min(eff["max_risk"], room)
    n = math.floor(budget / risk_per + 1e-9)
    acct_cap = cfg["max_account_fraction_per_trade"] * p["account_value"]
    n_acct = math.floor(acct_cap / (prem * 100) + 1e-9)
    n = min(n, n_acct)
    out["account_cap"] = round(acct_cap, 2)
    if n < 1:
        why = "stop does not fit the per-trade cap" if n_acct >= 1 else "30% account cap"
        return skip(f"0 contracts: {why}")

    return {**out, "contracts": n, "trade": True,
            "total_risk": round(n * risk_per, 2),
            "total_premium": round(n * prem * 100, 2),
            "reason": "ok"}


# ------------------------------------------------------------ exit engine
def next_stop(entry: float, peak_mark: float, current_stop: float, cfg: dict = CFG) -> dict:
    """Return the stop the ladder calls for. Stops only move up."""
    gain = peak_mark / entry - 1
    target = current_stop
    rule = "hold"
    for rung in cfg["ladder"]:
        if gain >= rung["peak_gain"] - 1e-9:
            lvl = round(entry * (1 + rung["lock_gain"]), 2)
            if lvl > target:
                target, rule = lvl, f"peak +{rung['peak_gain']:.0%} -> lock +{rung['lock_gain']:.0%}"
    tr = cfg["trail"]
    if gain >= tr["from_peak_gain"] - 1e-9:
        lvl = _cents_down(tr["fraction_of_peak"] * peak_mark)
        if lvl > target:
            target, rule = lvl, f"trail {tr['fraction_of_peak']:.0%} of peak {peak_mark:.2f}"
    raise_by = round(target - current_stop, 2)
    in_trail = gain >= tr["from_peak_gain"] - 1e-9
    # In trailing mode only move in steps of >= min_step (avoids churn on the one close order).
    if in_trail and 0 < raise_by < tr["min_step"] and rule.startswith("trail"):
        return {"move": False, "stop": current_stop, "peak_gain": round(gain, 4),
                "rule": f"trail step {raise_by:.2f} < {tr['min_step']:.2f}"}
    return {"move": target > current_stop, "stop": target if target > current_stop else current_stop,
            "peak_gain": round(gain, 4), "rule": rule}


def scale_out(contracts: int, entry: float, mark: float, already_scaled: bool, cfg: dict = CFG) -> int:
    """Contracts to sell now for the +50% half-off rule (0 if none)."""
    so = cfg["scale_out"]
    if already_scaled or contracts < so["min_contracts"]:
        return 0
    if mark / entry - 1 >= so["at_gain"] - 1e-9:
        return max(1, math.floor(contracts * so["fraction"]))
    return 0


# --------------------------------------------------------------------- CLI
def _main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd, arg = argv[1], json.loads(argv[2])
    if cmd == "score":
        res = score(arg)
    elif cmd == "size":
        res = size(arg)
    elif cmd == "stop":
        res = next_stop(arg["entry"], arg["peak_mark"], arg["current_stop"])
    elif cmd == "limit":
        res = {"daily_loss_limit": daily_loss_limit(arg.get("realized_pnl", 0.0))}
    elif cmd == "scale":
        res = {"sell": scale_out(arg["contracts"], arg["entry"], arg["mark"], arg.get("already_scaled", False))}
    else:
        print(f"unknown command {cmd}")
        return 2
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
