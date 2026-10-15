"""Forward-only sampled-quote hypothesis. No historical OHLCV or trading volume claims."""
import json
import sys
import time
from decimal import Decimal as D
from pathlib import Path
import fresh_paper_window as source
import dip_paper as dip

C=source.COIN
RULES=dict(runtime_seconds=2700,price_poll_seconds=10,minimum_samples_per_closed_minute=4,maximum_sample_gap_seconds=22,closed_minutes_required=16,entry_delay_seconds=10,signal_expiry_seconds=60,entry_cutoff_seconds=330,maximum_roundtrips=2,maximum_hold_seconds=300,net_take_profit_fraction='0.02',net_stop_loss_fraction='-0.03',maximum_immediate_cost_fraction='0.02',entry_lamports=50000000,initial_lamports=1000000000,network_assumed_per_side_lamports=50000,setup_network_assumed_lamports=50000,buy_output_haircut_fraction='0.005',sell_output_tolerance_percent='0.5',dip_fraction='0.02',rebound_fraction='0.005',last_bar_rise_fraction='0.001',session_observed_loss_lamports=50000000,consecutive_data_error_stop=3)
LIMITATIONS=['Own forward sampled-price hypothesis, not a verified copy of X or the earlier OHLCV strategy.','Price is 0.05 SOL divided by SDK expected buy output; AMM fee/impact changes can affect the series.','Minute OHLC represents our sampled indicative prices, not executed market trades. Sample counts are not trading volume.','Historical volume filter deliberately absent; no invented volume or historical warmup.','Both sides use adverse output bounds; hypothetical buys do not change the real pool.','AMM fees embedded. Network/setup fees are assumptions; token-account minimum deposit is a recoverable modeled asset, not actual payment or refund.','No transaction building/simulation/signing/sending. Fills, liquidity execution, holder control and LP locking remain unverified.','Short paper experiment cannot establish profitability or permanent operation.']


def validate_snapshot(s,previous):
    if s['pool']!=C['pool'] or s['mint']!=C['mint']:raise ValueError('Identity mismatch')
    if previous is not None and int(s['slot'])<=previous:raise ValueError('Chain context slot did not advance')
    if int(s['buy']['base'])<=0:raise ValueError('Nonpositive indicative output')


def sell_from_snapshot(s,quantity):
    if int(s['sell_quantity_atoms'])!=quantity:raise ValueError('Wrong liquidation quantity')
    return dict(received_utc=s['observed_utc'],snapshot=s,quote=dict(inputMint=C['mint'],outputMint=dip.gate.SOL,inputAmount=quantity,outputAmount=int(s['sell']['uiQuote']),otherAmountThreshold=int(s['sell']['minQuote']),routePlan=[dict(poolId=C['pool'])]))


def immediate_cost_passes(s):
    return (int(s['sell']['minQuote'])-50000)*10000>=50050000*9800


def signal(bars,now):
    closed=[b for b in bars if b['time']+60<=now]
    if len(closed)<16:return dict(eligible=False,reason='forward_warmup',closed_minutes=len(closed))
    b=closed[-16:];stamp=b[-1]['time']
    if now-stamp-60>90:return dict(eligible=False,reason='stale_sampled_bar',bar_time=stamp)
    if [x['time'] for x in b]!=list(range(stamp-900,stamp+60,60)):return dict(eligible=False,reason='sampled_bar_gap',bar_time=stamp)
    if any(x['samples']<4 or x['max_gap']>22 for x in b):return dict(eligible=False,reason='insufficient_samples',bar_time=stamp)
    old,last=b[:-1],b[-1];peak=max(D(x['high']) for x in old);pi=next(i for i,x in enumerate(old) if D(x['high'])==peak)
    bottom=min(D(x['close']) for x in old[-3:]);bi=12+next(i for i,x in enumerate(old[-3:]) if D(x['close'])==bottom)
    close=D(last['close']);drop=1-close/peak;rebound=close/bottom-1;rise=close/D(last['open'])-1
    good=pi<bi and drop>=D('0.02') and rebound>=D('0.005') and rise>=D('0.001')
    return dict(eligible=good,reason='sampled_price_dip_rebound' if good else 'conditions_not_met',bar_time=stamp,drop_fraction=str(drop),rebound_fraction=str(rebound),last_bar_rise_fraction=str(rise))


def preflight():
    checks=[];previous=None
    for i in range(2):
        q=source.quote(dip.gate.SOL,C['mint'],50000000);s=q['snapshot'];validate_snapshot(s,previous);previous=int(s['slot'])
        checks.append(dict(observed_utc=s['observed_utc'],slot=s['slot'],pool=s['pool'],mint=s['mint'],stressed_loss_fraction=str(1-D(int(s['sell']['minQuote'])-50000)/D(50050000)),cost_passed=immediate_cost_passes(s)))
        if not checks[-1]['cost_passed']:raise ValueError('Unchanged cost ceiling exceeded')
        if i==0:time.sleep(10)
    print('CHAIN_PREFLIGHT_JSON '+json.dumps(dict(status='passed',checks=checks,real_trades=0,paper_trades=0)),flush=True)


