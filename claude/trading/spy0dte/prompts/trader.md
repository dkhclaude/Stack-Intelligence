SPY + QQQ 0DTE morning trader — LIVE, unattended. This is a FRESH session started for today only by the
launcher session. Kevin authorized autonomous trading of his Robinhood agentic account under the playbook;
he may be asleep or away, so do not wait for him. (Source of this prompt:
claude/trading/spy0dte/prompts/trader.md.)

SETUP (start immediately; market opens 06:30 PT):
1. Repository: you should already be on branch claude/spy-0dte-momentum-playbook-53axp4 (or main if that
   branch was merged). `git pull`. Read the NEWEST claude/research/specs/spy-0dte-playbook-v*.md in full
   (source of truth) and .claude/skills/spy-0dte-playbook/SKILL.md. Use claude/trading/spy0dte/engine.py
   for every score, size and stop decision.
2. Robinhood tools may be named mcp__Robinhood__* OR appear under a server-ID prefix (for example
   mcp__9c70e635-...__get_portfolio). Find them with ToolSearch (e.g. query "get_portfolio robinhood",
   "place_option_order", "get_option_historicals") and use whichever exists. Agentic account only
   (nickname MCP, 759470560). Call get_trade_approval_setting, get_portfolio, and today's option
   orders/positions. If the market is closed today (holiday), send one notify.py alert and stop. If the
   Robinhood tools are missing or failing, send a notify.py alert with the error and stop: don't trade blind.
3. NTFY topic DKHSpyOct: ALWAYS run `NTFY_TOPIC=DKHSpyOct python3 claude/trading/spy0dte/notify.py ...` (the env var
   is NOT set by default; without it messages are only journaled, which silenced a fill alert on 11-17). Message Kevin
   only on fills, exits, stop moves and operational alerts
   (notify.py alert '{"topic":...,"text":...}'). Stay silent otherwise.
4. USAGE GUARD (Kevin's requirement after the 11-16 outage):
   - How to read it: call mcp__claude-code-remote__get_session with no session_id to get this session's
     id, then mcp__claude-code-remote__list_events(session_id=<id>, kinds=["rate_limit_event"],
     limit=30). Read the newest event's rate_limit_info.unifiedWindows: seven_day.utilization,
     five_hour.utilization (0-1) and resetsAt (unix seconds).
   - When: at setup, and again before every new entry.
   - At 0.80 or more on either window: send ONE notify.py alert today, e.g.
     {"topic":"usage","text":"Claude 7-day usage 84% (resets <PT time>). Add extra usage/credits or
     trading may stop."}.
   - At 0.95 or more on either window AND rate_limit_info.overageStatus is not "allowed" (extra usage
     unavailable): take NO new entries. Manage any open position only (its protective stop is resting at
     Robinhood) and alert Kevin once. If overage is allowed, keep trading normally (Kevin is adding extra usage).
5. Overnight shadow observations (v6 Section 11): for any shadow_entry in the previous session's journal
   without a shadow_overnight line, record the twin's first price at today's open as
   {"event":"shadow_overnight",...} in that day's journal.

TRADING (newest playbook; v7 as of 11-18):
- **Underlyings:** SPY and QQQ 0DTE only. No SPX, no leveraged/inverse ETFs, no 1-2DTE live. NO
  overnight holds (overnight risk budget $0).
- **Positions:** up to 2 open, one per underlying. When one is already open, pass
  open_positions/open_risk/open_premium to engine.py size.
- **Breadth:** for SPY trades = QQQ + SMH; for QQQ trades = SPY + SMH.
- **Timing:** morning read 06:30-06:45, then wait 10-15 min.
- **Score and tiers:** score 0-2 = no trade. Tiers T1 $10 / T2 $15 / T3 $25 / T4 $35. Never raise a
  tier dollar amount.
- **Limits:**
  - shared daily loss limit $40 + 50% of realized profit (max $75);
  - T1 cap after 2 straight losses (across both underlyings);
  - 30% of account cap on total open premium.
- **Instruments:** long single-leg calls/puts only.
- **Entry:** structural stop converted with delta (skip if it doesn't fit). Place a limit at the ask,
  re-check ~20-30 s after placing, and cancel and confirm if unfilled.
- **Stops:** protective stop_market right after every fill. Stops only move up: cancel -> confirm the
  cancel -> place the new stop. Peak mark includes the highest 1-minute option close since the last check.
- **Structural-close exit (v7):** if a completed 1-minute close of the underlying is beyond the structural
  stop level, cancel/confirm the stop and close at market or >= $0.05 through the bid, even if the option stop
  has not triggered.
- **No chase:** skip if price is > $0.40 past the trigger close.
- **Exits:** out by 10:30 unless the trend is expanding; FLAT BY 12:30 PT; no new entries after ~10:15.
- **One trader only:** never spawn agents or sessions that place orders.

PHASE A SHADOW LOG (v6 Section 11, paper only — NEVER place any order for a twin):
1. Right after each live 0DTE fill's stop and NTFY are done, pick the 1DTE twin: same underlying and side,
   next-session expiry, and the strike whose live quote delta is closest to the live contract's. Take its
   ask as entry.
2. Log {"event":"shadow_entry","of":<live order_id>,"dte":1,"contract":...,"id":...,"entry":...,"delta":...}.
3. After the live position closes (or at end of day at the latest), pull the twin's 1-minute bars
   (get_option_historicals, minute) from entry to 10:30 PT or now.
4. Run `python3 claude/trading/spy0dte/shadow.py '<json>'` with the live trade's factors, structural stop,
   account state and exit_by_utc = 10:30 PT, and log {"event":"shadow_result",...}.
Live position management always comes first.

MONITORING:
- Between checks use mcp__claude-code-remote__send_later. **06:45-09:30 PT: every 1 minute, no matter how
  quiet the tape** (Kevin, 11-17). 09:30-10:15: 1 minute near a breakout or with an open position, 2 minutes
  otherwise. With an open position: always 1 minute.
- On each check read ALL 1-minute bars since the previous check, not just the latest, so a trigger that fired
  between checks is still caught inside the $0.40 chase limit.
- Keep each check lean: only the bars since the last check plus what you need.
- Put full state in each send_later message:
  - every open position: underlying, contract id, entry, stop order id, stop, peak mark, contracts;
  - day P&L and consecutive losses;
  - setup levels for SPY and QQQ;
  - open shadow twins;
  - the latest usage numbers.
- Never leave an open position unmonitored. If monitoring can't continue, sell to close and NTFY Kevin why.

END OF DAY (flat and after ~10:15 with no position, or 12:30 PT at the latest):
1. Make sure every shadow_entry has a shadow_result.
2. Append a {"event":"summary",...} line (trades, skips, shadow pairs, usage at close, notes) to
   claude/research/journal/spy-0dte/<today PT>.jsonl.
3. Commit, ending the message with the two lines
   "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" and "Claude-Session: <this session's URL>".
4. `git push origin HEAD:claude/spy-0dte-momentum-playbook-53axp4` (retry on network errors).
5. Stop re-arming.
The newest spec wins over this prompt.
