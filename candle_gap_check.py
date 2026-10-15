"""Bounded read-only comparison of omitted and explicit zero-trade minutes."""
import datetime as dt
import json
import time
from decimal import Decimal as D
import safe_quote_gate as gate

POOL='EP2ib6dYdEeqD8MfE2ezHCxX3kP3K2eLKkirfPm5eyMx'
MINT='EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm'

def read(before,fill):
    url=('https://api.geckoterminal.com/api/v2/networks/solana/pools/'+POOL+
         '/ohlcv/minute?aggregate=1&limit=60&currency=token&token=base&before_timestamp='+str(before-1)+
         '&include_empty_intervals='+str(fill).lower())
    p=gate.read_public(url)
    if p.get('meta',{}).get('base',{}).get('address')!=MINT or p.get('meta',{}).get('quote',{}).get('address')!=gate.SOL:
        raise ValueError('Wrong assets')
    rows=p['data']['attributes']['ohlcv_list']
    if any(len(r)!=6 or not all(D(str(v)).is_finite() for v in r) for r in rows):raise ValueError('Malformed candles')
    if len({int(r[0]) for r in rows})!=len(rows):raise ValueError('Duplicate candles')
    if any(int(r[0])+60>before for r in rows):raise ValueError('Unclosed candles')
    return {int(r[0]):r for r in rows}

def compare(raw,filled,before):
    start=before-16*60;end=before-60
    expected=set(range(start,before,60))
    raw_window={t:r for t,r in raw.items() if t in expected}
    fill_window={t:r for t,r in filled.items() if t in expected}
    extras={t:r for t,r in fill_window.items() if t not in raw}
    flat_zero=all(D(str(r[5]))==0 and len({D(str(v)) for v in r[1:5]})==1 for r in extras.values())
    same_real=all([D(str(v)) for v in raw[t]]==[D(str(v)) for v in r] for t,r in fill_window.items() if t in raw)
    prior_close=True
    for t,r in extras.items():
        earlier=[s for s in raw if s<t]
        if not earlier or D(str(r[4]))!=D(str(raw[max(earlier)][4])):prior_close=False
    return dict(before_utc=dt.datetime.fromtimestamp(before,dt.timezone.utc).isoformat(),raw_real_minutes=len(raw_window),filled_minutes=len(fill_window),expected_minutes=16,raw_missing_minutes=sorted(expected-raw.keys()),filled_missing_minutes=sorted(expected-filled.keys()),added_minutes=len(extras),added_are_flat_zero_volume=flat_zero,added_use_previous_real_close=prior_close,real_bars_unchanged=same_real,raw_window=list(raw_window.values()),filled_window=list(fill_window.values()),verified_empty_interval_explanation=bool(extras) and flat_zero and prior_close and same_real and len(fill_window)==16)

def main():
    r=dict(purpose='data_semantics_diagnostic_only_not_strategy_test',pool=POOL,mint=MINT,checks=[],errors=[],real_trades=0,paper_trades=0)
    windows=[('previous_test_final_window',int(dt.datetime(2026,10,15,0,10,tzinfo=dt.timezone.utc).timestamp())),('current_closed_window',int(time.time())//60*60)]
    for label,before in windows:
        try:
            raw=read(before,False);time.sleep(7);filled=read(before,True)
            row=compare(raw,filled,before);row['label']=label;r['checks'].append(row)
        except Exception as exc:r['errors'].append(dict(label=label,error=str(exc)))
        time.sleep(7)
    r['status']='completed' if not r['errors'] else 'incomplete'
    print('GAP_RESULT_JSON '+json.dumps(r),flush=True)

if __name__=='__main__':main()
