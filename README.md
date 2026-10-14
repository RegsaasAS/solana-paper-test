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

## Prepared GitHub test

An update to `probe.py` or the workflow on `main` starts one ten-minute test.
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
