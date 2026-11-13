---
playbook: SPY 0DTE Momentum Playbook
version: 6 (DRAFT)
status: proposed - NOT ACTIVE. Live trading stays on v5 until Kevin approves.
proposed: 2026-11-13
owner: Kevin
---

# Playbook v6 DRAFT: 1-2 DTE contracts for SPY and QQQ

This draft is kept outside `specs/` on purpose. The skill loads the newest `spy-0dte-playbook-v*.md`,
so this file cannot go live by accident. To activate it, Kevin approves the changes, then they are
copied into `spy-0dte-playbook-v6.md`, `config.json` and the engine.

v6 is v5 plus the changes below. Everything not mentioned stays exactly as in v5. That includes the
confluence score, the tier dollar amounts, the daily loss limit, the 30% cap, the 2-position rule,
the stop ladder, out by 10:30, flat by 12:30, and one trader.

Evidence: `claude/research/replay/README.md`, a replay of the 6 live trades from 11-10 to 11-12.
- On the 3 signals both expiries could take, 1DTE tied 0DTE: +$52 each, with 1DTE using 2x the premium.
- 1DTE no longer fit the tier for 3 of the 6 signals.
- 2DTE fit only 1 signal, which lost $24.
That is not enough to trade 1DTE live. So v6 is built in two phases.

## Phase A: shadow log (proposed to start now, no money at risk)

1. Every live 0DTE entry gets a **shadow 1DTE twin** in the journal.
   - **Contract:** same underlying, same side, next-session expiry. Pick the strike whose **live
     quote delta** is closest to the live 0DTE contract's delta. Use the quote's delta, not a model;
     the replay showed model-matched strikes came out 0.10 delta high.
   - **Sizing:** shadow entry = the 1DTE ask at the live fill time. Size it with `engine.size` using
     the same factors, tier, structural stop and account state. Record the contracts, the risk per
     contract and whether it fit. Never place an order for the twin.
   - **Management:** run the same ladder on the twin's 1-minute closes and lows, from option
     historicals read at each check while the bars still exist (they turn into gap-fill after
     expiry). Close the twin when the ladder says so, or at the live position's exit rules
     (out by 10:30, flat by 12:30).
   - **Journal:** add `{"event":"shadow", "of": <live order_id>, "dte":1, ...}` lines with entry, risk
     per contract, contracts, stop moves, exit and P&L.
2. Shadow work must never delay a live action. On each check, the live position comes first (stop,
   ladder, exits). Shadow bookkeeping is done afterwards from historicals, and it is fine if it lags.
3. The daily review grades the shadow next to the live trade. It counts four things:
   - P&L per signal,
   - wick stop-outs avoided,
   - signals the twin couldn't size (didn't fit the tier),
   - premium used.

## Phase B: live 1DTE (only after the go-live test and Kevin's approval)

### Go-live test, measured on the shadow log

- At least **20 paired signals** (live 0DTE plus shadow 1DTE).
- Shadow 1DTE P&L at least as good as live 0DTE on the same signals, **and** fewer stop-outs on
  1-minute wicks.
- The twin fit its tier on at least 70% of signals. If it doesn't, the answer is "1DTE doesn't suit
  these tier sizes" and that ends it; the tiers are not changed to make it fit.
- Kevin approves in writing (chat). The review cannot activate Phase B on its own.

### What would change in Phase B

1. **Expiry choice (Section 1):**
   - Allowed expiries become SPY/QQQ **0DTE or 1DTE** (the next listed session).
   - **2DTE is excluded:** it hits the 30% cap and the tier caps at this account size, and the one
     replayed 2DTE trade lost $24.
   - **Choosing per signal:** default 0DTE. Use 1DTE only when the 1DTE contract at delta 0.18-0.30
     fits the tier (`engine.size` gives at least 1 contract) **and** either:
     - the trade is a trend continuation that starts after 08:30 PT, where 0DTE time decay and
       whipsaw hurt most; or
     - the 0DTE contract at the target delta costs under $0.20, too little premium to give the ladder
       room.
   - These two conditions are the hypothesis Phase A tests. Phase A must confirm or remove them
     before Phase B starts.
2. **No overnight holds.**
   - A 1DTE position follows the same out-by-10:30 and flat-by-12:30 rules as 0DTE.
   - Holding overnight would need its own risk budget, because a stop doesn't protect against a gap,
     so the honest risk is the whole premium. Only Kevin can set that budget. It is out of scope for v6.
3. **Sizing (Section 7):**
   - Unchanged formula: risk per contract = delta × structural stop distance, capped by the tier and
     the 30% cap.
   - A 1DTE contract costs about 2x more, so the 30% cap binds sooner. The engine already enforces this.
4. **Exit engine (Section 8):**
   - Same ladder for now.
   - **Open question for Phase A:** the ladder's % of premium rungs sit about 1.8x farther away in
     risk terms (R) on 1DTE than on 0DTE. The breakeven rung needs ~1.25R vs ~0.7R. On 11-12 that
     turned a winner into a −$9 loss.
   - An R-based ladder tested mixed (+$29 vs +$52 on 3 trades). Collect shadow data on both ladders
     before proposing one.
5. **Journal and engine:**
   - Add `dte` to every fill/exit line.
   - `engine.size` needs no change.
   - Add `dte` to the config's allowed expiries (`"expiries": [0, 1]`).
   - Add a unit test that rejects 2DTE.

## What does not change in any phase

- The tier dollar amounts, the daily loss limit, the 30% cap, the account, long single-leg calls and
  puts only, and one trader.
- Only Kevin changes dollar amounts or approves Phase B.

## Changelog

- **v6 DRAFT (2026-11-13):** Proposed Phase A shadow log of delta-matched 1DTE twins for every live
  0DTE entry; Phase B (live 1DTE, 2DTE excluded, no overnight) gated on 20+ paired signals and Kevin's
  approval. Based on the 11-10..11-12 replay (`claude/research/replay/`). Not active.
