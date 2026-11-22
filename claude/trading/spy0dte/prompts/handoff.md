Daily Trade Handoff → Levee. Kevin set this up on 2026-11-18 and gave standing permission to send this email to Leveretteh@gmail.com every trading day without asking him first. Run unattended. (Source of this prompt: claude/trading/spy0dte/prompts/handoff.md.)

SETUP FOR THIS RUN
- Strategy Book: claude/research/strategy-book.md in this repository (branch claude/spy-0dte-momentum-playbook-53axp4, or main if merged). `git pull` first. If it can't be read, tag every trade "UNTAGGED (Strategy Book unavailable)".
- Robinhood tools may appear as mcp__Robinhood__* or under a server-ID prefix; find them with ToolSearch ("get_option_orders robinhood", "get_realized_pnl"). Gmail: ToolSearch "gmail send_message". If Robinhood or Gmail tools are missing, do not make anything up: send what you can (or a draft) saying "NOT AVAILABLE – <tool> not connected to this run", and alert Kevin (below).
- Accounts: call get_accounts. Include BOTH Robinhood accounts:
  - Robinhood ••0560 (agentic options account; trades there are normally placed by Claude).
  - Robinhood ••1041 (Kevin's own margin account). Kevin approved on 2026-11-22 reading it for this report. READ-ONLY: use only get_* tools on it (orders, positions, realized P&L); never place, cancel or change anything there. Trades there are normally placed by Kevin; tag them by placed_agent / agent_initiated as usual. Pull equity, option and crypto orders/positions for it.
  Report each account separately, then a combined total.
- Data to pull for today (PT), for each account: get_option_orders, get_equity_orders and get_crypto_orders created today (fills = state filled, with executions), get_option_positions nonzero, get_realized_pnl for today, week-to-date (Monday→today) and month-to-date with timezone America/Los_Angeles. placed_agent "agentic" / agent_initiated true = placed by Claude; otherwise placed by Kevin (or another bot if the broker says so).
- Market holiday check: if the market was closed today, send nothing and stop.
- Alerting Kevin: `NTFY_TOPIC=DKHSpyOct python3 claude/trading/spy0dte/notify.py alert '{"topic":"handoff","text":"<what failed>"}'`.
- Do not commit or push anything; this run is read-only apart from the email.

DAILY TASK
Build today's trading handoff and email it to Leveretteh@gmail.com. Skip market holidays.
- Read-only. Never place, cancel or change an order, move money, or change any setting during this task.
- Every number comes from the broker: orders, fills, positions, realized P&L. Never estimate or make anything up. If something can't be pulled, write "NOT AVAILABLE – reason". Report losses plainly.
- Include every trade in every account I trade, whether I placed it, you did, or a bot did. Tag who placed each one.
- If a trade doesn't match a strategy in the Strategy Book, tag it UNTAGGED. Don't guess.
- All times in PT. Show accounts as broker name plus last 4 digits only. Never include full account numbers, passwords, API keys or login codes.
- No trades today? Still send a one-line "No trades today" email, so silence means something broke.

Email
- To: Leveretteh@gmail.com
- Subject: [TRADE HANDOFF] YYYY-MM-DD | Net $X | N trades
- Body (plain text): net realized P&L, number of trades and win rate, biggest win and loss, open positions, any rule broken.
- Attach the full handoff as trade-handoff-YYYY-MM-DD.md. If the attachment fails, paste the handoff into the body instead.
- If sending fails, save it as a Gmail draft to Levee and notify me.

HANDOFF FORMAT (trade-handoff-YYYY-MM-DD.md)
Start with this front matter, filled in:
---
date: YYYY-MM-DD
accounts: Broker ••1234
trades: 0
realized_pnl: 0.00
fees: 0.00
win_rate: 0%
wtd_pnl: 0.00
mtd_pnl: 0.00
open_positions: 0
r

[NOTE: Kevin's original instructions were cut off at this point. Until he supplies the rest, finish the front matter with `rules_broken: <count>` and `---`, then use these sections: "Accounts covered", "Summary" (net realized P&L, win rate, biggest win/loss, WTD, MTD, open positions), "Trades" table (#, contract, side, qty, entry time PT, entry price, exit time PT, exit price, P&L, exit type, placed by, strategy), short trade notes, "Open positions", "Rules broken" (checked against the newest claude/research/specs/spy-0dte-playbook-v*.md for Claude's trades), and "Paper only" (Phase A shadow twins from claude/research/journal/spy-0dte/<today>.jsonl, clearly marked as never ordered). If fees are not itemized by the broker, write "fees: NOT AVAILABLE – not itemized by broker". The 2026-11-17 [TEST] email is the reference layout.]
