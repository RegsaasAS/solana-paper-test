"""Bounded launch-focused research shortlist. No trades, signatures or browser access."""
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request
from decimal import Decimal as D
import dip_paper as dip
import safe_quote_gate as gate

RULES=dict(maximum_runtime_seconds=360,maximum_candidates=6,maximum_shortlist=3,minimum_pool_age_minutes=15,maximum_pool_age_minutes=4320,minimum_liquidity_usd=100000,minimum_reported_15m_trades=20,minimum_15m_buys=3,minimum_15m_sells=3,minimum_reported_15m_volume_usd=2000,minimum_holders_when_reported=80,minimum_real_closed_minutes_per16=8,gecko_spacing_seconds=8,input_lamports=50000000,assumed_network_lamports_per_side=50000,maximum_stressed_immediate_loss_fraction='0.02')
_last=0

def pause():
    global _last
    delay=8-(time.monotonic()-_last)
    if delay>0:time.sleep(delay)
    _last=time.monotonic()

def read_gecko(path,params=None):
    fixed=path in ('/networks/solana/new_pools','/networks/solana/trending_pools')
    token=bool(re.fullmatch(r'/networks/solana/tokens/[1-9A-HJ-NP-Za-km-z]{32,44}/(?:info|pools)',path))
    if not fixed and not token:raise ValueError('Not an approved public read path')
    pause();url='https://api.geckoterminal.com/api/v2'+path
    if params:url+='?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'PublicLaunchResearch/1.0'})
    with urllib.request.build_opener(gate.NoRedirect).open(req,timeout=8) as response:
        body=response.read(2_000_001)
        if len(body)>2_000_000:raise ValueError('Oversized response')
        return json.loads(body)

def age(created):return (time.time()-dt.datetime.fromisoformat(created.replace('Z','+00:00')).timestamp())/60

def discover(p,source):
    a=p['attributes'];rel=p['relationships'];mint=rel['base_token']['data']['id'].split('_',1)[1];quote=rel['quote_token']['data']['id'].split('_',1)[1]
    if quote!=gate.SOL or mint==gate.SOL or not gate.MINT.fullmatch(mint) or not gate.MINT.fullmatch(a['address']):return None
    minutes=age(a['pool_created_at']);liq=D(str(a.get('reserve_in_usd') or 0));vol=D(str(a.get('volume_usd',{}).get('m15') or 0))
    t=a.get('transactions',{}).get('m15',{});buys=int(t.get('buys',0));sells=int(t.get('sells',0))
    if not 15<=minutes<=4320 or liq<100000 or vol<2000 or buys<3 or sells<3 or buys+sells<20:return None
    return dict(name=a.get('name',''),mint=mint,pool=a['address'],pool_created_at=a['pool_created_at'],observed_pool_age_minutes=round(minutes,2),liquidity_usd=str(liq),reported_15m_volume_usd=str(vol),reported_15m_buys=buys,reported_15m_sells=sells,reported_market_cap_usd=a.get('market_cap_usd'),reported_fdv_usd=a.get('fdv_usd'),discovery_source=source)

def candles(coin):
    pause();rows=dip.fetch_candles(coin);now=int(time.time());d=dip.inspect(rows,now)
    d['observed_utc']=dip.utc();d['data_passed']=d['reason'] in ('conditions_not_met','closed_bar_dip_rebound')
    return d

def quote_check(coin):
    b=gate.quote(gate.SOL,coin['mint'],50000000);s=gate.quote(coin['mint'],gate.SOL,int(b['quote']['otherAmountThreshold']))
    input_cost=50050000;min_net=int(s['quote']['otherAmountThreshold'])-50000;quoted_net=int(s['quote']['outputAmount'])-50000
    return dict(buy=b,sell=s,stressed_same_quantity_roundtrip_loss_fraction=str(1-D(min_net)/D(input_cost)),sale_at_quote_same_quantity_loss_fraction=str(1-D(quoted_net)/D(input_cost)),cost_passed=min_net*10000>=input_cost*9800,signal_pool_used_in_both_quotes=all(any(p.get('poolId')==coin['pool'] for p in q['quote']['routePlan']) for q in (b,s)),account_setup_cost='unverified; not treated as a measured permanent expense',actual_fills_verified=False)

