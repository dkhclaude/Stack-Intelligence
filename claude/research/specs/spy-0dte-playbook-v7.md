---
playbook: SPY 0DTE Momentum Playbook
version: 7
effective: 2026-11-18
owner: Kevin
status: active
---

# SPY 0DTE Momentum Playbook (v7)

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
- **No overnight holds.** Every position is closed the same day (Section 8). Overnight risk budget: **$0** (v6).
- **Tradable underlyings: SPY and QQQ 0DTE options** (both list an expiration every trading day).
  Not SPX (a 0DTE SPX contract is ~10x SPY; a structural stop risks $100-200+ per contract, above every
  tier, so it always sizes to 0). Not leveraged/inverse ETFs (SSO, UPRO, SPXL, SH, SDS, QLD, TQQQ): no
  daily expirations (SDS lists monthlies only; TQQQ skips Tue/Thu), wider spreads, and the same index
  exposure SPY/QQQ already give. Kevin decided this on 2026-11-13.

## 2. Confluence score (Kevin's framework)

1 point per factor, scored at the trigger bar:

| # | Factor | Point if... |
|---|--------|-------------|
| 1 | Trend | Price on the trade's side of VWAP **and** 5-minute higher highs (calls) / lower lows (puts) |
| 2 | Structure | Clean flag, tight range or VWAP reclaim **with a clear invalidation level** |
| 3 | Key level | Break of the traded underlying's session high/low, prior-day high/low, or a $5 round number |
| 4 | Breadth | SPY trade: QQQ **and** SMH confirm. QQQ trade: SPY **and** SMH confirm (for a single name: its sector ETF) |
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
- **Never risk more than 30% of the account** (portfolio value) on one trade, and the **total premium of all
  open positions** stays within 30% of the account.
- **Up to 2 open positions at once, on different underlyings** (one SPY, one QQQ). Each trade gets its own tier
  from its own score. The daily loss limit is shared: a new trade's max risk plus the stop risk of the open
  position must fit inside the remaining daily room (`engine.py size` with `open_risk` / `open_premium`).
  The 2-loss streak cap counts losses across both underlyings. SPY and QQQ move together, so two same-direction
  positions are close to one doubled bet; the shared limits keep the combined risk inside the daily limit.
- Log each entry's score, factors and tier, and include them in the fill message.

## 5. Morning read (06:30-06:45 PT)

1. Quote SPY, QQQ, SMH, NVDA, AMD, AVGO, TSLA, MU, IWM. Note prior-day high/low and $5 rounds for both SPY and QQQ. Check news on any big gapper (|gap| >= 2%).
2. Wait 10-15 minutes. Do not pre-commit to a direction.
3. Trend day = SPY above VWAP with 5-minute higher highs (or the mirror for a down day).
   On a trend day, trade with the trend only.

## 6. Entries

- **Bull flag (calls):** SPY or QQQ above its VWAP, coiling in a range under $1.00 for 15-25 minutes
  near the session high. Buy a 0DTE call 3-4 strikes OTM (delta ~0.18-0.25, premium ~$0.35-0.45).
  Mirror for a bear flag with puts.
- **Gap and go:** in the first hour, SPY or QQQ reclaims the prior-day high and holds above VWAP.
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
- **Structural-close exit (v7): the structural level is the real stop; the option stop is only its estimate.**
  On every check, if a completed 1-minute close of the traded underlying is beyond `stop_underlying` (below it for
  a call, above it for a put), exit at once even if the option stop has not triggered: cancel the resting stop,
  confirm the cancel, then close with a market order or a limit at least $0.05 through the bid (Section 8).
  Wicks that close back inside do not count. The resting option stop stays in place as the backstop between checks.
  *2026-11-17: 739C bought 0.66 with the stop at SPY 733.69 (option stop 0.51 via delta 0.21). SPY closed 733.61
  and 733.41, below the level, but delta fell to 0.19 and the option held 0.63, so the option stop never fired.
  Exiting on the underlying close sold at 0.64 (-$2) instead of riding a broken setup toward the $15 stop.*
- Never use a tight fixed-% stop on a low-delta contract.
  *2026-11-09: a 22% stop on a 0.09-delta contract was stopped out by a 45-cent wiggle.*

## 8. Exit engine (stops only move up)

- With 2+ contracts (T3/T4): sell half at +50%, trail the rest.
- Stop ladder on the option mark (gain = mark / entry - 1, using the peak mark):
  - **Peak mark = the highest of (a) the current mark and (b) the highest 1-minute option CLOSE since the
    previous check** (`get_option_historicals`, interval minute, from the last check time). Checks fire 1-4 minutes
    late, so the live quote alone understates the peak. Use closes, not bar highs, to avoid single-print spikes.
    *2026-11-12: the 764C closed at 1.02 (+108%) at 08:11 between checks; the 08:12 check saw 0.955 and set the
    +40% lock (0.69) instead of the 75% trail (0.76). The option traded through 0.76 at 08:13; the exit came at 0.69
    (+$20 instead of about +$27).*
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

