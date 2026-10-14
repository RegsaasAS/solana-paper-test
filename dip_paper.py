"""Predeclared dip/rebound forward screen. Integer paper ledger, public data only."""
import datetime as dt
import json
import pathlib
import time
from decimal import Decimal as D
import safe_quote_gate as gate

RULES=dict(runtime_seconds=900,initial_virtual_sol='1',entry_amount_sol='0.05',dip_fraction='0.02',rebound_fraction='0.005',last_bar_rise_fraction='0.001',lookback_minutes=15,entry_delay_seconds=10,signal_expiry_seconds=60,net_take_profit_fraction='0.02',net_stop_loss_fraction='-0.03',maximum_hold_seconds=300,cooldown_seconds=60,maximum_roundtrips=2,session_loss_limit_sol='0.05',maximum_immediate_quote_loss_fraction='0.02',network_cost_assumed_lamports_per_side=50000,first_token_account_cost_assumed_lamports=3000000,candle_poll_seconds=45,quote_poll_seconds=10)
COHORT=[{'name':'Fartcoin','mint':'9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump','pool':'Bzc9NZfMqkXR6fz1DBph7BDf9BroyEf6pnzESP7v5iiw'},{'name':'WIF','mint':'EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm','pool':'EP2ib6dYdEeqD8MfE2ezHCxX3kP3K2eLKkirfPm5eyMx'}]


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def inspect(rows,now):
    if any(len(r)!=6 or not all(D(str(v)).is_finite() for v in r) or min(D(str(v)) for v in r[1:5])<=0 or D(str(r[5]))<0 for r in rows):
        raise ValueError('Invalid candle data')
    closed=sorted([r for r in rows if int(r[0])+60<=now],key=lambda r:int(r[0]))
    if len(closed)<16:
        return dict(eligible=False,reason='insufficient_closed_bars',bar_time=None)
    bars=closed[-16:];stamp=int(bars[-1][0])
    if now-stamp-60>90:
        return dict(eligible=False,reason='stale_bar',bar_time=stamp)
    if [int(r[0]) for r in bars]!=list(range(stamp-900,stamp+60,60)):
        return dict(eligible=False,reason='bar_gap',bar_time=stamp)
    previous,current=bars[:-1],bars[-1]
    peak=max(D(str(r[2])) for r in previous)
    peak_at=next(i for i,r in enumerate(previous) if D(str(r[2]))==peak)
    bottom=min(D(str(r[4])) for r in previous[-3:])
    bottom_at=12+next(i for i,r in enumerate(previous[-3:]) if D(str(r[4]))==bottom)
    opening,close,volume=D(str(current[1])),D(str(current[4])),D(str(current[5]))
    if min(peak,bottom,opening,close)<=0:
        return dict(eligible=False,reason='invalid_bar',bar_time=stamp)
    drop=1-close/peak;rebound=close/bottom-1;rise=close/opening-1
    eligible=peak_at<bottom_at and drop>=D(RULES['dip_fraction']) and rebound>=D(RULES['rebound_fraction']) and rise>=D(RULES['last_bar_rise_fraction']) and volume>0
    return dict(eligible=eligible,reason='closed_bar_dip_rebound' if eligible else 'conditions_not_met',bar_time=stamp,drop_fraction=str(drop),rebound_fraction=str(rebound),last_bar_rise_fraction=str(rise),closed_bars=bars)


