"""One fixed, predeclared SOL/USDT momentum hypothesis; paper execution only."""
import argparse
import datetime as dt
import decimal
import json
import pathlib
import time

from probe import D, execute_book, public, utc

RULES = {
    "lookback_closed_minutes": 5,
    "minimum_signal_candle_return": "0.003",
    "minimum_volume_multiple": "1.5",
    "maximum_spread_fraction": "0.001",
    "fee_per_side": "0.008",
    "adverse_slippage_per_side": "0.001",
    "entry_delay_seconds": 10,
    "signal_expiry_seconds": 90,
    "maximum_hold_seconds": 300,
    "net_take_profit": "0.01",
    "net_stop_loss": "-0.025",
    "session_loss_limit_usdt": "5",
    "maximum_roundtrips": 12,
    "virtual_cash_usdt": "100",
    "maximum_entry_cost_usdt": "10",
    "cooldown_seconds": 60,
}


def inspect_signal(rows, server_time):
    # Kraken documents the final row as unfinished even when its timestamp
    # looks old. Never use that row, nor a future/unfinished preceding row.
    completed = [r for r in rows[:-1] if int(r[0]) + 60 <= server_time]
    if len(completed) < 6:
        return {"eligible": False, "reason": "insufficient_closed_candles", "bar_time": None}
    previous, current = completed[-6:-1], completed[-1]
    stamp = int(current[0])
    if server_time - (stamp + 60) > 90:
        return {"eligible": False, "reason": "stale_candle", "bar_time": stamp}
    if [int(r[0]) for r in previous + [current]] != list(range(stamp - 300, stamp + 60, 60)):
        return {"eligible": False, "reason": "candle_gap", "bar_time": stamp}
    opening, close = D(current[1]), D(current[4])
    high = max(D(r[2]) for r in previous)
    average_volume = sum((D(r[6]) for r in previous), D(0)) / 5
    volume = D(current[6])
    if opening <= 0 or average_volume <= 0:
        return {"eligible": False, "reason": "invalid_price_or_no_volume", "bar_time": stamp}
    change, multiple = close / opening - 1, volume / average_volume
    eligible = close > high and change >= D(RULES["minimum_signal_candle_return"]) and multiple >= D(RULES["minimum_volume_multiple"])
    return {
        "eligible": eligible,
        "reason": "confirmed_breakout_volume_momentum" if eligible else "entry_conditions_not_met",
        "bar_time": stamp, "bar_closed_at": stamp + 60,
        "signal_close": str(close), "previous_five_bar_high": str(high),
        "candle_return": str(change), "volume_multiple": str(multiple),
    }


