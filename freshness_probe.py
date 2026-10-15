"""Bounded public data heartbeat. Logs every poll, including repeated and stale bars."""
import datetime as dt
import hashlib
import json
import time
import urllib.request
import dip_paper as dip
import safe_quote_gate as gate

COIN=dict(name='Nihilism / SOL',mint='FRCVr13HAEfvzyzQUr31CVVidPJ7zj8swQYkTDDU6Ls',pool='4NiSpF36BU3yNGzjaSktRe65Kgzpak3PKicofw3tgRBC')


def observation(rows,now,previous):
    d=dip.inspect(rows,now)
    stamp=d.get('bar_time')
    return dict(reason=d['reason'],eligible=d['eligible'],latest_closed_bar_time=stamp,latest_closed_bar_utc=dt.datetime.fromtimestamp(stamp,dt.timezone.utc).isoformat() if stamp is not None else None,age_after_close_seconds=round(now-stamp-60,3) if stamp is not None else None,advanced=previous is not None and stamp is not None and stamp>previous,repeated=previous is not None and stamp==previous,usable=d['reason'] in ('conditions_not_met','closed_bar_dip_rebound'),real_minutes=d.get('real_minutes'),empty_minutes=d.get('empty_minutes'))


def read(mode):
    before=int(time.time())//60*60
    url='https://api.geckoterminal.com/api/v2/networks/solana/pools/'+COIN['pool']+'/ohlcv/minute?aggregate=1&limit=30&currency=token&token=base&include_empty_intervals=true'
    if mode=='closed_cutoff':url+='&before_timestamp='+str(before-1)
    request=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'ReadOnlyDataHeartbeat/1.0'})
    with urllib.request.build_opener(gate.NoRedirect).open(request,timeout=8) as response:
        body=response.read(2_000_001)
        if len(body)>2_000_000:raise ValueError('Oversized data')
        headers={k:response.headers.get(k) for k in ('Date','Age','Cache-Control','CF-Cache-Status','X-Cache','ETag')}
    p=json.loads(body)
    if p.get('meta',{}).get('base',{}).get('address')!=COIN['mint'] or p.get('meta',{}).get('quote',{}).get('address')!=gate.SOL:raise ValueError('Candle asset identity mismatch')
    rows=p['data']['attributes']['ohlcv_list']
    if len({int(r[0]) for r in rows})!=len(rows):raise ValueError('Duplicate bar timestamps')
    return rows,dict(headers=headers,response_sha256=hashlib.sha256(body).hexdigest(),closed_cutoff_utc=dt.datetime.fromtimestamp(before,dt.timezone.utc).isoformat() if mode=='closed_cutoff' else None,returned_rows=len(rows))


def main():
    start=time.monotonic();samples=[];previous={};errors=[]
    for i in range(3):
        wait=start+i*65-time.monotonic()
        if wait>0:time.sleep(wait)
        for mode in ('default','closed_cutoff'):
            row=dict(poll=i,mode=mode,observed_utc=dip.utc())
            try:
                rows,details=read(mode)
                row.update(details);row.update(observation(rows,time.time(),previous.get(mode)))
                if row['latest_closed_bar_time'] is not None:previous[mode]=row['latest_closed_bar_time']
            except Exception as exc:
                row.update(usable=False,error=str(exc));errors.append(dict(poll=i,mode=mode,error=str(exc)))
            samples.append(row);print('DATA_HEARTBEAT '+json.dumps(row),flush=True)
            if mode=='default':time.sleep(8)
    modes={}
    for mode in ('default','closed_cutoff'):
        selected=[r for r in samples if r['mode']==mode]
        modes[mode]=dict(polls=len(selected),usable_polls=sum(r['usable'] for r in selected),advanced_polls=sum(r.get('advanced',False) for r in selected),repeated_polls=sum(r.get('repeated',False) for r in selected),stale_polls=sum(r.get('reason')=='stale_bar' for r in selected),errors=sum('error' in r for r in selected),passed=all(r['usable'] for r in selected) and sum(r.get('advanced',False) for r in selected)>=2)
    result=dict(status='freshness_observed' if any(x['passed'] for x in modes.values()) else 'freshness_not_demonstrated',coin=COIN,modes=modes,samples=samples,errors=errors,elapsed_seconds=time.monotonic()-start,real_trades=0,paper_trades=0,limitations=['Three polls over approximately 138 seconds cannot establish continuous market coverage or permanent reliability.','Before-timestamp is a legitimate closed-bar query; different responses do not by themselves establish caching as root cause.','Every poll is recorded, even if same bar becomes stale. No signal or risk thresholds changed.','Read-only data test, no profitability or fill evidence.'])
    print('FRESHNESS_RESULT_JSON '+json.dumps(result),flush=True)
if __name__=='__main__':main()
