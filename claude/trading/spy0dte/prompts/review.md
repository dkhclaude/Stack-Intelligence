SPY playbook daily review (post-close). Fresh session started by the launcher. READ-ONLY on the
brokerage: never place, cancel or modify any order. (Source: claude/trading/spy0dte/prompts/review.md.)

0. You should be on branch claude/spy-0dte-momentum-playbook-53axp4 (or main if merged); `git pull`.
   Robinhood tools may be named mcp__Robinhood__* or appear under a server-ID prefix; find them with
   ToolSearch (e.g. "get_option_orders").
1. Follow claude/research/specs/spy-0dte-daily-review.md exactly.
   - Read the newest claude/research/specs/spy-0dte-playbook-v*.md and today's journal
     claude/research/journal/spy-0dte/<today PT>.jsonl.
   - Cross-check today's option orders and P&L on the Robinhood agentic account (nickname MCP, 759470560).
   - Also grade the Phase A shadow pairs (Section 11).
2. Grade each trade (process vs outcome). Log score/factors/tier, P&L and lessons in
   claude/research/journal/spy-0dte/lessons.md.
3. Make at most ONE evidence-backed rule change:
   - Write it as a new spec version v<N+1> with a changelog entry.
   - Update claude/trading/spy0dte/config.json and run `python3 -m unittest` in claude/trading/spy0dte.
   - Never change tier dollar amounts, the daily loss limit, the 30% cap, account/instrument limits or
     the one-trader rule.
4. Commit and push (`git push origin HEAD:claude/spy-0dte-momentum-playbook-53axp4`). End the commit
   message with "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" and
   "Claude-Session: <this session's URL>". If there were no trades, record "no trades" in lessons.md
   and make no rule change.
5. Send one NTFY summary to Kevin (day P&L, grades, rule change or none):
   `NTFY_TOPIC=DKHSpyOct python3 claude/trading/spy0dte/notify.py alert '{"topic":"daily review","text":"..."}'`.
   If the send is blocked by a permission check, record that in lessons.md; don't work around it.
