# Strategy Book

Read by the "Daily Trade Handoff → Levee" task to tag each trade with its strategy. A trade that matches
no entry here is tagged UNTAGGED. The full live rules live in the newest
`claude/research/specs/spy-0dte-playbook-v*.md` (v7 as of 2026-11-18). If the two disagree, the spec wins.

Last updated: 2026-11-18 (from the playbook spec; pending Kevin's confirmation of other strategies).

---

## 1. SPY/QQQ 0DTE Momentum: Bull/Bear Flag

- **Status:** LIVE (Robinhood agentic account ••0560, placed by Claude)
- **Instruments:** SPY and QQQ 0DTE options, long single-leg calls/puts only, delta ~0.18-0.30
- **Timeframe:** 1-minute and 5-minute bars, 06:45-10:15 PT entries
- **Setup / entry trigger:** price on the trade's side of VWAP, coiling in a tight flag or range near the
  session high (calls) or low (puts), then a 1-minute close through the flag or key level. Limit order at the ask;
  no chase more than $0.40 past the trigger close.
- **Indicators:** VWAP, 5-min 9-EMA, 1-min volume vs prior-10-bar average, QQQ/SPY + SMH breadth
- **Confluence score (0-6):** trend, structure, key level, breadth, volume (≥1.5x), time (06:45-09:00)
- **Position sizing:** risk tier by score: 3 = $10, 4 = $15, 5 = $25, 6 = $35. Contracts = tier ÷ (delta ×
  structural stop distance × 100). Max 30% of the account in open premium; daily loss limit $40 + 50% of the
  day's profit (max $75); T1 only after 2 straight losses.
- **Stop:** structural, below the flag low or higher low (above the lower high for puts) + $0.05, converted to
  an option stop_market price with delta. v7: exit at once if a 1-minute underlying close goes through the
  structural level.
- **Exit:** ladder: +30% → breakeven, +50% → lock +25%, +80% → lock +40%, ≥+100% → trail 75% of the peak.
  Early exit on 2 lower 1-min highs (calls), a 5-min close through the 9-EMA, or a 25% give-back of the peak gain within 3 min.
  Out by 10:30 PT, flat by 12:30 PT, never held overnight.

## 2. SPY/QQQ 0DTE Momentum: Gap and Go

- **Status:** LIVE (same account and rules as #1)
- **Setup / entry trigger:** in the first hour, SPY or QQQ reclaims the prior-day high (low for puts) and holds
  above (below) VWAP.
- **Everything else:** same timeframe, indicators, sizing, stop and exit as #1.

## 3. Single-name 0DTE/short-dated puts (e.g. NVDA)

- **Status:** IDEA in the playbook text. Not traded live since v5 limited live trading to SPY and QQQ.
- **Setup:** the name is below its VWAP **and** its sector is red on the 5-minute chart; skip if IV > 150% after a
  news gap. Never short a laggard while its sector rips.

## 4. Phase A: 1DTE shadow twin

- **Status:** PAPER only (never ordered). It's a delta-matched 1DTE contract logged for every live 0DTE fill.
  It's reported in the handoff as a paper line, not as a trade.