def main():
    dip.RULES=dict(dip.RULES,first_token_account_cost_assumed_lamports=50000)
    book=source.StreamLedger();began=time.monotonic();deadline=began+2700;previous=None;bars=[];current=None;decisions=[];samples=[];errors=[];last_quote=None;pending=None;cooldown=began;bad=0;status='running';last_signal=None;next_poll=began
    def save():
        r=book.summary(status,last_quote)
        r.update(purpose='forward_sampled_chain_quote_paper_hypothesis',rules=RULES,coin=C,samples=samples,closed_sampled_bars=bars,decisions=decisions,eligible_signals=sum(x['eligible'] for x in decisions),quote_count=len(samples),errors=errors,elapsed_seconds=time.monotonic()-began,real_trades=0,credentials_used=False,limitations=LIMITATIONS,last_valid_quote_utc=last_quote.get('received_utc') if last_quote else None)
        Path('chain-paper-result.json').write_text(json.dumps(r,indent=2));return r
    print('CHAIN_PAPER_RULES '+json.dumps(dict(rules=RULES,coin=C,limitations=LIMITATIONS)),flush=True)
    try:
        while time.monotonic()<deadline or book.position:
            if time.monotonic()>deadline+30:status='unresolved_position';break
            wait=next_poll-time.monotonic()
            if wait>0:time.sleep(min(wait,10))
            if time.monotonic()<next_poll:continue
            next_poll=time.monotonic()+10
            try:
                holding=book.position is not None
                q=source.quote(C['mint'],dip.gate.SOL,book.position['quantity_atoms']) if holding else source.quote(dip.gate.SOL,C['mint'],50000000)
                s=q['snapshot'];validate_snapshot(s,previous);previous=int(s['slot']);bad=0
                now=time.monotonic();wall=time.time();stamp=int(wall)//60*60;price=D(50000000)/D(s['buy']['base'])
                observation=dict(observed_utc=s['observed_utc'],slot=s['slot'],indicative_lamports_per_token_atom=str(price),holding=holding)
                samples.append(observation);print('CHAIN_PRICE_SAMPLE '+json.dumps(observation),flush=True)
                if current is not None and current['time']!=stamp:
                    bars.append({k:v for k,v in current.items() if k!='last_sample_at'})
                    print('SAMPLED_PRICE_BAR '+json.dumps(bars[-1]),flush=True);current=None
                if current is None:current=dict(time=stamp,open=str(price),high=str(price),low=str(price),close=str(price),samples=0,max_gap=0,last_sample_at=wall)
                current.update(high=str(max(D(current['high']),price)),low=str(min(D(current['low']),price)),close=str(price),samples=current['samples']+1,max_gap=max(current['max_gap'],wall-current['last_sample_at']),last_sample_at=wall)
                if holding:
                    last_quote=q;reason=book.exit_reason(q,now,force=now>=deadline)
                    if reason:
                        book.close(q,reason);last_quote=None;pending=None;cooldown=now+60
                        print('CHAIN_PAPER_EVENT '+json.dumps(book.events[-1]),flush=True)
                elif pending is not None:
                    if now>pending['expires'] or now+330>=deadline:pending=None
                    elif now>=pending['ready']:
                        sell=sell_from_snapshot(s,int(q['quote']['otherAmountThreshold']))
                        if book.enter(C,q,sell,now):
                            book.events[-1]['signal']=pending['signal'];last_quote=sell
                            print('CHAIN_PAPER_EVENT '+json.dumps(book.events[-1]),flush=True)
                        else:decisions.append(dict(eligible=False,reason='entry_cost_or_budget_rejection',observed_utc=dip.utc()))
                        pending=None
                elif now>=cooldown and now+330<deadline:
                    d=signal(bars,wall)
                    if d.get('bar_time')!=last_signal and d.get('bar_time') is not None:
                        last_signal=d['bar_time'];d['observed_utc']=dip.utc();decisions.append(d)
                        print('CHAIN_SIGNAL '+json.dumps(d),flush=True)
                        if d['eligible']:pending=dict(ready=now+10,expires=now+60,signal=d)
                if book.closed>=2 or (book.position is None and book.cash+book.rent_deposit<=950000000):status='risk_limit_stop';break
            except Exception as exc:
                bad+=1;errors.append(dict(utc=dip.utc(),error=str(exc)));print('CHAIN_DATA_ERROR '+json.dumps(errors[-1]),flush=True)
                if bad>=3:
                    status='data_failure'
                    if book.position:
                        try:
                            q=source.quote(C['mint'],dip.gate.SOL,book.position['quantity_atoms']);book.close(q,'data_failure_exit');last_quote=None
                        except Exception as e:errors.append(dict(stage='forced_exit',error=str(e)));status='unresolved_position'
                    break
            save()
    except BaseException:
        status='interrupted' if book.position is None else 'unresolved_position'
        raise
    finally:
        if status=='running':status='completed' if book.position is None else 'unresolved_position'
        print('CHAIN_PAPER_RESULT_JSON '+json.dumps(save()),flush=True)
if __name__=='__main__':
    if '--preflight' in sys.argv:preflight()
    else:main()
