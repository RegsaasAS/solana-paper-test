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
respects the reported trade minimums, and additionally assumes 0.4% fees and
0.1% adverse slippage on each side. Fees are assumptions, not verified account
rates. Book snapshots are not executable quotes or verified fills.

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