class Ledger:
    def __init__(self):
        self.cash=1000000000;self.position=None;self.events=[];self.accounts=set();self.closed=0
    def record(self,side,delta,**fields):
        self.cash+=delta
        self.events.append(dict(utc=utc(),side=side,cash_change_lamports=delta,**fields))
    def enter(self,coin,buy,sell,now):
        if self.position:
            raise ValueError('One position only')
        qty=int(buy['quote']['otherAmountThreshold'])
        if qty<=0 or buy['quote']['inputMint']!=gate.SOL or buy['quote']['outputMint']!=coin['mint'] or int(buy['quote']['inputAmount'])!=gate.AMOUNT_LAMPORTS or sell['quote']['inputMint']!=coin['mint'] or sell['quote']['outputMint']!=gate.SOL or int(sell['quote']['inputAmount'])!=qty:
            raise ValueError('Entry quotes mismatched')
        spent=gate.AMOUNT_LAMPORTS+RULES['network_cost_assumed_lamports_per_side']
        proceeds=int(sell['quote']['otherAmountThreshold'])-RULES['network_cost_assumed_lamports_per_side']
        if proceeds*10000<spent*9800:
            return False
        setup=0 if coin['mint'] in self.accounts else RULES['first_token_account_cost_assumed_lamports']
        if self.cash<spent+setup:
            return False
        if setup:
            self.record('ACCOUNT_SETUP_MODEL_COST',-setup,mint=coin['mint'],assumed=True,refunded=False)
            self.accounts.add(coin['mint'])
        self.record('BUY',-spent,mint=coin['mint'],quantity_atoms=qty,quote=buy)
        self.position=dict(coin=coin,quantity_atoms=qty,spent_lamports=spent,entry_at=now,entry_utc=utc())
        return True
    def mark(self,q):
        if q['quote']['outputMint']!=gate.SOL or q['quote']['inputMint']!=self.position['coin']['mint'] or int(q['quote']['inputAmount'])!=self.position['quantity_atoms']:
            raise ValueError('Liquidation quote mismatched')
        return int(q['quote']['otherAmountThreshold'])-RULES['network_cost_assumed_lamports_per_side']
    def exit_reason(self,q,now,force=False):
        mark=self.mark(q);r=D(mark)/D(self.position['spent_lamports'])-1
        if force:return 'session_end'
        if r>=D(RULES['net_take_profit_fraction']):return 'net_take_profit'
        if r<=D(RULES['net_stop_loss_fraction']):return 'net_stop_loss'
        if now-self.position['entry_at']>=RULES['maximum_hold_seconds']:return 'five_minute_exit'
        return None
    def close(self,q,reason):
        p=self.position;proceeds=self.mark(q)
        self.record('SELL',proceeds,mint=p['coin']['mint'],quantity_atoms=p['quantity_atoms'],net_trade_pnl_lamports=proceeds-p['spent_lamports'],reason=reason,quote=q)
        self.position=None;self.closed+=1
    def summary(self,status,last_quote=None):
        mark=self.mark(last_quote) if self.position and last_quote else None
        equity=self.cash+(mark or 0) if self.position is None or mark is not None else None
        expected=1000000000+sum(e['cash_change_lamports'] for e in self.events)
        if expected!=self.cash:raise AssertionError('Paper ledger inconsistent')
        return dict(status=status,initial_cash_lamports=1000000000,cash_lamports=self.cash,position=self.position,events=self.events,completed_roundtrips=self.closed,account_setup_model_cost_lamports=sum(-e['cash_change_lamports'] for e in self.events if e['side']=='ACCOUNT_SETUP_MODEL_COST'),equity_at_last_valid_quote_lamports=equity,full_portfolio_net_pnl_lamports=equity-1000000000 if equity is not None else None,accounting_verified=True)


