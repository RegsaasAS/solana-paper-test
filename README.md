# SOL/USDT paper integration test

Bounded software test against Kraken's public order book. No accounts, API keys,
wallets or real orders. Entries are deliberately timed to test the complete
data, simulated buy, simulated sell and accounting pipeline. They are not a
trading strategy.

## What has actually been tested

On 14 October 2026, the local integration test completed two round trips,
recorded 14 order-book snapshots and stopped automatically. Starting virtual
cash was 100 USDT; net modeled result was -0.2056512551923468 USDT.

The model consumes visible book depth, uses asks for buys and bids for sells,
respects the reported trade minimums. Future runs default to 0.8% fees and
0.1% adverse slippage on each side. The fee models Kraken's published base
spot taker rate, checked on 14 October 2026; it is not a verified account rate.
The initial local and cloud probes instead used an explicit 0.4% fee assumption. Book snapshots are not executable quotes or verified fills.

## Original ten-minute GitHub test (completed)

The original workflow ran one ten-minute integration test; its verified result
is recorded below. The workflow is being replaced by the one-hour signal screen.
The job has a twelve-minute timeout, read-only repository permissions, no
schedule, no artifact upload and no caches. It uses a standard Linux runner
in a public repository. Results are printed to logs and the job summary.

This test is not a permanent hosting solution, an investment recommendation,
or evidence of profitable trading. Failure to obtain fresh data records an
error; an unresolved position is never presented as a completed trade.

## Run locally

```sh
python3 probe.py --seconds 180 --hold 45 --poll 10 --output paper-result
```

Python standard library only; no package installation is required.

## Verified GitHub execution — 14 October 2026

[Run 38597354015](https://github.com/RegsaasAS/solana-paper-test/actions/runs/38597354015)
completed successfully from 16:21:22 to 16:31:22 UTC on a standard hosted
Linux runner in this public repository. No open chat or user PC was required.

- 7 completed simulated round trips; 60 order-book observations.
- No data errors and no unresolved position; stopped at the time limit.
- Initial virtual cash: 100 USDT. Final: 99.282556851007994 USDT.
- Executed model result with 0.4% fees per side: -0.717443148992006 USDT.
- Sensitivity calculation for the same recorded quantities with 0.8% fees
  per side: -1.274570783812512 USDT. This is a recalculation, not a new run.
- Cash conservation and alternating buy/sell sequence independently checked.

These timed trades test functionality only. They provide no evidence of a
profitable strategy or real order execution. No permanent service is running.

Fee references: [Kraken fee schedule](https://www.kraken.com/features/fee-schedule)
and [July 2026 changes](https://support.kraken.com/articles/cross-platform-fee-tier-changes).

## Next test: one-hour forward signal screen

This is one fixed exploratory hypothesis. Parameters are chosen before the run,
not fitted to the previous timed probes. No trading API, keys, paid data,
scheduled repetition or permanent service is added.

Entry requires the latest **completed** one-minute candle to close above the
highs of the preceding five completed candles, gain at least 0.3% from its open,
and show at least 1.5 times the preceding five candles' mean volume. Missing,
unfinished or stale candles cannot trigger entry. An eligible signal waits at
least ten seconds for a new execution quote, expires after 90 seconds, and is
cancelled if the breakout is lost or the spread exceeds 0.1%.

Virtual starting cash is 100 USDT; each entry costs at most 10 USDT including
fees. At most one position is open. Simulated orders consume visible book
depth and include 0.8% fees plus 0.1% adverse slippage per side. Net take-profit
is +1%; net stop-loss is -2.5%; remaining positions are exited after five
minutes or at session end. These are sampled best-effort rules, not guaranteed
loss limits. A 5-USDT session loss check and 12-roundtrip limit stop new entries.
There is a 60-second cooldown. No new entry occurs in the final 5.5 minutes.

Run length is 60 minutes, with a short bounded liquidation grace period and a
65-minute job timeout. Three consecutive data failures stop the test; an open
position remains explicitly unresolved when it cannot be priced/exited.
Signals, rejected signals, fees, all trades and unresolved exposure are kept
in the final result and logs. A counterfactual buy-and-hold benchmark uses the
same 10-USDT entry budget; it is a simulation, not a real executed benchmark.

No signal or too few trades means insufficient evidence. Every result sets
`adequate_sample=false`: one hour cannot establish profitability. Any later
change of rule requires a new forward sample; this run's rules stay fixed.
The strategy trades SOL/USDT on Kraken, not newly launched Solana memecoins.

Synthetic tests cover unfinished/future data, volume confirmation, stale
signals, delayed/expired entries, duplicate-entry prevention, costs in exits,
stop/time exits, missing exit liquidity, end-of-session limits, and zero-trade
reporting. A short live-data preflight is performed before publishing.

Launch: `python3 signal_test.py --seconds 3600 --output signal-result`.
The GitHub workflow now runs this screen on relevant code updates. It has
read-only token permissions, no caches/artifact uploads, and no recurring schedule.

Pre-publication checks passed: 12 synthetic tests and a 90-second live-data
preflight with 7 order-book observations, no data errors and no trades.
The short preflight intentionally prohibits entries that could outlive it;
it checks data and signal evaluation, not live signal execution.