- **Check every 1 minute from 06:45 to 09:30 PT, whatever the tape** (Kevin, 2026-11-17: he is buying more
  Claude usage so signals are not missed between checks). From 09:30 to 10:15, check every 1 minute near a
  breakout or with an open position, every 2 minutes otherwise. With an open position, always every 1 minute.
  Use `send_later` to wake the session between turns.
  *2026-11-17: valid triggers at 08:45, 08:58 and 09:17 fired between 2-3 minute checks and were missed or
  became chases (the 09:17 call ran $0.43 past its trigger close before the next check).*
- Message Kevin on every fill, exit or stop move via NTFY. Stay silent otherwise.
- With two open positions, manage both on every check (each has its own stop order, peak mark and ladder) and
  carry both in the `send_later` state.

## 10. Daily improvement

Scheduled task "SPY playbook daily review" (weekdays 13:23 PT) grades each trade, logs lessons in
`claude/research/journal/spy-0dte/lessons.md`, and makes **at most one** evidence-backed rule change
per day as a new version of this doc. It never changes tier dollar amounts.

## 11. Phase A: 1DTE shadow log (v6)

Kevin approved Phase A on 2026-11-15. Live trading is unchanged: **0DTE only**. The full plan, including
Phase B, is in `drafts/spy-playbook-v6-1-2dte-DRAFT.md`. Evidence: `claude/research/replay/README.md`.

1. **On every live 0DTE fill, pick a twin** right after the stop is placed and the NTFY is sent.
   - Same underlying and side, **next-session expiry**.
   - Strike: the one whose **live quote delta** is closest to the live contract's delta.
   - Twin entry = that contract's **ask** at the same check.
   - Log `{"event":"shadow_entry","of":<live order_id>,"dte":1,"contract":...,"id":...,"entry":ask,
     "delta":...}`.
2. **No orders, ever, for the twin.** Shadow work never delays a live action. On each check, manage
   the live position first.
3. **After the live position closes** (or by the end-of-day summary at the latest):
   - Pull the twin's 1-minute bars from entry to the live exit rules with `get_option_historicals`,
     while they still exist. They become gap-fill after expiry.
   - Run `python3 claude/trading/spy0dte/shadow.py '<json>'` with the live trade's factors,
     structural stop, account state, `exit_by_utc` = 10:30 PT, and the bars.
   - Log `{"event":"shadow_result","of":...,"fits":...,"contracts":...,"risk_per_contract":...,
     "pnl":...,"exit":...}`.
4. **Overnight observation:** the next morning, record the twin's price at the open as
   `{"event":"shadow_overnight","of":...,"next_open":...,"obs":...}`. This is evidence only; there are
   no overnight holds.
5. **The daily review grades each pair,** comparing:
   - live P&L vs twin P&L,
   - whether the twin fit its tier,
   - stop-outs on 1-minute wicks avoided,
   - premium used.
6. **Go-live test for Phase B (the review only reports it; it never activates it):**
   - at least 20 pairs;
   - twin P&L at least as good as live on the same signals, with fewer wick stop-outs;
   - the twin fit its tier on at least 70% of signals;
   - Kevin's written approval.

**Overnight risk budget: $0.** Kevin delegated this number (2026-11-15). Reasons:
- There is no evidence yet about overnight holds.
- A stop doesn't protect against a gap, so the real risk is the whole premium. At the current tier
  sizes that means far out-of-the-money contracts only.
- The 2DTE replay lost money.

Revisit after 20 shadow pairs that include overnight observations. Any budget proposed then would be a
separate cap, never larger than T1 ($10) of total premium at first.

## 12. Low-delta paper test (Kevin, 2026-11-22; paper only)

Purpose: find out whether delta 0.12-0.15 contracts would make money on the setups that are skipped only because
the structural stop does not fit the tier at delta 0.18-0.25. **Live trading stays at delta 0.18-0.25 (Section 6).
Never place an order for a low-delta paper entry.**

1. **When:** every time a setup scores 3+ and passes every rule except size (engine.size gives 0 contracts at delta
   0.18-0.25 because the structural stop is too wide). Not for chases, failed breaks, score < 3 or no-base flushes.
2. **Contract:** same underlying, side and 0DTE expiry; the strike whose live quote delta is closest to 0.13
   (allowed 0.12-0.15) with premium >= $0.30. Entry = its ask at the trigger check.