class PaperEngine:
    def __init__(self, metadata, started, deadline):
        self.metadata, self.started, self.deadline = metadata, started, deadline
        self.cash = D(RULES["virtual_cash_usdt"])
        self.position = None
        self.pending = None
        self.cooldown_until = started
        self.last_bar = None
        self.closed = 0
        self.trades = []
        self.decisions = []
        self.fee = D(RULES["fee_per_side"])
        self.slip = D(RULES["adverse_slippage_per_side"])
        self.quantum = D(1).scaleb(-int(metadata["lot_decimals"]))

    def allow_entry(self, now):
        return self.position is None and now >= self.cooldown_until and now + RULES["maximum_hold_seconds"] + 30 < self.deadline and self.cash > D(RULES["virtual_cash_usdt"]) - D(RULES["session_loss_limit_usdt"]) and self.closed < RULES["maximum_roundtrips"]

    def observe(self, decision, now):
        if decision["bar_time"] is None or decision["bar_time"] == self.last_bar:
            return
        self.last_bar = decision["bar_time"]
        recorded = dict(decision, observed_utc=utc(), entry_allowed=self.allow_entry(now))
        self.decisions.append(recorded)
        if decision["eligible"] and self.allow_entry(now):
            self.pending = dict(decision, ready_at=now + RULES["entry_delay_seconds"], expires_at=now + RULES["signal_expiry_seconds"])

    def liquidation(self, book):
        gross = execute_book(book["bids"], D(self.position["quantity_sol"]))
        modeled = gross * (1 - self.slip)
        return gross, modeled, modeled * self.fee, modeled * (1 - self.fee)

    def tick(self, book, now, force_exit=False):
        ask, bid = D(book["asks"][0][0]), D(book["bids"][0][0])
        if not (ask > 0 and bid > 0 and bid <= ask):
            raise ValueError("Invalid or crossed book")
        if self.position:
            gross, modeled, fee, proceeds = self.liquidation(book)
            spent = D(self.position["spent_usdt"])
            net_return = proceeds / spent - 1
            reason = None
            if force_exit:
                reason = "session_end"
            elif net_return >= D(RULES["net_take_profit"]):
                reason = "net_take_profit"
            elif net_return <= D(RULES["net_stop_loss"]):
                reason = "net_stop_loss"
            elif now - self.position["entry_at"] >= RULES["maximum_hold_seconds"]:
                reason = "five_minute_time_exit"
            if reason:
                row = dict(utc=utc(), side="SELL", quantity_sol=self.position["quantity_sol"], book_gross_usdt=str(gross), modeled_gross_usdt=str(modeled), fee_usdt=str(fee), cash_change_usdt=str(proceeds), reason=reason, net_return=str(net_return), net_pnl_usdt=str(proceeds-spent))
                self.cash += proceeds
                self.trades.append(row)
                self.closed += 1
                self.position, self.pending = None, None
                self.cooldown_until = now + RULES["cooldown_seconds"]
                return row
        elif self.pending:
            pending = self.pending
            if now > pending["expires_at"] or not self.allow_entry(now) or force_exit:
                self.pending = None
            elif now >= pending["ready_at"]:
                self.pending = None
                if (ask-bid)/ask > D(RULES["maximum_spread_fraction"]):
                    self.decisions.append(dict(bar_time=pending["bar_time"], eligible=False, reason="entry_spread_too_wide", observed_utc=utc()))
                    return None
                # Cancel the trade if the quote has fallen below the breakout.
                if bid <= D(pending["previous_five_bar_high"]):
                    self.decisions.append(dict(bar_time=pending["bar_time"], eligible=False, reason="breakout_lost_before_entry", observed_utc=utc()))
                    return None
                budget = min(D(RULES["maximum_entry_cost_usdt"]), self.cash)
                qty = (budget/(ask*(1+self.slip)*(1+self.fee))).quantize(self.quantum, rounding=decimal.ROUND_DOWN)
                # Reduce size when deeper book prices would exceed the budget.
                for _ in range(4):
                    gross = execute_book(book["asks"], qty)
                    modeled = gross * (1+self.slip)
                    fee = modeled*self.fee
                    spent = modeled+fee
                    if spent <= budget:
                        break
                    qty = (qty*budget/spent).quantize(self.quantum, rounding=decimal.ROUND_DOWN)
                if spent > budget or qty < D(self.metadata["ordermin"]) or gross < D(self.metadata["costmin"]):
                    raise ValueError("Order size/budget/minimum check failed")
                row = dict(utc=utc(), side="BUY", quantity_sol=str(qty), book_gross_usdt=str(gross), modeled_gross_usdt=str(modeled), fee_usdt=str(fee), cash_change_usdt=str(-spent), reason="confirmed_breakout_volume_momentum", signal_bar_time=pending["bar_time"])
                self.cash -= spent
                self.position = dict(quantity_sol=str(qty), spent_usdt=str(spent), entry_at=now, entry_utc=row["utc"], signal_bar_time=pending["bar_time"])
                self.trades.append(row)
                return row
        return None

    def summary(self, status, quotes, errors, reference_first=None, reference_last=None):
        closed_pnl = sum((D(t["net_pnl_usdt"]) for t in self.trades if t["side"] == "SELL"), D(0))
        mark = None
        if self.position and reference_last:
            mark = self.liquidation(reference_last)[-1]
        equity = self.cash + (mark if mark is not None else D(0))
        baseline = None
        if reference_first and reference_last:
            ask = D(reference_first["asks"][0][0]);bid = D(reference_last["bids"][0][0])
            passive_qty = (D(RULES["maximum_entry_cost_usdt"])/(ask*(1+self.slip)*(1+self.fee))).quantize(self.quantum, rounding=decimal.ROUND_DOWN)
            try:
                bought = execute_book(reference_first["asks"], passive_qty)*(1+self.slip)*(1+self.fee)
                sold = execute_book(reference_last["bids"], passive_qty)*(1-self.slip)*(1-self.fee)
                baseline = str(sold-bought)
            except RuntimeError:
                pass  # A missing reference fill must not fabricate a benchmark.
        return dict(purpose="predeclared_forward_signal_screen_not_verified_performance", pair="SOL/USDT", status=status, rules=RULES, virtual_cash_initial_usdt="100", virtual_cash_usdt=str(self.cash), position=self.position, open_position_last_quote_value_usdt=str(mark) if mark is not None else None, completed_roundtrips=self.closed, eligible_signals=sum(d.get("eligible",False) for d in self.decisions), decisions=self.decisions, trades=self.trades, quote_count=quotes, errors=errors, realized_net_pnl_usdt=str(closed_pnl), equity_at_last_valid_quote_usdt=str(equity) if self.position is None or mark is not None else None, full_portfolio_net_pnl_usdt=str(equity-D("100")) if self.position is None or mark is not None else None, passive_buy_hold_net_pnl_usdt=baseline, passive_buy_hold_entry_budget_usdt=RULES["maximum_entry_cost_usdt"], adequate_sample=False, limitations=["one-hour screen cannot establish profitable expectancy", "fees use published base tier, not verified account rate", "visible book simulation, not guaranteed fills", "stop losses are sampled rules, not guaranteed prices", "reference equity uses last valid quote and may be stale after a data failure", "SOL/USDT on Kraken, not new Solana memecoins", "bounded software test, no permanent hosting"])


