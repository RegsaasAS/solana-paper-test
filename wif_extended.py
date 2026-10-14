"""One bounded extension of the already declared WIF paper hypothesis."""
import json
import dip_paper as dip


def main():
    # Preserve every entry, exit, position, risk and cost rule.
    original_rules=dict(dip.RULES)
    wif=[coin for coin in dip.COHORT if coin['mint']=='EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm']
    if len(wif)!=1 or original_rules['runtime_seconds']!=900:
        raise ValueError('Unexpected baseline; extended test not started')
    dip.COHORT=wif
    dip.RULES=dict(original_rules,runtime_seconds=14400)
    assert {k:v for k,v in dip.RULES.items() if k!='runtime_seconds'}=={k:v for k,v in original_rules.items() if k!='runtime_seconds'}
    print('EXTENDED_WINDOW '+json.dumps(dict(duration_seconds=14400,cohort=wif,changed_trade_rules=False,maximum_roundtrips=2,permanent_operation=False)),flush=True)
    dip.main()


if __name__=='__main__':main()
