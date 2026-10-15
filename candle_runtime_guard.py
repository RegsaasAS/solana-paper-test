"""Fail closed on unusable market data and retain a heartbeat for every candle poll."""
import json
import time
import dip_paper as engine
from candle_duplicates import normalize

ORIGINAL_FETCH=engine.fetch_candles
ORIGINAL_INSPECT=engine.inspect
ORIGINAL_SUMMARY=engine.Ledger.summary
POLLS=[]


def checked_fetch(coin,before=None):
    try:
        # Provider's closed-minute cutoff, not a fabricated cache-busting argument.
        rows=ORIGINAL_FETCH(coin,int(time.time())//60*60 if before is None else before)
        clean,details=normalize(rows)
        if clean is None:raise ValueError('Conflicting minute data; no row selected')
        return clean
    except Exception as exc:
        p=dict(observed_utc=engine.utc(),usable=False,stage='fetch',error=str(exc),mint=coin['mint'])
        POLLS.append(p);print('CANDLE_POLL '+json.dumps(p),flush=True)
        raise


def checked_inspect(rows,now):
    try:
        d=ORIGINAL_INSPECT(rows,now)
    except Exception as exc:
        p=dict(observed_utc=engine.utc(),usable=False,stage='inspect',error=str(exc))
        POLLS.append(p);print('CANDLE_POLL '+json.dumps(p),flush=True)
        raise
    p=dict(observed_utc=engine.utc(),reason=d['reason'],bar_time=d.get('bar_time'),usable=d['reason'] in ('conditions_not_met','closed_bar_dip_rebound'),eligible=d['eligible'],real_minutes=d.get('real_minutes'))
    if p['bar_time'] is not None:p['age_after_close_seconds']=round(now-p['bar_time']-60,3)
    POLLS.append(p);print('CANDLE_POLL '+json.dumps(p),flush=True)
    if not p['usable']:raise ValueError('Unusable candle poll: '+p['reason'])
    return d


def checked_summary(self,status,last_quote=None):
    r=ORIGINAL_SUMMARY(self,status,last_quote)
    r.update(candle_polls=list(POLLS),candle_poll_count=len(POLLS),usable_candle_poll_count=sum(p['usable'] for p in POLLS),unusable_candle_poll_count=sum(not p['usable'] for p in POLLS),freshness_guard_enabled=True)
    return r


def install():
    POLLS.clear()
    engine.fetch_candles=checked_fetch
    engine.inspect=checked_inspect
    engine.Ledger.summary=checked_summary
