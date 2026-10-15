"""Fixed public data reads only: pool activity, chart freshness and chain cross-check."""
import datetime as dt
import json
import re
import time
import urllib.request
from safe_quote_gate import NoRedirect, SOL
POOL='EP2ib6dYdEeqD8MfE2ezHCxX3kP3K2eLKkirfPm5eyMx'
MINT='EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm'
BASE='https://api.geckoterminal.com/api/v2/networks/solana/pools/'+POOL
READS={'pool':BASE,'trades':BASE+'/trades?trade_volume_in_usd_greater_than=0','candles':BASE+'/ohlcv/minute?aggregate=1&limit=60&currency=token&token=base&include_empty_intervals=false','rpc':'https://api.mainnet-beta.solana.com'}

def public_read(kind,payload=None):
    if kind not in READS:raise ValueError('Not a fixed public read')
    if kind=='rpc':
        if payload is None or payload.get('method') not in ('getSignaturesForAddress','getTransaction'):raise ValueError('Not a permitted read-only RPC method')
        if payload['method']=='getSignaturesForAddress' and payload['params'][0]!=POOL:raise ValueError('Not the fixed pool')
        if payload['method']=='getTransaction' and not re.fullmatch(r'[1-9A-HJ-NP-Za-km-z]{64,90}',payload['params'][0]):raise ValueError('Invalid public signature')
    elif payload is not None:raise ValueError('GET only')
    req=urllib.request.Request(READS[kind],data=json.dumps(payload).encode() if payload else None,headers={'Accept':'application/json','Content-Type':'application/json','User-Agent':'ReadOnlyPoolActivityCheck/1.0'})
    with urllib.request.build_opener(NoRedirect).open(req,timeout=10) as response:
        body=response.read(2_000_001)
        if len(body)>2_000_000:raise ValueError('Oversized public response')
        p=json.loads(body)
    if kind=='rpc' and p.get('error'):raise ValueError('RPC: '+json.dumps(p['error']))
    return p

def epoch(s):return dt.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
def stamp(s):return dt.datetime.fromtimestamp(s,dt.timezone.utc).isoformat() if s is not None else None

def main():
    r=dict(pool=POOL,mint=MINT,started_utc=stamp(time.time()),errors=[],real_trades_submitted=0,paper_trades=0)
    try:
        p=public_read('pool')['data'];a=p['attributes'];rel=p['relationships']
        if rel['base_token']['data']['id']!='solana_'+MINT or rel['quote_token']['data']['id']!='solana_'+SOL:raise ValueError('Pool identity mismatch')
        r['pool_info']={k:a.get(k) for k in ('address','name','reserve_in_usd','volume_usd','transactions','pool_created_at')}
    except Exception as exc:r['errors'].append(dict(stage='pool',error=str(exc)))
    time.sleep(7)
    try:
        p=public_read('trades');trades=[]
        for t in p['data']:
            a=t['attributes']
            if {a['from_token_address'],a['to_token_address']}!={MINT,SOL}:raise ValueError('Trade asset mismatch')
            trades.append({k:a.get(k) for k in ('tx_hash','block_timestamp','kind','volume_in_usd','from_token_address','to_token_address')})
        trades.sort(key=lambda a:epoch(a['block_timestamp']),reverse=True)
        now=time.time()
        r['reported_trades']=dict(returned_count=len(trades),not_exhaustive=True,latest_age_seconds=round(now-epoch(trades[0]['block_timestamp']),2) if trades else None,latest=trades[:5],returned_last_15min=sum(0<=now-epoch(t['block_timestamp'])<=900 for t in trades))
    except Exception as exc:r['errors'].append(dict(stage='trades',error=str(exc)))
    time.sleep(7)
    try:
        p=public_read('candles')
        if p.get('meta',{}).get('base',{}).get('address')!=MINT or p.get('meta',{}).get('quote',{}).get('address')!=SOL:raise ValueError('Candle identity mismatch')
        now=time.time();rows=p['data']['attributes']['ohlcv_list'];closed=sorted([v for v in rows if int(v[0])+60<=now],key=lambda a:a[0])
        r['candles']=dict(returned_rows=len(rows),latest_any_bar_start_utc=stamp(max(int(v[0]) for v in rows)) if rows else None,latest_closed_bar_start_utc=stamp(int(closed[-1][0])) if closed else None,latest_closed_bar_age_after_close_seconds=round(now-int(closed[-1][0])-60,2) if closed else None,real_closed_rows_last_16min=sum(now-960<=int(v[0]) for v in closed),last_five_closed_rows=closed[-5:])
    except Exception as exc:r['errors'].append(dict(stage='candles',error=str(exc)))
    time.sleep(7)
    try:
        p=public_read('rpc',dict(jsonrpc='2.0',id=1,method='getSignaturesForAddress',params=[POOL,dict(limit=5,commitment='confirmed')]))
        sigs=[{k:a.get(k) for k in ('signature','slot','err','blockTime','confirmationStatus')} for a in p['result']]
        r['onchain_pool_transactions']=dict(latest=sigs,latest_age_seconds=round(time.time()-sigs[0]['blockTime'],2) if sigs and sigs[0]['blockTime'] is not None else None,limitation='Pool references are not automatically swaps.')
        valid=next((s for s in sigs if s['err'] is None),None)
        if valid:
            time.sleep(7)
            p=public_read('rpc',dict(jsonrpc='2.0',id=2,method='getTransaction',params=[valid['signature'],dict(encoding='jsonParsed',maxSupportedTransactionVersion=0,commitment='confirmed')]))
            t=p.get('result')
            if t:
                keys=t['transaction']['message']['accountKeys'];keys=[k.get('pubkey') if isinstance(k,dict) else k for k in keys]
                meta=t['meta'];balances=meta.get('preTokenBalances',[])+meta.get('postTokenBalances',[])
                swap_logs=[s for s in meta.get('logMessages',[]) if re.search(r'Instruction: Swap',s,re.I)]
                r['latest_confirmed_transaction_detail']=dict(signature=valid['signature'],blockTime=t.get('blockTime'),block_utc=stamp(t.get('blockTime')),pool_referenced=POOL in keys,error=meta.get('err'),contains_wif_balance=any(b['mint']==MINT for b in balances),contains_wrapped_sol_balance=any(b['mint']==SOL for b in balances),swap_instruction_logs=swap_logs,limitation='Transaction may contain multiple pool operations; no claim of complete swap decoding.')
            else:r['errors'].append(dict(stage='transaction',error='Transaction details unavailable'))
    except Exception as exc:r['errors'].append(dict(stage='rpc',error=str(exc)))
    r['completed_utc']=stamp(time.time());r['status']='completed' if not r['errors'] else 'partial'
    print('ACTIVITY_RESULT_JSON '+json.dumps(r),flush=True)
if __name__=='__main__':main()
