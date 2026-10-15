"""Bounded fresh-data-first candidate screen; no performance-based ranking or orders."""
import json
import subprocess
import time
from decimal import Decimal as D
import launch_shortlist as scan
import dip_paper as dip
import safe_quote_gate as gate
from candle_duplicates import normalize

_last=0

def spaced(fn,*a,**kw):
    global _last
    wait=12-(time.monotonic()-_last)
    if wait>0:time.sleep(wait)
    _last=time.monotonic()
    return fn(*a,**kw)

def candles(c):
    raw=spaced(dip.fetch_candles,c,int(time.time())//60*60)
    rows,details=normalize(raw)
    if rows is None:raise ValueError('Conflicting duplicate minute rows')
    d=dip.inspect(rows,time.time());d['observed_utc']=dip.utc();d['duplicate_check']=details
    d['usable']=d['reason'] in ('conditions_not_met','closed_bar_dip_rebound')
    return d

def price(c):
    p=subprocess.run(['node','screen_pool_prices.cjs','buy',c['pool'],c['mint']],text=True,capture_output=True,timeout=35)
    if p.returncode:raise ValueError(p.stderr[-1200:])
    lines=[x for x in p.stdout.splitlines() if x.startswith('STREAM_SNAPSHOT_JSON ')]
    if len(lines)!=1:raise ValueError('Missing price snapshot')
    s=json.loads(lines[0].split(' ',1)[1])
    if s['mint']!=c['mint'] or s['pool']!=c['pool']:raise ValueError('Price identity mismatch')
    return s

def main():
    began=time.monotonic();deadline=began+420;found={};errors=[];rows=[];watch=[];chosen=None;counts={}
    rules=dict(maximum_candidates=8,maximum_runtime_seconds=420,minimum_pool_age_minutes=15,maximum_pool_age_minutes=4320,minimum_liquidity_usd=100000,two_fresh_windows_required=True,minimum_window_separation_seconds=65,adverse_output_fraction_each_side='0.005',maximum_immediate_cost_fraction='0.02',network_assumed_each_side_lamports=50000,ranking='reported activity; no returns',invalid_data_not_repaired_by_choosing_one_conflicting_row=True)
    print('VERIFIED_SCREEN_RULES '+json.dumps(rules),flush=True)
    for source,page in [('trending_pools',i) for i in (1,2,3,4)]+[('new_pools',5)]:
        try:
            params={'page':page}
            if source=='trending_pools':params['duration']='1h'
            p=spaced(scan.read_gecko,'/networks/solana/'+source,params);counts[source+':'+str(page)]=len(p.get('data',[]))
            for item in p.get('data',[]):
                c=scan.discover(item,source+':'+str(page))
                if c and c['mint']!='FRCVr13HAEfvzyzQUr31CVVidPJ7zj8swQYkTDDU6Ls':found[c['pool']]=c
        except Exception as exc:errors.append(dict(stage='discovery',source=source,page=page,error=str(exc)))
    cohort=[];seen=set()
    for c in sorted(found.values(),key=lambda c:(-(c['reported_15m_buys']+c['reported_15m_sells']),-D(c['reported_15m_volume_usd']),c['pool'])):
        if c['mint'] not in seen:cohort.append(c);seen.add(c['mint'])
        if len(cohort)>=8:break
    print('VERIFIED_FROZEN_COHORT '+json.dumps(cohort),flush=True)
    for c in cohort:
        if time.monotonic()+35>deadline:break
        row=dict(candidate=c,passed=False)
        try:
            row['first_data']=candles(c);row['first_at_monotonic']=time.monotonic()
            if not row['first_data']['usable']:row['rejection']='first_data_not_usable'
            else:
                row['price']=price(c);s=row['price'];spent=50050000;out=int(s['sell']['minQuote'])-50000
                row['stressed_loss_fraction']=str(1-D(out)/D(spent))
                if out*10000<spent*9800:row['rejection']='cost_above_2pct'
                else:watch.append(row)
        except Exception as exc:row['error']=str(exc)
        rows.append(row);print('VERIFIED_FIRST_CHECK '+json.dumps(row),flush=True)
    for row in watch:
        if time.monotonic()+50>deadline:break
        c=row['candidate']
        try:
            wait=65-(time.monotonic()-row['first_at_monotonic'])
            if wait>0:time.sleep(wait)
            row['second_data']=candles(c)
            if not row['second_data']['usable'] or row['second_data']['bar_time']<=row['first_data']['bar_time']:row['rejection']='second_data_stale_or_not_advanced'
            else:
                row['mint_checks']=gate.confirmed_standard_mint(c['mint'])
                info=spaced(scan.read_gecko,'/networks/solana/tokens/'+c['mint']+'/info')['data']['attributes']
                if info.get('address')!=c['mint']:raise ValueError('Info identity mismatch')
                row['reported_metadata']={k:info.get(k) for k in ('holders','developer_holding_percentage','launchpad_details','gt_verified')}
                launch=info.get('launchpad_details') or {}
                if launch.get('completed_at') and scan.age(launch['completed_at'])>4320:row['rejection']='known_old_migration'
                else:
                    holders=info.get('holders') or {};top=(holders.get('distribution_percentage') or {}).get('top_10');count=holders.get('count')
                    s=row['price'];outside=D(1)-D(s['target_pool_vault_atoms'])/D(s['target_mint_supply_atoms']);row['outside_verified_pool_fraction']=str(outside)
                    row['holder_control']='outside_pool_supply_upper_bound' if outside<=D('0.60') else 'provider_top10'
                    if count is None or int(count)<80 or (outside>D('0.60') and (top is None or D(str(top))>60)):row['rejection']='holder_filter_unresolved_or_failed'
                    else:
                        pools=spaced(scan.read_gecko,'/networks/solana/tokens/'+c['mint']+'/pools',{'page':1}).get('data',[])
                        known=[]
                        for p in pools:
                            ids=[v['data']['id'] for k,v in p['relationships'].items() if k in ('base_token','quote_token')]
                            if 'solana_'+c['mint'] not in ids:raise ValueError('Pool history identity mismatch')
                            known.append(dict(pool=p['attributes']['address'],age_minutes=scan.age(p['attributes']['pool_created_at'])))
                        row['known_pools']=known
                        if not known or not any(x['pool']==c['pool'] for x in known) or any(x['age_minutes']>4320 for x in known):row['rejection']='history_unverified_or_old'
                        else:row['passed']=True;chosen=c
        except Exception as exc:row['error']=str(exc)
        print('VERIFIED_SECOND_CHECK '+json.dumps(row),flush=True)
        if chosen:break
    print('VERIFIED_SCREEN_RESULT_JSON '+json.dumps(dict(status='candidate_verified_for_paper_only' if chosen else 'none_verified_in_sample',rules=rules,chosen=chosen,cohort=cohort,discovery_counts=counts,tested=rows,errors=errors,elapsed_seconds=time.monotonic()-began,real_trades=0,paper_trades=0,limitations=['Two usable advanced windows do not prove sustained data coverage.','Quote bounds and assumed network cost are not actual fills.','Holder data may be stale; pool-vault upper bound is not proof of independent ownership or locked liquidity.','Pool age is not mint birth; history query is bounded, not complete.','No profits, wallets, order construction or permanent bot.'])),flush=True)
if __name__=='__main__':main()
