"""Inspect duplicate timestamps without using conflicting observations for trading."""
import collections
import json
import time
import urllib.request
from decimal import Decimal as D
import freshness_probe as probe
import safe_quote_gate as gate


def normalize(rows):
    grouped=collections.defaultdict(list)
    for row in rows:
        if len(row)!=6 or not all(D(str(v)).is_finite() for v in row):raise ValueError('Invalid row')
        stamp=D(str(row[0]))
        if stamp!=int(stamp) or int(stamp)%60:raise ValueError('Invalid minute timestamp')
        grouped[int(stamp)].append(row)
    duplicates={t:v for t,v in grouped.items() if len(v)>1}
    conflicting={t:v for t,v in duplicates.items() if len({tuple(D(str(x)) for x in r) for r in v})>1}
    details=dict(raw_rows=len(rows),unique_minutes=len(grouped),duplicate_minutes=len(duplicates),redundant_rows=len(rows)-len(grouped),conflicting_minutes=len(conflicting),duplicate_examples=[dict(timestamp=t,rows=v) for t,v in list(duplicates.items())[:4]])
    return None if conflicting else [grouped[t][0] for t in sorted(grouped)],details


def main():
    results=[]
    for mode in ('default','closed_cutoff'):
        out=dict(mode=mode,observed_utc=probe.dip.utc())
        try:
            before=int(time.time())//60*60
            url='https://api.geckoterminal.com/api/v2/networks/solana/pools/'+probe.COIN['pool']+'/ohlcv/minute?aggregate=1&limit=30&currency=token&token=base&include_empty_intervals=true'
            if mode=='closed_cutoff':url+='&before_timestamp='+str(before-1)
            req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'ReadOnlyDuplicateInspection/1.0'})
            with urllib.request.build_opener(gate.NoRedirect).open(req,timeout=8) as response:
                body=response.read(2_000_001)
                if len(body)>2_000_000:raise ValueError('Oversized response')
                out['headers']={k:response.headers.get(k) for k in ('Date','Age','Cache-Control','CF-Cache-Status')}
            p=json.loads(body)
            if p.get('meta',{}).get('base',{}).get('address')!=probe.COIN['mint'] or p.get('meta',{}).get('quote',{}).get('address')!=gate.SOL:raise ValueError('Asset mismatch')
            rows=p['data']['attributes']['ohlcv_list'];clean,details=normalize(rows);out.update(details)
            out['raw_rows']=rows
            out['normalization_status']='conflicting_rows_rejected' if clean is None else 'exact_duplicates_removed'
            if clean is not None:out['assessment']=probe.observation(clean,time.time(),None)
        except Exception as e:out['error']=str(e)
        results.append(out);print('DUPLICATE_SAMPLE '+json.dumps(out),flush=True)
        if mode=='default':time.sleep(8)
    print('DUPLICATE_RESULT_JSON '+json.dumps(dict(samples=results,real_trades=0,paper_trades=0)),flush=True)
if __name__=='__main__':main()
