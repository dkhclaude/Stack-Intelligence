# Replay: 0DTE vs 1DTE vs 2DTE on the live trades of 2026-11-10 to 11-12

Question: if each live signal had been traded with a 1DTE or 2DTE SPY contract instead of 0DTE,
with everything else the same, what would have happened?

Same signal, same structural stop on SPY, same score and tier, same engine sizing
(`engine.size`), same stop ladder (`engine.next_stop`, `engine.scale_out`). Only the expiry changes.
The 1DTE/2DTE strike was picked to match the live 0DTE contract's delta (Black-Scholes on a
trading-time clock, IV backed out of the live 0DTE price).

Run: `python3 replay.py` (results also in `results.jsonl`); `python3 sensitivity_r_ladder.py`.

## Results

| Signal | 0DTE (sim / real) | 1DTE (delta-matched) | 2DTE (delta-matched) |
|---|---|---|---|
| 11-10 #1 call, T4 $35 | 1 ct, +$16 / +$24 | **0 ct**: $36 risk > $35 | **0 ct**: 30% cap |
| 11-10 #2 put, T3 $25 | 1 ct, +$19 / +$27 | **0 ct**: $28 risk > $25 | **0 ct**: 30% cap |
| 11-11 #1 call, T2 $15 | 1 ct, +$14 / +$14 | **0 ct**: $17 risk > $15 | **0 ct**: $19 risk > $15 |
| 11-11 #2 call, T3 $25 | 2 ct, −$18 / −$27 | 1 ct, −$14 (stopped in entry bar) | **0 ct**: 30% cap |
| 11-11 #3 call, T3 $25 | 2 ct, +$50 / +$50 | 1 ct, **+$75** (still open 09:45, marked) | **0 ct**: 30% cap |
| 11-12 #1 call, T3 $25 | 1 ct, +$20 / +$20 | 1 ct, **−$9** (never reached breakeven rung) | 1 ct, −$24 |
| **Total** | **+$101 sim / +$108 real**, 6 trades | **+$52**, 3 trades | **−$24**, 1 trade |

On the 3 signals both 0DTE and 1DTE could take, P&L was **tied: +$52 each**. 1DTE used about 2x the
premium to get there ($330 vs $169).

## What the replay shows

1. **Sizing is the binding constraint, not the expiry.** Delta-matched 1DTE contracts carried slightly
   *more* risk per contract than the 0DTE ones (1-2DTE IV was higher than 0DTE IV on 11-11, so the
   "matched" strike's real delta was ~0.32 vs 0.21). Three of six signals no longer fit their tier.
   2DTE premiums ($1.40-2.40) hit the 30% cap at the $489-540 account size of that week.
2. **1DTE's smoother path cuts both ways.**
   - It held the 11-11 trend leg that 0DTE's trail stop exited early (+$75 vs +$50).
   - On 11-12 the 1DTE contract only rose +38% before SPY reversed. The ladder's first rung (+30% to
     breakeven) had moved its stop to entry, and it then gapped through that stop on the reversal
     (−$9 vs 0DTE's +$20).
   - The cause: the % of premium ladder rungs are much farther away in risk terms on a 1DTE contract.
     The breakeven rung needs about 1.25R on 1DTE vs about 0.7R on 0DTE.
3. **The R-multiple ladder test was mixed** (1DTE +$29 vs +$52 with the current ladder). With 3 trades
   that proves nothing either way, so there is no case for changing the ladder yet.
4. **2DTE is not viable at the current account and tier sizes.** It fit one trade, and that trade lost
   $24.

## Limitations (read before using these numbers)

- Robinhood keeps only **5-minute bars** for expired option contracts (1-minute requests return gap-fill).
  The ladder therefore runs on 5-minute OHLC: the stop is checked against the bar low, and the peak
  uses the bar close. The 0DTE simulation landed within $9 of each real trade and +$101 vs +$108 net,
  so it is a reasonable but rough model.
- **The sample is 6 signals from one week.** This is a direction to investigate, not a statistical result.
- Bar prices are trades, not bid/ask; spreads are not modelled. SPY 0-2DTE spreads are $0.01-0.03.
- **How the 1/2DTE entry price was estimated:** it was interpolated within the entry bar. It takes the
  same fraction of the bar's open-to-close move as the real 0DTE fill did.
- **Early profit-take exits are not modelled for any expiry.** That covers the exits on 2 lower
  1-minute highs, a 5-minute close below the 9-EMA, and a 25% give-back.
- The 11-11 #2 0DTE trade was stopped inside its entry bar (known from the journal). That one case
  also checks the entry bar's low for every expiry.
- Positions still open at the end of the data (09:45 PT) are marked at the last close, not run to the
  10:30 exit.

## Conclusion

There is **no evidence yet** that 1DTE beats 0DTE for this playbook's intraday trades, and 2DTE is
worse at the current size. The useful next step is a forward **shadow log** (playbook v6 draft): every
live 0DTE entry also records the delta-matched 1DTE contract. That builds real 1-minute evidence without
risking money, and it gives Kevin a data-backed go/no-go.
