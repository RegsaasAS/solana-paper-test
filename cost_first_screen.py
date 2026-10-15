"""One bounded cost-first refresh; freeze cohort before checking any price outcome."""
import json
import time
from decimal import Decimal as D
import launch_shortlist as scan
import safe_quote_gate as gate


def main():
    began=time.monotonic();deadline=began+360;found={};errors=[];rows=[];counts={}
    sources=[('trending_pools',i) for i in (1,2,3,4)]+[('new_pools',i) for i in (1,5)]
    print('COST_FIRST_RULES '+json.dumps(dict(base=scan.RULES,sources=sources,same_signal_and_quote_pool_required=True,maximum_candidates=6,maximum_runtime_seconds=360,returns_not_used_for_ranking=True)),flush=True)
    for source,page in sources:
        label=source+':'+str(page)
        try:
            params={'page':page}
            if source=='trending_pools':params['duration']='1h'
            result=scan.read_gecko('/networks/solana/'+source,params)
            counts[label]=len(result.get('data',[]))
            for raw in result.get('data',[]):
                c=scan.discover(raw,label)
                if c:found[c['pool']]=c
        except Exception as e:errors.append(dict(stage='discovery',source=label,error=str(e)))
    ranked=sorted(found.values(),key=lambda c:(-(c['reported_15m_buys']+c['reported_15m_sells']),-D(c['reported_15m_volume_usd']),c['pool']))
    cohort=[];seen=set()
    for c in ranked:
        if c['mint'] not in seen:cohort.append(c);seen.add(c['mint'])
        if len(cohort)>=6:break
    print('COST_FIRST_FROZEN_COHORT '+json.dumps(cohort),flush=True)
    for c in cohort:
        if time.monotonic()+60>deadline:break
        row=dict(candidate=c,passed=False)
        try:
            row['quotes']=scan.quote_check(c)
            if not row['quotes']['cost_passed']:row['rejection']='roundtrip_cost_above_2pct'
            elif not row['quotes']['signal_pool_used_in_both_quotes']:row['rejection']='quote_pool_differs_from_signal_pool'
            else:
                row['mint_checks']=gate.confirmed_standard_mint(c['mint'])
                row['candles']=scan.candles(c)
                if not row['candles']['data_passed']:row['rejection']='candle_data_or_activity'
                else:
                    info=scan.read_gecko('/networks/solana/tokens/'+c['mint']+'/info')['data']['attributes']
                    if info.get('address')!=c['mint']:raise ValueError('Metadata identity mismatch')
                    row['reported_metadata']={k:info.get(k) for k in ('holders','developer_holding_percentage','launchpad_details','gt_verified')}
                    holders=info.get('holders') or {};top=(holders.get('distribution_percentage') or {}).get('top_10');n=holders.get('count')
                    if top is None or n is None:row['rejection']='holder_data_unavailable'
                    elif D(str(top))>60 or int(n)<80:row['rejection']='reported_holder_filter'
                    else:
                        pools=scan.read_gecko('/networks/solana/tokens/'+c['mint']+'/pools',{'page':1}).get('data',[])
                        known=[]
                        for p in pools:
                            ids=[v['data']['id'] for k,v in p['relationships'].items() if k in ('base_token','quote_token')]
                            if 'solana_'+c['mint'] not in ids:raise ValueError('Other pool identity mismatch')
                            known.append(dict(pool=p['attributes']['address'],age_minutes=scan.age(p['attributes']['pool_created_at'])))
                        row['known_pools']=known
                        launch=info.get('launchpad_details') or {}
                        if any(x['age_minutes']>4320 for x in known) or (launch.get('completed_at') and scan.age(launch['completed_at'])>4320):row['rejection']='known_old_token'
                        else:row['passed']=True
        except Exception as e:row['error']=str(e)
        rows.append(row);print('COST_FIRST_CANDIDATE '+json.dumps(row),flush=True)
    result=dict(status='candidate_found' if any(r['passed'] for r in rows) else 'none_verified_in_sample',discovery_counts=counts,cohort=cohort,tested=rows,untested_count=len(cohort)-len(rows),errors=errors,elapsed_seconds=time.monotonic()-began,paper_trades=0,real_trades=0,credentials_used=False,limitations=['Bounded sample, not whole market. Ranking uses reported activity, not subsequent returns.','Pool age is not token launch age. Metadata and holders are provider reports, not full security audit.','Both quote sides use 0.5% adverse bounds and assumed 50000 lamports network each; setup costs separate/unverified.','Quotes are hypothetical and do not establish actual fills, organic flow or profitability.','No candidate causes an automatic trade or strategy run.'])
    print('COST_FIRST_RESULT_JSON '+json.dumps(result),flush=True)
if __name__=='__main__':main()
