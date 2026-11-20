"""Replay the 6 live 0DTE trades (11-10..11-12) with delta-matched 1DTE and 2DTE SPY contracts.

Same signal, same underlying structural stop, same score/tier, same engine sizing and
stop ladder; only the expiry changes. Robinhood keeps only 5-minute bars for expired
contracts, so the ladder runs on 5-minute OHLC:
  * stop is checked against the bar low first (fill = min(stop, bar open) on a gap),
  * then the peak mark updates from the bar CLOSE (conservative; v4 uses 1-min closes),
  * the +50% scale-out uses the bar close,
  * a position still open at the end of the data (09:45 PT) is marked at the last close.
Early discretionary exits (2 lower 1m highs, 5m close < 9-EMA, give-back) are NOT
modelled for any expiry, so the 0DTE row is a calibration check against the real P&L.
Entry price for 1/2DTE = same fraction of the entry bar's open->close move as the real fill.
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "trading" / "spy0dte"))
import engine
from bs import iv, delta, trading_years
import data_1110 as d10, data_1111 as d11, data_1112 as d12

def bars(s): return [tuple(float(x) for x in b.split()) for b in s.split("|")]

FACT = lambda names: {f: f in names for f in engine.FACTORS} if hasattr(engine, "FACTORS") else None
# trade: id, day, series dict, bar index of entry, real fill, entry utc, spot, underlying stop, kind,
#        factors, real P&L, account value
TRADES = [
 ("11-10 #1 754C", "11-10", d10.T1, 0, 0.62, "2026-11-10T14:58:00Z", 749.77, 748.20, "call",
  ["trend","structure","key_level","breadth","volume","time"], 24, 489, 0.21),
 ("11-10 #2 744P", "11-10", d10.T2, 0, 0.48, "2026-11-10T15:43:00Z", 748.63, 749.80, "put",
  ["trend","structure","breadth","volume","time"], 27, 489, 0.18),
 ("11-11 #1 760C", "11-11", d11.A, 0, 0.25, "2026-11-11T15:45:03Z", 757.46, 756.85, "call",
  ["trend","structure","breadth","time"], 14, 540, 0.18),
 ("11-11 #2 761C", "11-11", d11.B, 0, 0.30, "2026-11-11T16:31:54Z", 759.22, 758.80, "call",
  ["trend","structure","key_level","breadth","time"], -27, 540, 0.214),
 ("11-11 #3 761C", "11-11", d11.B, 3, 0.30, "2026-11-11T16:45:06Z", 759.40, 758.90, "call",
  ["trend","structure","key_level","breadth","time"], 50, 540, 0.218),
 ("11-12 #1 764C", "11-12", d12.A, 0, 0.49, "2026-11-12T16:08:05Z", 760.87, 759.93, "call",
  ["trend","structure","key_level","breadth","time"], 20, 876, 0.224),
]

def run_one(b, i0, entry, d, eu, su, factors, acct, realized, losses, kind, entry_bar_stop=False):
    p = {"factors": {f: f in factors for f in ["trend","structure","key_level","breadth","volume","time"]},
         "entry_premium": entry, "delta": abs(d), "entry_underlying": eu, "stop_underlying": su,
         "account_value": acct, "realized_pnl": realized, "consecutive_losses": losses, "side": kind}
    sz = engine.size(p)
    n = sz["contracts"]
    if n == 0:
        return {"contracts": 0, "pnl": 0.0, "why": sz["reason"], "risk_per": sz.get("risk_per_contract")}
    stop = sz["option_stop"]; peak = entry; held = n; pnl = 0.0; scaled = False; exit_note = None
    # The live 11-11 #2 trade was stopped out inside its entry bar (journal: 08:31 fill, 08:34 stop).
    # 5-minute bars can't see that ordering, so for that trade only the entry bar's low also counts.
    if entry_bar_stop and b[i0][2] <= stop:
        return {"contracts": n, "entry": round(entry, 2), "delta": round(abs(d), 2), "risk_per": sz["risk_per_contract"],
                "premium": round(n * entry * 100), "pnl": round((stop - entry) * 100 * n, 2), "peak": entry,
                "exit": f"stop {stop:.2f} hit inside the entry bar (low {b[i0][2]:.2f})"}
    for O, H, L, C in b[i0 + 1:]:
        if L <= stop:
            px = min(stop, O); pnl += (px - entry) * 100 * held; held = 0
            exit_note = f"stop {stop:.2f} hit, fill {px:.2f}"; break
        peak = max(peak, C)
        k = engine.scale_out(held, entry, C, scaled)
        if k:
            pnl += (C - entry) * 100 * k; held -= k; scaled = True
        stop = engine.next_stop(entry, peak, stop)["stop"]
    if held:
        C = b[-1][3]; pnl += (C - entry) * 100 * held; exit_note = f"open at 09:45 PT, marked {C:.2f}"
    return {"contracts": n, "entry": round(entry, 2), "delta": round(abs(d), 2), "risk_per": sz["risk_per_contract"],
            "premium": round(n * entry * 100), "pnl": round(pnl, 2), "peak": round(peak, 2), "exit": exit_note}

def main():
    rows = []; tracks = {k: {} for k in ("0DTE", "1DTE", "2DTE")}
    for tid, day, series, i0, fill, ts, eu, su, kind, factors, real, acct, d_live in TRADES:
        names = list(series)
        o0, c0 = bars(series[names[0]])[i0][0], bars(series[names[0]])[i0][3]
        frac = 0.0 if c0 == o0 else min(max((fill - o0) / (c0 - o0), 0), 1)
        for n_after, name in enumerate(names):
            tag = name.split()[0]; b = bars(series[name])
            entry = fill if n_after == 0 else round(b[i0][0] + frac * (b[i0][3] - b[i0][0]), 2)
            T = trading_years(ts, n_after if day != "11-12" or n_after < 2 else 2)
            v = iv(entry, eu, float(name.split()[1][:-1]), T, kind); d = delta(eu, float(name.split()[1][:-1]), T, v, kind)
            if n_after == 0: d = d_live
            st = tracks[tag].setdefault(day, {"realized": 0.0, "losses": 0})
            r = run_one(b, i0, entry, d, eu, su, factors, acct, st["realized"], st["losses"], kind, entry_bar_stop=(tid == "11-11 #2 761C"))
            st["realized"] += r["pnl"]
            st["losses"] = st["losses"] + 1 if r["pnl"] < 0 else (0 if r["pnl"] > 0 else st["losses"])
            rows.append({"trade": tid, "contract": name, "iv": round(v, 3), **r, "real_0dte_pnl": real if n_after == 0 else None})
    return rows

if __name__ == "__main__":
    rows = main()
    for r in rows: print(json.dumps(r))
    tot = {}
    for r in rows:
        k = r["contract"].split()[0]; tot.setdefault(k, [0, 0, 0]); tot[k][0] += r["pnl"]; tot[k][1] += r["contracts"] > 0; tot[k][2] += r.get("premium", 0)
    print("TOTALS (sim pnl, trades taken, premium deployed):", {k: [round(v[0], 2), v[1], v[2]] for k, v in tot.items()})