def run(seconds, output):
    out = pathlib.Path(output)
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    deadline = started+seconds
    metadata = public("AssetPairs?pair=SOLUSDT")["SOLUSDT"]
    if metadata["status"] != "online":
        raise RuntimeError("Market unavailable")
    engine = PaperEngine(metadata, started, deadline)
    errors = []
    consecutive_errors = quotes = 0
    next_candles = 0
    first_book = last_book = None
    status = "running"
    def save():
        value = engine.summary(status, quotes, errors, first_book, last_book)
        value.update(started_utc=dt.datetime.fromtimestamp(time.time()-(time.monotonic()-started),dt.timezone.utc).isoformat(), updated_utc=utc(), maximum_runtime_seconds=seconds)
        temp = out/'result.tmp'
        temp.write_text(json.dumps(value,indent=2),encoding='utf-8')
        temp.replace(out/'result.json')
        return value
    save()
    print(json.dumps(dict(event="started",rules=RULES,maximum_runtime_seconds=seconds)),flush=True)
    with (out/'observations.jsonl').open('w',encoding='utf-8') as log:
        while time.monotonic()<deadline or engine.position:
            loop_at = time.monotonic()
            if loop_at>deadline+120:
                status="data_failure_unresolved_position"
                break
            try:
                server = public('Time')
                server_time = int(server['unixtime'])
                if abs(time.time()-server_time)>30:
                    raise ValueError('Clock mismatch or stale server-time response')
                # Signals are read before fetching the execution book. A later
                # tick supplies the entry quote after the mandatory delay.
                if loop_at>=next_candles and loop_at<deadline:
                    rows = public('OHLC?pair=SOLUSDT&interval=1')['SOLUSDT']
                    decision = inspect_signal(rows,server_time)
                    decision['received_utc'] = utc()
                    log.write(json.dumps(dict(event='signal_check',decision=decision,raw_rows=rows[-8:]))+'\n')
                    print(json.dumps(dict(event='signal_check',decision=decision)),flush=True)
                    engine.observe(decision,time.monotonic())
                    next_candles = time.monotonic()+30
                book = public('Depth?pair=SOLUSDT&count=25')['SOLUSDT']
                row = engine.tick(book,time.monotonic(),force_exit=time.monotonic()>=deadline)
                first_book = first_book or book
                last_book = book
                quotes += 1
                log.write(json.dumps(dict(event='quote',received_utc=utc(),book=book))+'\n')
                if row:
                    print(json.dumps(dict(event='paper_trade',trade=row)),flush=True)
                log.flush()
                consecutive_errors = 0
                save()
                if engine.closed>=RULES['maximum_roundtrips'] or (engine.position is None and engine.cash<=D('95')):
                    status='risk_limit_stop'
                    break
            except Exception as exc:
                consecutive_errors += 1
                errors.append(dict(utc=utc(),error=str(exc)))
                print(json.dumps(dict(event='data_error',error=str(exc))),flush=True)
                if consecutive_errors>=3:
                    status='data_failure_unresolved_position' if engine.position else 'data_failure'
                    break
            if time.monotonic()>=deadline and engine.position is None:
                status='completed'
                break
            time.sleep(max(0,10-(time.monotonic()-loop_at)))
    if status=='running':
        status='completed' if engine.position is None else 'data_failure_unresolved_position'
    value = save()
    print('RESULT_JSON '+json.dumps(value),flush=True)
    return 0 if status in ('completed','risk_limit_stop') else 1


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--seconds',type=int,default=3600)
    p.add_argument('--output',default='signal-result')
    a=p.parse_args()
    if not 90<=a.seconds<=3600:
        p.error('Bounded screening test: 90-3600 seconds')
    raise SystemExit(run(a.seconds,a.output))
