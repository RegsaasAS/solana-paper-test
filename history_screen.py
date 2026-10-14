"""Retrospective diagnostic of fixed rules, not a trade backtest."""
import collections
import datetime as dt
import json
from decimal import Decimal as D

from probe import public
from signal_test import RULES, inspect_signal


def main():
    raw = public('OHLC?pair=SOLUSDT&interval=1')['SOLUSDT']
    server = int(public('Time')['unixtime'])
    rows = [r for r in raw[:-1] if int(r[0]) + 60 <= server]
    if len(rows) < 6:
        raise RuntimeError('Insufficient closed bars')
    if server - (int(rows[-1][0]) + 60) > 90:
        raise RuntimeError('Stale market data')
    fee, slip = D(RULES['fee_per_side']), D(RULES['adverse_slippage_per_side'])
    factor = (1 + slip) * (1 + fee) / ((1 - slip) * (1 - fee))
    breakeven = factor - 1
    target = factor * (1 + D(RULES['net_take_profit'])) - 1
    reasons, signals = collections.Counter(), []
    for i in range(5, len(rows)):
        # Append the actual unfinished row, which inspect_signal discards.
        decision = inspect_signal(rows[i-5:i+1] + [raw[-1]], int(rows[i][0]) + 60)
        reasons[decision['reason']] += 1
        if not decision['eligible']:
            continue
        future = rows[i+1:i+6]
        complete = len(future) == 5 and [int(r[0]) for r in future] == list(range(int(rows[i][0])+60, int(rows[i][0])+360, 60))
        high_return = max(D(r[2]) for r in future) / D(rows[i][4]) - 1 if complete else None
        signals.append(dict(signal_utc=dt.datetime.fromtimestamp(int(rows[i][0])+60, dt.timezone.utc).isoformat(), candle_return=decision['candle_return'], volume_multiple=decision['volume_multiple'], future_five_minutes_complete=complete, next_five_minute_max_high_return_from_signal_close=str(high_return) if high_return is not None else None))
    observed = [D(s['next_five_minute_max_high_return_from_signal_close']) for s in signals if s['future_five_minutes_complete']]
    result = dict(purpose='retrospective_signal_and_price_range_diagnostic_not_trade_performance', status='completed', fetched_utc=dt.datetime.now(dt.timezone.utc).isoformat(), first_bar_utc=dt.datetime.fromtimestamp(int(rows[0][0]), dt.timezone.utc).isoformat(), last_bar_utc=dt.datetime.fromtimestamp(int(rows[-1][0]), dt.timezone.utc).isoformat(), closed_bars=len(rows), screened_minutes=sum(reasons.values()), rules=RULES, reasons=dict(reasons), eligible_signals=len(signals), signals_with_complete_next_five_minutes=len(observed), break_even_price_increase_before_spread=str(breakeven), price_increase_for_one_percent_net_profit_before_spread=str(target), next_five_minute_high_at_or_above_break_even=sum(r >= breakeven for r in observed), next_five_minute_high_at_or_above_target=sum(r >= target for r in observed), maximum_next_five_minute_high_return_among_signals=str(max(observed)) if observed else None, signals=signals, limitations=['No simulated or real orders; signal count is not trade count.', 'Future highs are diagnostic observations, not achievable fills.', 'Signal close is a reference, not the actual delayed ask entry price.', 'No historical bid-ask depth, spread, entry delay or exit path model.', 'A short historical window cannot establish profitable expectancy.'])
    print('HISTORY_JSON ' + json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
