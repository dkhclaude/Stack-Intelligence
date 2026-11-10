# SPY 0DTE playbook - lessons log

Appended by the daily review (weekdays 13:23 PT). Newest at the bottom.

## 2026-11-09 (seeded from playbook v1)

- A 22% fixed stop on a 0.09-delta contract was stopped out by a 45-cent SPY wiggle.
  Lesson: stops come from structure, converted to option price with delta, and size adjusts to fit the tier cap.

## 2026-11-10 — 2 trades, 2 wins, +$51 (fees ~$0.16) — playbook v1

Robinhood cross-check: all four fills match the journal (754C 0.62→0.86, 744P 0.48→0.75). Kevin separately sold XBI and NTRA equity in this account (not agent-initiated).

| # | Contract | Score / tier | Factors | Entry → exit | P&L | Process grade | Outcome |
|---|----------|--------------|---------|--------------|-----|---------------|---------|
| 1 | SPY 754C | 6/6 T4 ($35) | trend, structure, key_level, breadth, volume, time | 0.62 → 0.86 | +$24 | **B+** | Good |
| 2 | SPY 744P | 5/6 T3 ($25) | trend, structure, breadth, volume, time | 0.48 → 0.75 | +$27 | **B-** | Good |

**Trade 1 (754C).** Entry was textbook: 06:56 break of the 749.60 session high on 1.4x volume with QQQ/SMH at new highs, VWAP reclaim, structural stop below VWAP sized by the engine ($32 vs $35 cap). Minor: premium 0.62 was above the 0.35–0.45 guideline (delta 0.21 was in range). Ladder was followed exactly (+85% peak → stop 0.87). The stop_market was hit by a one-minute SPY wick to 750.63 and the option was back at 1.05 a minute later — the rule, not the execution, cut the winner. One sample; logged, not acted on yet.
*Lesson:* a tight option-price lock on a 0.2–0.3 delta 0DTE is vulnerable to 1-minute noise. Watch for a second instance before changing the ladder.

**Trade 2 (744P).** Entry valid but generous: volume factor was barely met (42,970 vs 42,323 needed), structure credited for a VWAP loss after an opening-range chop. Correctly skipped the 745P whose stop didn't fit and took the 744P. Ladder followed (0.27 → 0.60 → 0.79 trail). The early-exit signal (2 higher 1m lows after the 746.00 LOD) was valid, but execution was poor: cancelled the 0.79 stop, then sent a 0.89 limit at a stale bid; bid fell to 0.74 within ~10 s; sold at market 0.75 — $0.04 below the cancelled stop and ~25 s unprotected.
*Lesson:* after the cancel confirms, exit with a market/marketable order. → **Rule change v2.**

**Missed / skipped.**
- 09:37 SPY broke the 745.87 LOD on 70k volume with breadth confirming; the send_later check fired ~6 min late (checks ran 2–6 min late from ~09:35), so the entry was missed and correctly not chased.
- Many stand-asides in 08:00–10:15 chop were correct (SPY repeatedly held its LOD while QQQ/SMH made new lows).
- Yesterday (11-09) the 10:20 self-imposed cutoff was followed by the real breakout to 755.42 — the cutoff was not a playbook rule; dropped today.

**Rule change:** v2 — discretionary exits use a market/marketable order immediately after the stop cancel confirms (evidence: trade 2). No dollar amounts, limits or tiers changed.
