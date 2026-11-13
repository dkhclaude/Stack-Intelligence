"""Black-Scholes helpers for the 0DTE vs 1-2DTE replay (r=0, no dividends)."""
import math
from datetime import datetime, timezone

def _N(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def price(S, K, T, vol, kind):
    if T <= 0: return max(0.0, (S - K) if kind == "call" else (K - S))
    d1 = (math.log(S / K) + 0.5 * vol * vol * T) / (vol * math.sqrt(T)); d2 = d1 - vol * math.sqrt(T)
    return S * _N(d1) - K * _N(d2) if kind == "call" else K * _N(-d2) - S * _N(-d1)

def delta(S, K, T, vol, kind):
    d1 = (math.log(S / K) + 0.5 * vol * vol * T) / (vol * math.sqrt(T))
    return _N(d1) if kind == "call" else _N(d1) - 1

def iv(p, S, K, T, kind):
    lo, hi = 0.01, 3.0
    for _ in range(100):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if price(S, K, T, m, kind) < p else (lo, m)
    return (lo + hi) / 2

def years(now_utc: str, expiry_date: str) -> float:
    """Calendar time from now to 21:00Z (16:00 ET close) on expiry_date, in years."""
    t0 = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(expiry_date + "T21:00:00+00:00")
    return max((t1 - t0).total_seconds(), 60) / (365 * 24 * 3600)

# Trading-time clock: 0DTE prices move like ~1 trading day of variance, so calendar time
# badly misprices 0DTE vs 1-2DTE. Use regular-session hours left + 1 trading day per extra session.
SESSION_H = 6.5
def trading_years(now_utc: str, sessions_after_today: int) -> float:
    t0 = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
    close = t0.replace(hour=21, minute=0, second=0)
    h_left = max((close - t0).total_seconds() / 3600, 1 / 60)
    return (h_left / SESSION_H + sessions_after_today) / 252
