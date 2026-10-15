"""Supplement the frozen discovery cohort with already checked official pool pricing."""
import json
import subprocess
import time
from decimal import Decimal as D
from pathlib import Path
import launch_shortlist as scan
import safe_quote_gate as gate


def main():
    began=time.monotonic();cohort=json.loads(Path('cost-pool-cohort.json').read_text());rows=[]
    for coin in cohort:
        row=dict(candidate=coin,passed=False)
        try:
            p=subprocess.run(['node','cohort_pool_price.cjs','buy',coin['pool'],coin['mint']],capture_output=True,text=True,timeout=45)
            if p.returncode:raise ValueError(p.stderr[-1400:])
            lines=[x for x in p.stdout.splitlines() if x.startswith('STREAM_SNAPSHOT_JSON ')]
            if len(lines)!=1:raise ValueError('Unique pricing result missing')
            s=json.loads(lines[0].split(' ',1)[1]);row['snapshot']=s
            if s['pool']!=coin['pool'] or s['mint']!=coin['mint']:raise ValueError('Identity mismatch')
            spent=50_050_000;out=int(s['sell']['minQuote'])-50_000
            row['stressed_loss_fraction']=str(1-D(out)/D(spent))
            if out*10000<spent*9800:row['rejection']='stressed_cost_above_2pct'
            else:
                row['mint_checks']=gate.confirmed_standard_mint(coin['mint'])
                row['candles']=scan.candles(coin)
                if not row['candles']['data_passed']:row['rejection']='candle_data_or_activity'
                else:
                    info=scan.read_gecko('/networks/solana/tokens/'+coin['mint']+'/info')['data']['attributes']
                    if info.get('address')!=coin['mint']:raise ValueError('Metadata identity mismatch')
                    row['reported_metadata']={k:info.get(k) for k in ('holders','developer_holding_percentage','launchpad_details','gt_verified')}
                    holders=info.get('holders') or {};top=(holders.get('distribution_percentage') or {}).get('top_10');n=holders.get('count')
                    if top is None or n is None:row['rejection']='holder_data_unavailable'
                    elif D(str(top))>60 or int(n)<80:row['rejection']='reported_holder_filter'
                    else:
                        pools=scan.read_gecko('/networks/solana/tokens/'+coin['mint']+'/pools',{'page':1}).get('data',[])
                        known=[]
                        for p in pools:
                            ids=[v['data']['id'] for k,v in p['relationships'].items() if k in ('base_token','quote_token')]
                            if 'solana_'+coin['mint'] not in ids:raise ValueError('Other pool identity mismatch')
                            known.append(dict(pool=p['attributes']['address'],age_minutes=scan.age(p['attributes']['pool_created_at'])))
                        row['known_pools']=known
                        launch=info.get('launchpad_details') or {}
                        if any(x['age_minutes']>4320 for x in known) or (launch.get('completed_at') and scan.age(launch['completed_at'])>4320):row['rejection']='known_old_token'
                        else:row['passed']=True
        except Exception as e:row['error']=str(e)
        rows.append(row);print('COHORT_COST_CANDIDATE '+json.dumps(row),flush=True)
        if time.monotonic()-began>240:break
        time.sleep(3)
    print('COHORT_COST_RESULT_JSON '+json.dumps(dict(status='candidate_found' if any(r['passed'] for r in rows) else 'none_verified_in_sample',source_run=38719983617,tested=rows,elapsed_seconds=time.monotonic()-began,untested_count=len(cohort)-len(rows),real_trades=0,paper_trades=0,limitations=['Same frozen cohort, no selection using returns.','Pure PumpSwap estimates on one unchanged snapshot, no actual fills or transaction simulation.','Both 0.5% adverse bounds and 50000 lamports assumed network per side. Account deposit/setup excluded from per-trade cost guard.','Mint and provider-holder checks are incomplete safety evidence; reported pool age is not token creation age.'])),flush=True)
if __name__=='__main__':main()
