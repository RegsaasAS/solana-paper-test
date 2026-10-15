"""Bounded public candidate screen. No ledger, order or signing calls."""
import datetime as dt
import json
import time
from decimal import Decimal as D
import dip_paper as dip
import safe_quote_gate as gate

SCREEN_RULES=dict(maximum_runtime_seconds=240,maximum_candidates=6,minimum_pool_age_minutes=15,minimum_liquidity_usd=100000,minimum_reported_15m_trades=20,minimum_reported_15m_buys=3,minimum_reported_15m_sells=3,minimum_reported_15m_volume_usd=2000,minimum_real_closed_minutes_per16=8,confirmation_delay_seconds=60,gecko_spacing_seconds=8,reference_input_lamports=50000000,maximum_immediate_modeled_loss_fraction='0.02',network_assumption_lamports_per_side=50000,first_account_assumption_lamports=3000000)
_last_gecko=0

def pause_gecko():
    global _last_gecko
    wait=8-(time.monotonic()-_last_gecko)
    if wait>0:time.sleep(wait)
    _last_gecko=time.monotonic()

def candles(coin):
    pause_gecko();rows=dip.fetch_candles(coin);now=int(time.time())
    d=dip.inspect(rows,now);d['observed_utc']=dip.utc()
    d['data_passed']=d['reason'] in ('conditions_not_met','closed_bar_dip_rebound')
    return d

def cost(coin):
    b=gate.quote(gate.SOL,coin['mint'],50000000)
    s=gate.quote(coin['mint'],gate.SOL,int(b['quote']['otherAmountThreshold']))
    spent=50050000;out=int(s['quote']['otherAmountThreshold'])-50000
    return dict(buy_quote=b,sell_quote=s,network_included_trade_loss_fraction=str(1-D(out)/D(spent)),cost_passed=out*10000>=spent*9800,modeled_trade_input_lamports=spent,modeled_immediate_proceeds_lamports=out,first_account_assumption_excluded_from_cost_gate_lamports=3000000,initial_roundtrip_with_account_change_lamports=out-spent-3000000,buy_route_uses_signal_pool=any(v.get('poolId')==coin['pool'] for v in b['quote']['routePlan']),sell_route_uses_signal_pool=any(v.get('poolId')==coin['pool'] for v in s['quote']['routePlan']))

def main():
    began=time.monotonic();deadline=began+240;available={};tested=[];errors=[];selected=None
    print('ACTIVE_SCREEN_RULES '+json.dumps(SCREEN_RULES),flush=True)
    for page in (1,2):
        try:
            pause_gecko();p=gate.read_public('https://api.geckoterminal.com/api/v2/networks/solana/trending_pools?duration=1h&page='+str(page))
            for pool in p.get('data',[]):
                a=pool['attributes'];rel=pool['relationships']
                mint=rel['base_token']['data']['id'].split('_',1)[1];quote=rel['quote_token']['data']['id'].split('_',1)[1]
                created=dt.datetime.fromisoformat(a['pool_created_at'].replace('Z','+00:00')).timestamp()
                age=(time.time()-created)/60
                trades=a.get('transactions',{}).get('m15',{});buys=int(trades.get('buys',0));sells=int(trades.get('sells',0))
                liquidity=D(str(a.get('reserve_in_usd') or 0));volume=D(str(a.get('volume_usd',{}).get('m15') or 0))
                symbol=a.get('name','').split(' / ')[0].upper()
                if quote!=gate.SOL or mint==gate.SOL or not gate.MINT.fullmatch(mint) or not gate.MINT.fullmatch(a['address']) or symbol in ('USDC','USDT','WSOL','SOL'):continue
                if age<15 or liquidity<100000 or buys<3 or sells<3 or buys+sells<20 or volume<2000:continue
                # Keep pool identity: the largest pool per token need not be the most active.
                available[a['address']]=dict(mint=mint,pool=a['address'],name=a['name'],liquidity_usd=str(liquidity),reported_15m_volume_usd=str(volume),reported_15m_buys=buys,reported_15m_sells=sells,pool_age_minutes=round(age,2))
        except Exception as exc:errors.append(dict(stage='discovery',page=page,error=str(exc)))
    cohort=sorted(available.values(),key=lambda c:(-(c['reported_15m_buys']+c['reported_15m_sells']),-D(c['reported_15m_volume_usd']),c['pool']))[:6]
    print('ACTIVE_SCREEN_COHORT '+json.dumps(cohort),flush=True)
    for coin in cohort:
        if time.monotonic()+40>deadline:break
        row=dict(candidate=coin,passed=False)
        try:
            row['initial_candles']=candles(coin)
            if row['initial_candles']['data_passed']:
                row['mint_checks']=gate.confirmed_standard_mint(coin['mint'])
                row['initial_cost']=cost(coin)
                if row['initial_cost']['cost_passed']:
                    if time.monotonic()+105>deadline:
                        row['blocked']='insufficient_time_for_independent_confirmation'
                    else:
                        time.sleep(60)
                        row['confirmation_candles']=candles(coin)
                        if row['confirmation_candles']['data_passed']:
                            row['confirmation_mint_checks']=gate.confirmed_standard_mint(coin['mint'])
                            row['confirmation_cost']=cost(coin)
                            row['passed']=row['confirmation_cost']['cost_passed']
                            if row['passed']:selected=coin
        except Exception as exc:row['error']=str(exc)
        tested.append(row);print('ACTIVE_SCREEN_CANDIDATE '+json.dumps(row),flush=True)
        if selected:break
    result=dict(status='candidate_found' if selected else 'no_candidate_verified',rules=SCREEN_RULES,cohort=cohort,tested=tested,selected=selected,errors=errors,elapsed_seconds=round(time.monotonic()-began,3),paper_trades=0,real_trades=0,credentials_used=False,limitations=['Selection uses reported activity, not returns.','Only a bounded trending-pool sample; not the whole Solana market.','Authority and extension checks are limited; not a security or liquidity audit.','Volume and positive-volume bars do not prove organic activity.','Two short observations do not establish continuous coverage.','Quotes are modeled outputs, not fills; hypothetical buys do not change pool state.','The 2% cost gate excludes the 0.003 SOL assumed first account cost, which is separately reported.','Router may use other pools than the signal pool; route identity is reported.','No strategy profitability or permanent operation tested.','Token category and any connection to the X author are not established.'])
    print('ACTIVE_SCREEN_RESULT_JSON '+json.dumps(result),flush=True)
if __name__=='__main__':main()
