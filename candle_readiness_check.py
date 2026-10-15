"""Read-only verification of the production candle gate, with no ledger or quotes."""
import datetime as dt
import json
import time
from decimal import Decimal as D
import dip_paper as dip

def main():
    result=dict(status='running',minimum_real_minutes_per_16=dip.RULES['minimum_real_minutes_per_16'],checks=[],errors=[],paper_trades=0,real_trades=0)
    historic=int(dt.datetime(2026,10,15,0,10,tzinfo=dt.timezone.utc).timestamp())
    cases=[('historical_data_regression',dip.COHORT[1],historic)]+[('current_snapshot',coin,None) for coin in dip.COHORT]
    for label,coin,before in cases:
        try:
            rows=dip.fetch_candles(coin,before=before)
            now=before if before is not None else int(time.time())
            closed=sorted([r for r in rows if int(r[0])+60<=now],key=lambda r:r[0])
            d=dip.inspect(rows,now)
            result['checks'].append(dict(label=label,name=coin['name'],pool=coin['pool'],observed_utc=dip.utc(),evaluation_time_utc=dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),data_gate_passed=d['reason'] in ('conditions_not_met','closed_bar_dip_rebound'),data_check=d,actual_positive_volume_minutes_in_last16_returned=sum(D(str(r[5]))>0 for r in closed[-16:]),latest_bar_age_after_close_seconds=now-int(closed[-1][0])-60 if closed else None,last16_closed_rows=closed[-16:]))
        except Exception as exc:result['errors'].append(dict(label=label,name=coin['name'],error=str(exc)))
        time.sleep(7)
    result['status']='completed' if not result['errors'] else 'partial'
    result['current_data_ready_pools']=[c['name'] for c in result['checks'] if c['label']=='current_snapshot' and c['data_gate_passed']]
    result['limitations']=['Historical regression is a data-handling check, not a backtest.','One current snapshot does not prove continuous coverage or profitable trading.','Positive-volume minutes are not proof of organic activity.','No quote, order, signing or wallet access in this diagnostic.']
    print('READINESS_RESULT_JSON '+json.dumps(result),flush=True)
if __name__=='__main__':main()
