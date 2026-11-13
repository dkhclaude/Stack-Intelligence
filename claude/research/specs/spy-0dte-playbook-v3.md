---
playbook: SPY 0DTE Momentum Playbook
version: 3
effective: 2026-11-12
owner: Kevin
status: active
---

# SPY 0DTE Momentum Playbook (v3)

This is the source of truth. The skill at `.claude/skills/spy-0dte-playbook/SKILL.md`
always loads the newest `spy-0dte-playbook-v*.md` in this folder. If they disagree,
this doc wins. The daily review may change at most one rule per day by writing
`v<N+1>` (never edit an older version in place) and adding a changelog entry.

Machine-readable numbers live in `claude/trading/spy0dte/config.json`. Keep it in sync
with this doc when a version bump changes a number.

## 1. Account and instruments

- Robinhood **agentic account only** (nickname "MCP", cash account). Never touch any other account.
- **Long single-leg calls and puts only.** No spreads, no short options, no equity, no margin.
- One trader only: no parallel agents placing orders.

## 2. Confluence score (Kevin's framework)

1 point per factor, scored at the trigger bar:

| # | Factor | Point if... |
|---|--------|-------------|
| 1 | Trend | Price on the trade's side of VWAP **and** 5-minute higher highs (calls) / lower lows (puts) |
| 2 | Structure | Clean flag, tight range or VWAP reclaim **with a clear invalidation level** |
| 3 | Key level | Break of session high/low, prior-day high/low, or a $5 round number |
| 4 | Breadth | QQQ **and** SMH confirm the direction (for a single name: its sector ETF) |
| 5 | Volume | Trigger bar volume >= 1.5x the average of the prior 10 bars |
| 6 | Time | Entry between 06:45 and 09:00 PT |

## 3. Tiers (max dollar risk per trade)

| Score | Tier | Max risk |
|-------|------|----------|
| 0-2 | none | no trade |
| 3 | T1 | $10 |
| 4 | T2 | $15 |
| 5 | T3 | $25 |
| 6 | T4 | $35 |

**Only Kevin changes the dollar amounts.** The daily review may not raise or lower them.

## 4. Account-level limits

- **Daily loss limit** = $40 + 50% of the day's realized profit, capped at **$75**.
  Stop trading for the day once realized P&L <= -limit, or when the next trade's max
  risk would push the day past it.
- **After 2 straight losses**, the next trade is capped at T1 regardless of score.
- **Never risk more than 30% of the account** (portfolio value) on one trade.
- Log each entry's score, factors and tier, and include them in the fill message.

## 5. Morning read (06:30-06:45 PT)

1. Quote SPY, QQQ, SMH, NVDA, AMD, AVGO, TSLA, MU, IWM. Check news on any big gapper (|gap| >= 2%).
2. Wait 10-15 minutes. Do not pre-commit to a direction.
3. Trend day = SPY above VWAP with 5-minute higher highs (or the mirror for a down day).
   On a trend day, trade with the trend only.

## 6. Entries

- **Bull flag (calls):** SPY above VWAP, coiling in a range under $1.00 for 15-25 minutes
  near the session high. Buy a 0DTE call 3-4 strikes OTM (delta ~0.18-0.25, premium ~$0.35-0.45).
  Mirror for a bear flag with puts.
- **Gap and go:** in the first hour, SPY reclaims the prior-day high and holds above VWAP.
- **Single-name puts (e.g. NVDA):** only when the name is below its VWAP **and** its sector is
  red on the 5-minute chart. Never short a laggard while its sector rips. Skip if IV > 150%
  after a news gap.

## 7. Stops and sizing