def main():
    began=time.monotonic();deadline=began+RULES['runtime_seconds'];book=Ledger()
    errors=[];decisions=[];quote_count=0;seen={};pending=None;cooldown=began;next_candles=began;last_quote=None;status='running';active=[];consecutive=0
    def quoted(a,b,n):
        nonlocal quote_count
        q=gate.quote(a,b,n);quote_count+=1;return q
    def save():
        result=book.summary(status,last_quote)
        result.update(purpose='predeclared_forward_dip_rebound_paper_screen_not_verified_performance',rules=RULES,cohort=COHORT,active_cohort=active,decisions=decisions,eligible_signals=sum(d.get('eligible',False) for d in decisions),quote_count=quote_count,errors=errors,elapsed_seconds=round(time.monotonic()-began,3),updated_utc=utc(),adequate_sample=False,real_trades=0,credentials_used=False,limitations=['Older liquid Solana tokens, not original newly launched coin selection.','Fixed new hypothesis, not a replicated or validated author strategy.','PnL is in SOL relative to holding SOL, not a dollar return.','Quotes and minimum outputs are modeled fills; no orders, signatures or guaranteed execution.','Quoted AMM fees are embedded; network and one-time account costs are assumptions, not actual measured charges.','Account setup modeled at 0.003 SOL per token, not refunded, included in full portfolio result.','Initial cost guard is per trade and excludes one-time account setup; portfolio accounting includes it.','Hypothetical buys do not change real pool state.','Last-valid quote equity can be stale after a data failure.','Stops are sampled decisions, not guaranteed loss limits.','Mint checks do not verify owner concentration, liquidity locks or general token safety.','Short bounded test cannot establish profitability or permanent operation.'])
        pathlib.Path('dip-paper-result.json').write_text(json.dumps(result,indent=2))
        return result
    print('DIP_RULES '+json.dumps(RULES),flush=True)
    for coin in COHORT:
        try:
            gate.confirmed_standard_mint(coin['mint'])
            buy=quoted(gate.SOL,coin['mint'],gate.AMOUNT_LAMPORTS)
            sell=quoted(coin['mint'],gate.SOL,int(buy['quote']['otherAmountThreshold']))
            spent=gate.AMOUNT_LAMPORTS+50000;out=int(sell['quote']['otherAmountThreshold'])-50000
            if out*10000>=spent*9800:active.append(coin)
            else:decisions.append(dict(mint=coin['mint'],eligible=False,reason='preflight_cost_rejection'))
        except Exception as exc:
            errors.append(dict(stage='preflight',mint=coin['mint'],error=str(exc)))
    if not active:status='blocked_preflight'
    save()
    while active and status=='running' and (time.monotonic()<deadline or book.position):
        now=time.monotonic()
        if now>deadline+30:
            status='unresolved_position';break
        try:
            if book.position:
                last_quote=quoted(book.position['coin']['mint'],gate.SOL,book.position['quantity_atoms'])
                reason=book.exit_reason(last_quote,time.monotonic(),force=time.monotonic()>=deadline)
                if reason:
                    book.close(last_quote,reason);last_quote=None;pending=None;cooldown=time.monotonic()+60
                    print('PAPER_EVENT '+json.dumps(book.events[-1]),flush=True)
                consecutive=0
            elif pending:
                if now>pending['expires'] or now+330>=deadline:pending=None
                elif now>=pending['ready']:
                    coin=pending['coin'];signal=pending['signal'];pending=None
                    gate.confirmed_standard_mint(coin['mint'])
                    buy=quoted(gate.SOL,coin['mint'],gate.AMOUNT_LAMPORTS)
                    sell=quoted(coin['mint'],gate.SOL,int(buy['quote']['otherAmountThreshold']))
                    if book.enter(coin,buy,sell,time.monotonic()):
                        book.events[-1]['signal']=signal;last_quote=sell;print('PAPER_EVENT '+json.dumps(book.events[-1]),flush=True)
                    else:decisions.append(dict(mint=coin['mint'],eligible=False,reason='entry_cost_or_budget_rejection'))
                    consecutive=0
            elif now>=next_candles and now<deadline:
                for coin in active:
                    p=gate.read_public('https://api.geckoterminal.com/api/v2/networks/solana/pools/'+coin['pool']+'/ohlcv/minute?aggregate=1&limit=30&currency=token&token=base')
                    if p.get('meta',{}).get('base',{}).get('address')!=coin['mint'] or p.get('meta',{}).get('quote',{}).get('address')!=gate.SOL:
                        raise ValueError('Candle token identity mismatch')
                    d=inspect(p['data']['attributes']['ohlcv_list'],int(time.time()));d['mint']=coin['mint'];d['observed_utc']=utc()
                    if d['bar_time'] is not None and seen.get(coin['mint'])!=d['bar_time']:
                        seen[coin['mint']]=d['bar_time'];decisions.append(d);print('DIP_SIGNAL '+json.dumps(d),flush=True)
                        if d['eligible'] and time.monotonic()>=cooldown and time.monotonic()+330<deadline:
                            pending=dict(coin=coin,ready=time.monotonic()+10,expires=time.monotonic()+60,signal=d);break
                    time.sleep(7)
                next_candles=time.monotonic()+45;consecutive=0
            if book.closed>=2 or (book.position is None and book.cash<=950000000):
                status='risk_limit_stop';break
        except Exception as exc:
            errors.append(dict(utc=utc(),error=str(exc)));consecutive+=1
            if consecutive>=3:
                status='data_failure'
                if book.position:
                    try:
                        q=quoted(book.position['coin']['mint'],gate.SOL,book.position['quantity_atoms']);book.close(q,'data_failure_exit');last_quote=None
                    except Exception as exit_exc:
                        errors.append(dict(stage='forced_exit',error=str(exit_exc)));status='unresolved_position'
                break
        save();time.sleep(10)
    if status=='running':status='completed' if book.position is None else 'unresolved_position'
    print('DIP_RESULT_JSON '+json.dumps(save()),flush=True)


if __name__=='__main__':
    main()