def main():
    began=time.monotonic();deadline=began+360;found={};errors=[];tested=[];shortlist=[];discovery_counts={}
    print('LAUNCH_RULES '+json.dumps(RULES),flush=True)
    for source,page in [('trending_pools',1),('trending_pools',2),('new_pools',1),('new_pools',5)]:
        label=source+':'+str(page)
        try:
            params={'page':page}
            if source=='trending_pools':params['duration']='1h'
            p=read_gecko('/networks/solana/'+source,params);discovery_counts[label]=len(p.get('data',[]))
            for pool in p.get('data',[]):
                try:
                    c=discover(pool,label)
                    if c:found[c['pool']]=c
                except Exception as exc:errors.append(dict(stage='candidate_parse',source=label,error=str(exc)))
        except Exception as exc:errors.append(dict(stage='discovery',source=label,error=str(exc)))
    ranked=sorted(found.values(),key=lambda c:(-(c['reported_15m_buys']+c['reported_15m_sells']),-D(c['reported_15m_volume_usd']),c['pool']))
    cohort=[];mints=set()
    for c in ranked:
        if c['mint'] not in mints:cohort.append(c);mints.add(c['mint'])
        if len(cohort)>=6:break
    print('LAUNCH_FROZEN_COHORT '+json.dumps(cohort),flush=True)
    for coin in cohort:
        if time.monotonic()+60>deadline:break
        row=dict(candidate=coin,shortlisted=False,unresolved=['Exact mint creation time is not verified.','Pool liquidity control/locks are not verified.','Social legitimacy, organic flow and actual fills are not verified.'])
        try:
            row['candles']=candles(coin)
            if row['candles']['data_passed']:
                row['mint_checks']=gate.confirmed_standard_mint(coin['mint'])
                info=read_gecko('/networks/solana/tokens/'+coin['mint']+'/info')['data']['attributes']
                if info.get('address')!=coin['mint']:raise ValueError('Token info identity mismatch')
                row['reported_metadata']={k:info.get(k) for k in ('holders','developer_holding_percentage','launchpad_details','gt_verified','gt_category_ids')}
                row['social_handle_present']=bool(info.get('twitter_handle'))
                pools=read_gecko('/networks/solana/tokens/'+coin['mint']+'/pools',{'page':1}).get('data',[])
                known=[]
                for p in pools:
                    ids=[v['data']['id'] for k,v in p['relationships'].items() if k in ('base_token','quote_token')]
                    if 'solana_'+coin['mint'] not in ids:raise ValueError('Other pool token mismatch')
                    known.append(dict(pool=p['attributes']['address'],age_minutes=round(age(p['attributes']['pool_created_at']),2)))
                row['known_pool_age_check']=dict(returned_pools=known,complete_history=False,known_older_pool=any(v['age_minutes']>4320 for v in known))
                launch=info.get('launchpad_details') or {};graduation_old=bool(launch.get('completed_at')) and age(launch['completed_at'])>4320
                row['known_old_launch']=graduation_old
                holders=info.get('holders') or {};distribution=holders.get('distribution_percentage') or {};top=distribution.get('top_10')
                row['reported_concentration_filter']=dict(provider_top10_percent=top,includes_all_account_types=True,passes_if_reported=top is None or D(str(top))<=60)
                holder_count=holders.get('count')
                row['reported_holder_count_filter']=holder_count is None or int(holder_count)>=80
                if top is None:row['unresolved'].append('Top-holder concentration unavailable.')
                if not holders.get('count'):row['unresolved'].append('Holder count unavailable.')
                if not row['known_pool_age_check']['known_older_pool'] and not graduation_old and row['reported_concentration_filter']['passes_if_reported'] and row['reported_holder_count_filter']:
                    row['quotes']=quote_check(coin)
                    row['shortlisted']=row['quotes']['cost_passed']
                    if not row['quotes']['signal_pool_used_in_both_quotes']:row['unresolved'].append('Quote route differs from signal pool; align before any strategy test.')
        except Exception as exc:row['error']=str(exc)
        tested.append(row);print('LAUNCH_CANDIDATE '+json.dumps(row),flush=True)
        if row['shortlisted']:shortlist.append(row)
        if len(shortlist)>=3:break
    result=dict(status='research_shortlist_found' if shortlist else 'no_candidate_verified_in_sample',rules=RULES,discovery_counts=discovery_counts,cohort=cohort,tested=tested,shortlist=shortlist,untested_count=len(cohort)-len(tested),errors=errors,elapsed_seconds=round(time.monotonic()-began,3),paper_trades=0,real_trades=0,credentials_used=False,limitations=['Watchlist only, not trade approval or a safety audit.','Pool age is verified from provider data; exact token creation age remains unresolved.','Other-pool and migration checks exclude known old tokens, but do not prove launch age.','Holder statistics are provider reports, may include vaults and may be stale.','Quoted slippage bounds are stressed assumptions, not measured execution.','No returns, future selection, AI prediction, transaction building or broadcasting.','Only a bounded public sample; not the whole market or a complete replication of the X guide.'])
    print('LAUNCH_SHORTLIST_RESULT_JSON '+json.dumps(result),flush=True)
if __name__=='__main__':main()