- Stop = a **structural** level (below the flag range, or below VWAP).
- **Place the stop beyond the base the breakout came from, not at the breakout level.** For a call, the
  stop goes below the lowest low of the consolidation/flag (or the most recent confirmed higher low) that
  preceded the break, minus a $0.05 buffer; mirror for puts. A stop just under the broken level is not
  structural - retests of the breakout level are normal. If the wider stop does not fit the tier cap, size
  down or skip; never tighten the stop to make the size fit.
  *2026-11-11: 761C x3 entered on the 758.85 break with the stop at SPY 758.80; SPY retested to 758.62 -
  the exact low of the base - stopping the trade out for -$27, then ran to 761.02. The re-entry used a stop
  below the 758.965 higher low, held, and made +$50.*
- Convert to an option price: `option_stop = entry_premium - delta * |entry_underlying - stop_underlying|`
  (floor at $0.01).
- Risk per contract = `(entry_premium - option_stop) * 100`.
- Contracts = floor(tier cap / risk per contract). **If that is 0, skip the trade.**
- Also respect the 30%-of-account rule (total premium at risk = entry premium x 100 x contracts).
- Never use a tight fixed-% stop on a low-delta contract.
  *2026-11-09: a 22% stop on a 0.09-delta contract was stopped out by a 45-cent wiggle.*

## 8. Exit engine (stops only move up)

- With 2+ contracts (T3/T4): sell half at +50%, trail the rest.
- Stop ladder on the option mark (gain = mark / entry - 1, using the peak mark):
  - peak +30% -> stop to breakeven
  - peak +50% -> stop locks +25%
  - peak +80% -> stop locks +40%
  - peak +100% or more -> trail at 75% of peak mark, raised in steps of >= $0.03
- Take profit early on any of: 2 lower 1-minute highs after a session high; a 5-minute close
  below the 9-EMA (above, for puts); the option giving back 25% of its peak gain within 3 minutes.
- Robinhood allows one close order per contract: **cancel, confirm the cancel, then place the new stop.**
- **Discretionary exits (early profit-take, time exit): after the cancel of the resting stop is confirmed, close
  immediately with a market order (or a limit at least $0.05 through the bid).** Never re-quote a passive limit
  at the last-seen bid while the position has no stop.
  *2026-11-10: on the 744P early exit, a 0.89 limit at the stale bid missed while the bid fell to 0.74 within
  ~10 s; sold at market 0.75, $0.04 below the 0.79 trailing stop that had just been cancelled.*
- Out by 10:30 PT unless the trend is still expanding. **Flat by 12:30 PT.**

## 9. Monitoring

- Check every 1 minute near a breakout or with an open position near a stop/target, every 2 minutes otherwise.
  Use `send_later` to wake the session between turns.
- Message Kevin on every fill, exit or stop move via NTFY. Stay silent otherwise.

## 10. Daily improvement

Scheduled task "SPY playbook daily review" (weekdays 13:23 PT) grades each trade, logs lessons in
`claude/research/journal/spy-0dte/lessons.md`, and makes **at most one** evidence-backed rule change
per day as a new version of this doc. It never changes tier dollar amounts.

## Changelog

- **v3 (2026-11-12):** Section 7 - initial stops go below the lowest low of the base/flag (or the latest
  higher low) that preceded the breakout, with a $0.05 buffer, never just under the breakout level; size down
  or skip if it does not fit. Evidence: 2026-11-11 761C x3 (stop 758.80 under the 758.85 break; base low
  758.62 tagged to the cent, stopped -$27, SPY then +$2.40 higher) vs. the 761C x2 re-entry (stop under the
  758.965 higher low, held, +$50). No dollar amounts or limits changed.

- **v2 (2026-11-11):** Section 8 — discretionary exits close with a market (or marketable) order right after the stop cancel confirms. Evidence: 2026-11-10 trade 2 (744P) — passive limit at stale bid missed in a fast bounce, exit $0.14 below the intended price and $0.04 below the cancelled trailing stop, position briefly unprotected. No dollar amounts or limits changed.

- **v1 (2026-11-09):** Initial version from Kevin's playbook. Includes the 2026-11-09 lesson on fixed-% stops on low-delta contracts.
