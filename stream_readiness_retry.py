"""One bounded retry for a transient STREAM second-window timeout; no new discovery."""
import json
import time
from decimal import Decimal as D
import verified_candidate_screen as v
import launch_shortlist as scan
import safe_quote_gate as gate

C=dict(name='STREAM / SOL',mint='9a98oQHtxfqmr4EyzsP6wfw69uYAK3JbUeVEuNW1pump',pool='D9NCkN3unPTVLtA56Y68J2cXisje9yyYe61gMM2HCHwJ')
def main():
    r=dict(candidate=C,status='not_verified',source_run=38750921870,real_trades=0,paper_trades=0);started=time.monotonic()
    try:
        r['first_data']=v.candles(C);first=time.monotonic()
        if not r['first_data']['usable']:raise ValueError('First data unusable')
        r['mint_checks']=gate.confirmed_standard_mint(C['mint'])
        info=v.spaced(scan.read_gecko,'/networks/solana/tokens/'+C['mint']+'/info')['data']['attributes']
        if info.get('address')!=C['mint']:raise ValueError('Info identity mismatch')
        r['reported_metadata']={k:info.get(k) for k in ('holders','developer_holding_percentage','launchpad_details','gt_verified')}
        h=info.get('holders') or {};top=(h.get('distribution_percentage') or {}).get('top_10');count=h.get('count')
        if top is None or count is None or D(str(top))>60 or int(count)<80:raise ValueError('Holder filter missing or failed')
        launch=info.get('launchpad_details') or {}
        if launch.get('completed_at') and scan.age(launch['completed_at'])>4320:raise ValueError('Known migration older than 72 hours')
        pools=v.spaced(scan.read_gecko,'/networks/solana/tokens/'+C['mint']+'/pools',{'page':1}).get('data',[]);known=[]
        for p in pools:
            ids=[x['data']['id'] for k,x in p['relationships'].items() if k in ('base_token','quote_token')]
            if 'solana_'+C['mint'] not in ids:raise ValueError('History identity mismatch')
            known.append(dict(pool=p['attributes']['address'],age_minutes=scan.age(p['attributes']['pool_created_at'])))
        r['known_pools']=known
        if not known or not any(p['pool']==C['pool'] for p in known) or any(p['age_minutes']>4320 for p in known):raise ValueError('Known history old or missing')
        print('READINESS_PARTIAL '+json.dumps(r),flush=True)
        wait=65-(time.monotonic()-first)
        if wait>0:time.sleep(wait)
        r['second_data']=v.candles(C)
        if not r['second_data']['usable'] or r['second_data']['bar_time']<=r['first_data']['bar_time']:raise ValueError('Second window not usable and advancing')
        r['price']=v.price(C);s=r['price'];spent=50050000;out=int(s['sell']['minQuote'])-50000
        r['stressed_loss_fraction']=str(1-D(out)/D(spent))
        if out*10000<spent*9800:raise ValueError('Cost exceeds unchanged 2 percent ceiling')
        r['status']='verified_for_paper_only'
    except Exception as exc:r['error']=str(exc)
    r['elapsed_seconds']=time.monotonic()-started
    print('STREAM_READINESS_RESULT_JSON '+json.dumps(r),flush=True)
if __name__=='__main__':main()
