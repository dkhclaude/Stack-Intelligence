"""Sensitivity: run the 1DTE legs with the ladder in R (multiples of initial risk) instead of % of premium.
Rungs are the live 0DTE % rungs translated at the 0DTE sample's median premium/risk (~2.3x):
  +30% -> 0.7R BE; +50% -> 1.2R lock 0.6R; +80% -> 1.9R lock 0.95R; >=+100% (2.3R) -> keep 60% of peak gain.
Indicative only: 3 comparable trades."""
import replay, engine
R_LADDER = [(0.7, 0.0), (1.2, 0.6), (1.9, 0.95)]
def r_stop(entry, risk, peak, cur):
    g = (peak - entry) / risk; tgt = cur
    for at, lock in R_LADDER:
        if g >= at: tgt = max(tgt, round(entry + lock * risk, 2))
    if g >= 2.3: tgt = max(tgt, round(entry + 0.6 * (peak - entry), 2))
    return tgt
orig = engine.next_stop
def patched(entry, peak, cur, cfg=None):
    risk = patched.risk
    return {"stop": r_stop(entry, risk, peak, cur)}
engine.next_stop = patched
_run = replay.run_one
def run_one(b, i0, entry, d, eu, su, *a, **k):
    patched.risk = abs(d) * abs(eu - su)
    return _run(b, i0, entry, d, eu, su, *a, **k)
replay.run_one = run_one
for r in replay.main():
    if r["contract"].startswith(("1DTE", "0DTE")) and r["contracts"]:
        print(f"{r['trade']:15} {r['contract']:17} n={r['contracts']} pnl={r['pnl']:>6} | {r['exit']}")
