"""One 30-minute paper-only forward test after the frozen activity screen."""
import json
import dip_paper as dip

COIN=dict(name='arc / SOL',mint='61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump',pool='J3b6dvheS2Y1cbMtVz5TCWXNegSjJDbUKxdUVDPoqmS7')

def main():
    if dip.RULES['runtime_seconds']!=900 or dip.RULES['minimum_real_minutes_per_16']!=8:raise ValueError('Unexpected baseline')
    original=dict(dip.RULES)
    dip.COHORT=[COIN]
    dip.RULES=dict(original,runtime_seconds=1800)
    assert all(dip.RULES[k]==v for k,v in original.items() if k!='runtime_seconds')
    print('ARC_WINDOW '+json.dumps(dict(screen_commit='ed367be36322b442908f6e4387e17afe9ec77dbd',screen_run=38701792782,cohort=dip.COHORT,changed_trade_rules=False,maximum_runtime_seconds=1800,permanent_operation=False)),flush=True)
    dip.main()
if __name__=='__main__':main()
