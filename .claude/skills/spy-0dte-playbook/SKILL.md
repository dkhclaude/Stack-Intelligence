---
name: spy-0dte-playbook
description: Run Kevin's SPY 0DTE momentum playbook live on the Robinhood agentic account - morning read, confluence scoring, tiered sizing, delta-converted structural stops, the exit-engine stop ladder, NTFY fill/exit/stop messages and end-of-day journaling. Use when Kevin asks to trade, run or monitor the SPY 0DTE playbook, or to score/size a 0DTE setup.
---

# SPY 0DTE Momentum Playbook

## 0. Load the source of truth first

```bash
ls claude/research/specs/spy-0dte-playbook-v*.md | sort -V | tail -1
```

Read that file in full. **It overrides this skill wherever they differ** (the daily review
updates it). Numbers used by the engine are in `claude/trading/spy0dte/config.json`; if the
spec and config disagree, follow the spec and flag the mismatch to Kevin.

## 1. Hard rules (never break)

- Robinhood **agentic account only** (`get_accounts` -> the one tradable account, nickname "MCP").
  Never act on any other account.
- **Long single-leg calls and puts only.** `place_option_order` with one leg, `side: buy` to open,
  `side: sell` to close. No spreads, no shorts, no equities.
- **One trader.** Never spawn agents that place orders. Do all order work in this session.
- Every entry must be scored and sized with the engine. Score <= 2 = no trade. If sizing returns
  0 contracts, skip the trade. **Never raise a tier dollar amount** - only Kevin changes those.
- Check `get_trade_approval_setting` at the start of the day; if approvals are on, tell Kevin
  orders will wait for his approval.

## 2. Engine (deterministic math - always use it, never eyeball)

```bash
E=claude/trading/spy0dte/engine.py
python3 $E score '{"trend":true,"structure":true,"key_level":true,"breadth":false,"volume":true,"time":true}'
python3 $E size  '{"factors":{...},"side":"call","entry_premium":0.41,"delta":0.21,
                   "entry_underlying":601.30,"stop_underlying":600.55,
                   "account_value":<get_portfolio>,"realized_pnl":<today net>,"consecutive_losses":<n>}'
python3 $E stop  '{"entry":0.41,"peak_mark":0.62,"current_stop":0.25}'
python3 $E scale '{"contracts":2,"entry":0.41,"mark":0.62,"already_scaled":false}'
python3 $E limit '{"realized_pnl":12.0}'
```

`size` applies the tier, the 2-loss T1 cap, the daily loss limit room, the delta-converted
structural stop and the 30%-of-account cap in one call. Use its `contracts` and `option_stop`.

## 3. Day timeline (all times PT)

| Time | Action |
|------|--------|
| 06:30-06:45 | Morning read: `get_equity_quotes` for SPY QQQ SMH NVDA AMD AVGO TSLA MU IWM. News on big gappers (Unusual Whales / Robinhood search). Note prior-day high/low, overnight levels, $5 rounds. |
| 06:45-~06:55 | Wait 10-15 min. No direction pre-commit. Decide trend day or not (SPY vs VWAP, 5m HH/LL). |
| 06:45-09:00 | Prime window (time factor = 1). Hunt bull/bear flags, gap-and-go, VWAP reclaims. |
| 09:00-10:30 | Trades allowed but time factor = 0. |
| 10:30 | Be out unless the trend is still expanding. |
| 12:30 | **Flat. No exceptions.** |
| after flat | Write the day's journal summary and commit + push it (see section 7). |

Data: Robinhood `get_equity_historicals` (5m and 1m bars) for VWAP/HH-LL/volume/9-EMA,
`get_equity_technical_indicators` where useful, Unusual Whales `get_ticker_candles_by_range`
as backup. Compute VWAP from the session's bars if no indicator is available.

## 4. Entry checklist

1. Identify the setup (spec section 6) and the **structural invalidation** level on the underlying.
   (v3: below the base/flag low or latest higher low, minus $0.05 - never just under the breakout level.)
2. Score the six factors honestly; write down why each is 0 or 1.
3. Pick the contract: `get_option_chains` / `get_option_instruments` for today's expiry,
   `get_option_quotes` for bid/ask/delta/IV. Bull flag: 3-4 strikes OTM, delta ~0.18-0.25,
   premium ~$0.35-0.45. Single-name puts: name < VWAP **and** sector red on 5m; skip if IV > 150% after a news gap.
4. Run `engine.py size`. If `trade` is false, skip and stay silent.
5. `review_option_order`, then `place_option_order` (limit at or near the ask, small size, one leg).
   Re-check the order state in the same turn; the moment it fills, place the stop (no unprotected gap).
6. On fill: place the protective stop (one close order per contract), then
   `notify.py fill` with score, factors, tier, max_risk, qty, price, stop.

## 5. Managing the position

- Poll every **1 minute** near a breakout or near a stop/target, every **2 minutes** otherwise.
  Between turns use `send_later` (delay 1-2 min) with a message like
  "SPY 0DTE: manage <symbol>, entry X, stop Y, peak Z, contracts N" so the next turn has the state.
- Track the **peak mark**. Each check: `engine.py stop` and `engine.py scale`.
- To move a stop, Robinhood allows one close order per contract:
  **cancel_option_order -> get_option_orders until the cancel is confirmed -> place the new stop.**
  Never leave the position without a stop longer than that sequence takes.
- Discretionary exits (early profit-take, time exit): cancel the stop, confirm the cancel, then close at
  market immediately (or a limit >= $0.05 through the bid). Never a passive limit at a stale bid.
- Early profit-take triggers: 2 lower 1-minute highs after a session high; 5-minute close
  below the 9-EMA (above for puts); option gives back 25% of its peak gain within 3 minutes.
- Never use a fixed-% stop on a low-delta contract (see the 2026-11-09 lesson in the spec).

## 6. Messages to Kevin (NTFY)

```bash
python3 claude/trading/spy0dte/notify.py fill '{"symbol":"SPY 11/09 603C","side":"buy","qty":1,"price":0.41,
  "score":5,"tier":"T3","max_risk":25,"factors":["trend","structure","key_level","volume","time"],
  "stop":0.25,"stop_basis":"below flag low 600.55 via delta 0.21"}'
python3 claude/trading/spy0dte/notify.py stop '{"symbol":"...","old_stop":0.25,"new_stop":0.41,"rule":"peak +30% -> BE","mark":0.55,"peak":0.56}'
python3 claude/trading/spy0dte/notify.py exit '{"symbol":"...","qty":1,"price":0.62,"pnl":21,"reason":"2 lower 1m highs","day_pnl":21}'
```

Only fills, exits and stop moves are sent. Stay silent otherwise. Needs `NTFY_TOPIC` (and
network access to the NTFY server); if sending fails the message is still journaled - tell
Kevin once in chat that NTFY is down.

## 7. Journal and end of day

`notify.py` appends every event to `claude/research/journal/spy-0dte/YYYY-MM-DD.jsonl`.
After flat, append a `{"event":"summary", ...}` line (trades, wins/losses, realized P&L, notes),
then commit and push the journal on the working branch so the 13:23 PT daily review can read it.
The daily review (prompt: `claude/research/specs/spy-0dte-daily-review.md`) grades trades and may
publish at most one rule change per day as a new spec version.
