# One forward momentum paper experiment

Purpose: evaluate a new fixed entry hypothesis using the existing verified public-chain price reader. No investment return is promised. No wallet, account creation, paid service or real order.

Before this run: two reversal trades lost. The existing 31-minute price log is development data, not validation data for this momentum hypothesis. A backward-looking opportunity check found some large moves but cannot identify executable profitable entries. No parameter sweep or historical strategy-return claim is used to select these rules.

## Frozen rules

- STREAM mint 9a98oQHtxfqmr4EyzsP6wfw69uYAK3JbUeVEuNW1pump; pool D9NCkN3unPTVLtA56Y68J2cXisje9yyYe61gMM2HCHwJ.
- At most 90 minutes, six completed roundtrips, one position at a time; 1 SOL virtual capital, 0.05 SOL per entry.
- Read official pinned PumpSwap SDK 2.1.0 public-account price estimates roughly every 10 seconds. Indicative sampled price is 50,000,000 lamports divided by expected token output. Not a traded-price or volume series.
- Six contiguous closed minute bars; each has at least four observations and maximum within-bar observation gap of 22 seconds. Latest closed bar at most 90 seconds old.
- Entry signal: latest close above the previous five bars' highs, return from close three minutes earlier at least 1%, latest bar close/open return at least 0.3%.
- Entry after at least 10 seconds on a later observation, signal expires after 60 seconds. No entry during final 330 seconds.
- Same cost guard: modeled immediate buy/sell loss including network assumptions at most 2%. Adverse output bounds 0.5% each side; embedded AMM fees; assumed network 50,000 lamports each side and 50,000 once for setup. RPC minimum token-account deposit is a potentially recoverable asset, not a realized refund or trading expense.
- Same exits: net +2%, net -3%, or five-minute holding cap, 60-second cooldown. Observed session loss limit 0.05 SOL; stops are sampled decisions, not guaranteed execution limits.
- Stop after three consecutive data errors. Chain context slots must advance.
- Retain every observed quote and liquidation value while holding so stop overshoot can be examined.

## Decision rule

Stop at the fixed time/trade/data/risk limit. No automatic extension or retuning. A few gains or losses do not establish an edge. Assess actual sample size, complete data coverage, net after modeled costs and all closed/open positions before deciding on further work. No progression to real trading is authorized.

## Observation startup clarification before the live observation run

The initial attempt (run 38763704991) stopped before observation because its preflight cost exceeded 2%; no strategy return was produced. The next run allows public read-only collection when the cost guard is temporarily exceeded. Both advancing chain-context checks still must pass. Every actual paper entry still enforces the unchanged 2% cost ceiling through StreamLedger.enter. Entry thresholds, output bounds, position size and exits are unchanged. This startup change uses no performance observations from the blocked attempt.