3. **Sizing:** engine.size with the same factors, tier, structural stop and account state. Record contracts, risk per
   contract and whether it fits. If it still does not fit at 0.12, log it as "no fit".
4. **Management:** the normal ladder and stops, plus a time stop: exit at the 1-minute close 10 minutes after entry
   unless a close has reached +30%. Simulate with `shadow.py` (`time_stop: {"minutes": 10, "min_gain": 0.30}`,
   `exit_by_utc` = 10:30 PT) on the contract's 1-minute bars after the live session's last position is managed.
5. **Journal:** `{"event":"lowdelta_entry", ...}` at the check, `{"event":"lowdelta_result", ...}` by end of day. Live
   management and the 1DTE shadow always come first.
6. **Decision:** after about 20 paper entries, the daily review reports win rate, P&L per entry, how many fit, and
   time-stop vs price-stop exits. Kevin decides whether to allow low delta live; the review cannot.

## Changelog

- **v7 addendum (2026-11-22, Kevin):** Section 12, a paper-only low-delta (0.12-0.15) test on size-0 skips with a 10-minute / +30% time stop. `shadow.py` gains `time_stop`. No live rule, dollar amount or limit changed.

- **v7 (2026-11-18):** Section 7 - structural-close exit: when a completed 1-minute close of the underlying is
  beyond the structural stop level, exit at once even if the delta-converted option stop has not triggered (the
  resting option stop remains the between-checks backstop; wicks that close back inside do not count). Evidence:
  2026-11-17 739C - SPY closed 733.61 and 733.41 below the 733.69 structural stop while the option held 0.63 vs its
  0.51 stop (delta drift 0.21 -> 0.19); the exit on the underlying close was -$2 vs up to -$15. Codifies what was done
  by judgment. No dollar amounts, limits or tiers changed. `config.json`: `playbook_version` 7, `structural_close_exit` true.
  - Section 9 (Kevin, 2026-11-17): 1-minute checks every minute 06:45-09:30 PT; Kevin is adding Claude usage to
    pay for it. Evidence: three valid triggers missed between 2-3 minute checks on 11-17.

- **v6 (2026-11-16, Kevin approved Phase A 2026-11-15):**
  - Added Section 11, a paper shadow log of a delta-matched 1DTE twin for every live 0DTE fill:
    no orders, graded in the daily review, gated go-live test for Phase B.
  - Overnight risk budget set to $0 (Kevin delegated the number). No overnight holds.
  - `config.json` gains `live_expiries_dte: [0]`, `shadow`, `overnight_risk_budget: 0`.
  - New helper `shadow.py` with tests.
  - Tier dollar amounts, the daily loss limit and the 30% cap are unchanged.

- **v5 (2026-11-13, Kevin):** Add QQQ 0DTE options alongside SPY; allow up to 2 open positions on different
  underlyings with a shared daily loss limit (open stop risk counts against the room), a shared 2-loss streak cap
  and a 30% cap on total open premium; breadth for QQQ trades = SPY + SMH. SPX and leveraged/inverse ETFs
  excluded (contract size / no daily expirations). Tier dollar amounts unchanged.

- **v4 (2026-11-13):** Section 8 - the ladder's peak mark includes the highest 1-minute option close since the
  previous check (from option historicals), not just the live quote. Evidence: 2026-11-12 764C, true peak close 1.02
  (08:11) vs 0.955 seen at the late 08:12 check -> stop 0.69 instead of 0.76; exit 0.69 vs ~0.76 available. Replay also
  showed that loosening the ladder would not have helped (option fell from 1.04 to 0.22 by 08:41), so the ladder
  widths stay. No dollar amounts or limits changed.

- **v3 (2026-11-12):** Section 7 - initial stops go below the lowest low of the base/flag (or the latest
  higher low) that preceded the breakout, with a $0.05 buffer, never just under the breakout level; size down
  or skip if it does not fit. Evidence: 2026-11-11 761C x3 (stop 758.80 under the 758.85 break; base low
  758.62 tagged to the cent, stopped -$27, SPY then +$2.40 higher) vs. the 761C x2 re-entry (stop under the
  758.965 higher low, held, +$50). No dollar amounts or limits changed.

- **v2 (2026-11-11):** Section 8 — discretionary exits close with a market (or marketable) order right after the stop cancel confirms. Evidence: 2026-11-10 trade 2 (744P) — passive limit at stale bid missed in a fast bounce, exit $0.14 below the intended price and $0.04 below the cancelled trailing stop, position briefly unprotected. No dollar amounts or limits changed.

- **v1 (2026-11-09):** Initial version from Kevin's playbook. Includes the 2026-11-09 lesson on fixed-% stops on low-delta contracts.
