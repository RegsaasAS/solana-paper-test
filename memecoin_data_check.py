"""Bounded read-only data feasibility check, no orders or performance model."""
import datetime as dt
import json
import time
import urllib.error
import urllib.request

BASE = 'https://api.geckoterminal.com/api/v2'
SOL = 'solana_So11111111111111111111111111111111111111112'
MAX_SECONDS = 300
MIN_LIQUIDITY = 1000


def stamp(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def main():
    started = time.time()
    deadline = time.monotonic() + MAX_SECONDS
    last_call = 0
    errors, observations, candidates = [], [], []
    calls = 0

    def get(path):
        nonlocal last_call, calls
        wait = max(0, last_call + 7 - time.monotonic())
        if time.monotonic() + wait + 9 > deadline:
            raise TimeoutError('Test time budget exhausted')
        time.sleep(wait)
        last_call = time.monotonic()
        calls += 1
        req = urllib.request.Request(BASE + path, headers={'Accept': 'application/json;version=20230302', 'User-Agent': 'BoundedPaperDataResearch/1.0'})
        began = time.monotonic()
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.load(response)
            meta = dict(received_utc=dt.datetime.now(dt.timezone.utc).isoformat(), latency_seconds=round(time.monotonic()-began,3), http_status=response.status, http_age=response.headers.get('Age'))
        if not isinstance(data.get('data'), list):
            raise ValueError('Unexpected public API schema')
        return data['data'], meta

    available = {}
    for page in (1,5,10):
        try:
            rows, meta = get('/networks/solana/new_pools?page=' + str(page))
            for pool in rows:
                attr, rel = pool['attributes'], pool['relationships']
                base = rel['base_token']['data']['id']
                quote = rel['quote_token']['data']['id']
                age = started - stamp(attr['pool_created_at'])
                if quote == SOL and base != SOL and 0 <= age <= 86400 and float(attr.get('reserve_in_usd') or 0) >= MIN_LIQUIDITY:
                    available.setdefault(base, dict(pool=attr['address'], token=base, name=attr['name'], created_at=attr['pool_created_at'], initial_liquidity_usd=attr['reserve_in_usd']))
        except Exception as exc:
            errors.append(dict(stage='discovery',page=page,error=str(exc)))
    candidates = sorted(available.values(), key=lambda c: c['pool'])[:5]
    print('FIXED_COHORT ' + json.dumps(candidates), flush=True)
    stats = {c['pool']: dict(valid_snapshots=0, missing_snapshots=0, price_changes=0, liquidity_changes=0, trade_responses=0, fresh_latest_trade_responses=0, missing_trade_timestamp=0, new_unique_trade_count=0, observed_buy_count=0, observed_sell_count=0, previous_price=None, previous_liquidity=None, seen=set(), latest_trade_age_seconds=[]) for c in candidates}
    if candidates:
        for round_number in range(6):
            try:
                pools, meta = get('/networks/solana/pools/multi/' + ','.join(c['pool'] for c in candidates))
                by_address = {p['attributes']['address']:p for p in pools}
                for c in candidates:
                    s = stats[c['pool']]
                    p = by_address.get(c['pool'])
                    if not p:
                        s['missing_snapshots'] += 1
                        continue
                    a = p['attributes']
                    price, liquidity = a.get('base_token_price_usd'), a.get('reserve_in_usd')
                    valid = price is not None and liquidity is not None and float(price)>0 and float(liquidity)>0
                    if valid:
                        s['valid_snapshots'] += 1
                        s['price_changes'] += s['previous_price'] is not None and price != s['previous_price']
                        s['liquidity_changes'] += s['previous_liquidity'] is not None and liquidity != s['previous_liquidity']
                        s['previous_price'], s['previous_liquidity'] = price, liquidity
                    else:
                        s['missing_snapshots'] += 1
                    observations.append(dict(kind='pool_snapshot',round=round_number,pool=c['pool'],price_usd=price,liquidity_usd=liquidity,**meta))
            except Exception as exc:
                errors.append(dict(stage='pool_snapshot',round=round_number,error=str(exc)))
                if isinstance(exc,TimeoutError):
                    break
            exhausted = False
            for c in candidates:
                try:
                    trades, meta = get('/networks/solana/pools/' + c['pool'] + '/trades')
                    s = stats[c['pool']]
                    s['trade_responses'] += 1
                    event_times = []
                    for t in trades:
                        a = t['attributes']
                        value = a.get('block_timestamp')
                        if not value:
                            continue
                        event = stamp(value)
                        event_times.append(event)
                        key = t.get('id') or a.get('tx_hash')
                        if not key or key in s['seen']:
                            continue
                        s['seen'].add(key)
                        if event >= started and event <= time.time()+5:
                            s['new_unique_trade_count'] += 1
                            if a.get('kind') == 'buy':
                                s['observed_buy_count'] += 1
                            elif a.get('kind') == 'sell':
                                s['observed_sell_count'] += 1
                    age = time.time()-max(event_times) if event_times else None
                    if age is None:
                        s['missing_trade_timestamp'] += 1
                    else:
                        s['latest_trade_age_seconds'].append(round(age,3))
                        if 0 <= age <= 60:
                            s['fresh_latest_trade_responses'] += 1
                    observations.append(dict(kind='recent_trades',round=round_number,pool=c['pool'],returned_count=len(trades),latest_trade_age_seconds=age,**meta))
                except Exception as exc:
                    errors.append(dict(stage='recent_trades',round=round_number,pool=c['pool'],error=str(exc)))
                    if isinstance(exc,TimeoutError):
                        exhausted = True
                        break
            if exhausted:
                break
    for s in stats.values():
        s.pop('seen')
        n = s['trade_responses']
        s['fresh_trade_fraction'] = s['fresh_latest_trade_responses']/n if n else None
        s['coarse_monitoring_check_passed'] = s['valid_snapshots']>=4 and n>=4 and s['fresh_latest_trade_responses']/n>=0.8 and s['observed_buy_count']>0 and s['observed_sell_count']>0
    count = sum(s['coarse_monitoring_check_passed'] for s in stats.values())
    result = dict(purpose='public_memecoin_candidate_data_feasibility_only',status='completed' if candidates else 'no_eligible_cohort',started_utc=dt.datetime.fromtimestamp(started,dt.timezone.utc).isoformat(),ended_utc=dt.datetime.now(dt.timezone.utc).isoformat(),maximum_runtime_seconds=MAX_SECONDS,elapsed_seconds=round(time.time()-started,3),source='GeckoTerminal public API v2',sampling='New pools pages 1,5,10; SOL quote, age <=24h, liquidity >=1000 USD; unique base tokens, first five by pool address; frozen before observations. Candidate names do not establish token purpose or safety.',cohort=candidates,api_calls=calls,minimum_request_spacing_seconds=7,errors=errors,pools=stats,observations=observations,coarse_monitoring_pass_count=count,coarse_monitoring_feasible_in_this_sample=count>=3,executable_quotes_verified=False,trades_executed=0,paper_trades=0,profitability_evaluated=False,limitations=['Partial discovery universe; no broad strategy or representativeness claim.', 'Recent trade age combines actual inactivity and unknown indexing delay; not a measured indexing latency.', 'Recent trade lists are bounded at 300; completeness not verified.', 'Pool price and liquidity are not size-specific executable buy/sell quotes.', 'No wallet safety, token authority, liquidity control or holder concentration checks.', 'At most five-minute data test; no continuous operation or profitability proof.'])
    print('MEME_DATA_JSON ' + json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
