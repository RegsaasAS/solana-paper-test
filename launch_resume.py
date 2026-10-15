"""One rate-limited retry of the original frozen candidates, no new discovery."""
import json
import time
import urllib.error
from decimal import Decimal as D
import launch_shortlist as launch
import safe_quote_gate as gate

COHORT_JSON='launch-resume-cohort.json'
_last_read=0

def slow(fn,*args,**kwargs):
    global _last_read
    delay=21-(time.monotonic()-_last_read)
    if delay>0:time.sleep(delay)
    _last_read=time.monotonic()
    return fn(*args,**kwargs)

def main():
    cohort=json.load(open(COHORT_JSON));result=dict(status='running',source_run=38716408506,cohort=cohort,tested=[],shortlist=[],paper_trades=0,real_trades=0,initial_backoff_seconds=60,gecko_spacing_seconds=21)
    time.sleep(60)
    for coin in cohort:
        row=dict(candidate=coin,shortlisted=False,unresolved=['Exact mint creation time unverified.','Liquidity locks, organic trading, social legitimacy and actual fills unverified.'])
        try:
            row['candles']=slow(launch.candles,coin)
            if row['candles']['data_passed']:
                row['mint_checks']=gate.confirmed_standard_mint(coin['mint'])
                info=slow(launch.read_gecko,'/networks/solana/tokens/'+coin['mint']+'/info')['data']['attributes']
                if info.get('address')!=coin['mint']:raise ValueError('Token info identity mismatch')
                row['reported_metadata']={k:info.get(k) for k in ('holders','developer_holding_percentage','launchpad_details','gt_verified','gt_category_ids')}
                holders=info.get('holders') or {};top=(holders.get('distribution_percentage') or {}).get('top_10');count=holders.get('count')
                row['holder_filter']=dict(top10_percent=top,count=count,passes_if_reported=(top is None or D(str(top))<=60) and (count is None or int(count)>=80))
                if top is None or count is None:row['unresolved'].append('Holder/concentration data incomplete.')
                launch_data=info.get('launchpad_details') or {};row['known_old_launch']=bool(launch_data.get('completed_at')) and launch.age(launch_data['completed_at'])>4320
                if row['holder_filter']['passes_if_reported'] and not row['known_old_launch']:
                    pools=slow(launch.read_gecko,'/networks/solana/tokens/'+coin['mint']+'/pools',{'page':1}).get('data',[])
                    ages=[]
                    for p in pools:
                        ids=[v['data']['id'] for k,v in p['relationships'].items() if k in ('base_token','quote_token')]
                        if 'solana_'+coin['mint'] not in ids:raise ValueError('Pool token mismatch')
                        ages.append(dict(pool=p['attributes']['address'],age_minutes=round(launch.age(p['attributes']['pool_created_at']),2)))
                    row['known_pool_age_check']=dict(returned_pools=ages,complete_history=False,known_older_pool=any(p['age_minutes']>4320 for p in ages))
                    if not row['known_pool_age_check']['known_older_pool']:
                        row['quotes']=launch.quote_check(coin)
                        row['shortlisted']=row['quotes']['cost_passed']
                        if not row['quotes']['signal_pool_used_in_both_quotes']:row['unresolved'].append('Quote route differs from signal pool; align before strategy test.')
        except Exception as exc:row['error']=str(exc)
        result['tested'].append(row)
        if row['shortlisted']:result['shortlist'].append(row)
        print('LAUNCH_RESUME_CANDIDATE '+json.dumps(row),flush=True)
    result['status']='completed' if all('error' not in r for r in result['tested']) else 'partial'
    print('LAUNCH_RESUME_RESULT_JSON '+json.dumps(result),flush=True)
if __name__=='__main__':main()
