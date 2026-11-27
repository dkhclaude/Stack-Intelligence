# SPY playbook daily review (weekdays 13:23 PT)

Prompt used by the scheduled task "SPY playbook daily review". Read-only on the brokerage:
this task never places, cancels or changes orders.

1. Load the newest `claude/research/specs/spy-0dte-playbook-v*.md` and today's journal
   `claude/research/journal/spy-0dte/YYYY-MM-DD.jsonl` (pull the latest branch first).
   Cross-check against Robinhood `get_option_orders` / `get_pnl_trade_history` on the agentic
   account for today. If there were no trades, note "no trades" in lessons.md and stop.
2. Grade each trade A-F on: rule adherence (score honest? tier and size per engine? structural
   stop? stop ladder followed? cancel-confirm-replace done? time rules?), and execution quality
   (entry location, exit vs. what the exit engine called for). Separate process from outcome.
3. Append a dated section to `claude/research/journal/spy-0dte/lessons.md`: per-trade grade,
   score/factors/tier, P&L, what went right, what went wrong, one-line lesson.
4. Rule change - **at most one per day**, only if backed by evidence from the journal/orders
   (cite the trades). Never change tier dollar amounts, the daily loss limit, the 30% account cap,
   the account/instrument restrictions or the one-trader rule; those are Kevin's.
   If a change is warranted: copy the newest spec to `v<N+1>`, bump `version`/`effective`,
   make the change, add a changelog entry with the evidence, and update
   `claude/trading/spy0dte/config.json` (`playbook_version` and any changed number). Run
   `python3 -m unittest` in `claude/trading/spy0dte` and fix tests only to reflect the new rule.
5. Commit and push. Send one NTFY summary to Kevin (day P&L, grades, and the rule change or
   "no rule change").
