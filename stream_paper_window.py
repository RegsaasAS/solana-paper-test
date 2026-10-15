"""Frozen STREAM forward paper test. Public RPC/market data only; no wallet."""
import json
import subprocess
import time
from pathlib import Path
import dip_paper as dip
import safe_quote_gate as gate

COIN=dict(name='STREAM / SOL',mint='9a98oQHtxfqmr4EyzsP6wfw69uYAK3JbUeVEuNW1pump',pool='D9NCkN3unPTVLtA56Y68J2cXisje9yyYe61gMM2HCHwJ')
OBSERVATIONS=[]
OriginalLedger=dip.Ledger


def quote(a,b,n):
    buy=(a,b)==(gate.SOL,COIN['mint'])
    if not buy and (a,b)!=(COIN['mint'],gate.SOL):raise ValueError('Unexpected pair')
    if n<=0 or (buy and n!=50_000_000):raise ValueError('Unexpected amount')
    started=time.monotonic()
    p=subprocess.run(['node','stream_paper_prices.cjs','buy' if buy else str(n)],capture_output=True,text=True,timeout=45)
    if p.returncode:raise ValueError('Public pricing failed: '+p.stderr[-2000:])
    lines=[x for x in p.stdout.splitlines() if x.startswith('STREAM_SNAPSHOT_JSON ')]
    if len(lines)!=1:raise ValueError('Missing unique snapshot')
    s=json.loads(lines[0].split(' ',1)[1])
    if s['pool']!=COIN['pool'] or s['mint']!=COIN['mint']:raise ValueError('Wrong pool/mint')
    if time.monotonic()-started>12:raise ValueError('Pricing observation too slow')
    OBSERVATIONS.append(s)
    return dict(received_utc=s['observed_utc'],latency_seconds=time.monotonic()-started,snapshot=s,quote=dict(inputMint=a,outputMint=b,inputAmount=n,outputAmount=int(s['buy']['base'] if buy else s['sell']['uiQuote']),otherAmountThreshold=int(s['conservative_buy_quantity_atoms'] if buy else s['sell']['minQuote']),routePlan=[dict(poolId=COIN['pool'])]))


class StreamLedger(OriginalLedger):
    def __init__(self):
        super().__init__();self.rent_deposit=0
    def enter(self,coin,buy,sell,now):
        deposit=int(buy['snapshot']['refundable_rent_deposit_lamports']) if not self.accounts else 0
        before=self.cash
        if before<50_100_000+deposit:return False
        if self.position:raise ValueError('One position only')
        qty=int(buy['quote']['otherAmountThreshold'])
        if qty<=0 or buy['quote']['inputMint']!=gate.SOL or buy['quote']['outputMint']!=coin['mint'] or int(buy['quote']['inputAmount'])!=50_000_000 or sell['quote']['inputMint']!=coin['mint'] or sell['quote']['outputMint']!=gate.SOL or int(sell['quote']['inputAmount'])!=qty:raise ValueError('Entry quotes mismatched')
        spent=50_000_000+dip.RULES['network_cost_assumed_lamports_per_side']
        proceeds=int(sell['quote']['otherAmountThreshold'])-dip.RULES['network_cost_assumed_lamports_per_side']
        if proceeds*10000<spent*9800:return False
        setup=0 if self.accounts else dip.RULES['first_token_account_cost_assumed_lamports']
        if self.cash<spent+setup+deposit:return False
        if deposit:
            self.record('ACCOUNT_RENT_DEPOSIT',-deposit,assumed_created=True,refundable_if_empty_and_closed=True)
            self.rent_deposit+=deposit
        if setup:self.record('ACCOUNT_SETUP_MODEL_COST',-setup,assumed=True,refunded=False)
        self.accounts.add(coin['mint'])
        self.record('BUY',-spent,mint=coin['mint'],quantity_atoms=qty,quote=buy)
        self.position=dict(coin=coin,quantity_atoms=qty,spent_lamports=spent,entry_at=now,entry_utc=dip.utc())
        return True
    def summary(self,status,last_quote=None):
        s=super().summary(status,last_quote)
        s['recoverable_account_rent_lamports']=self.rent_deposit
        equity=s['equity_at_last_valid_quote_lamports']
        s['cash_plus_position_plus_recoverable_rent_lamports']=None if equity is None else equity+self.rent_deposit
        s['full_portfolio_net_pnl_lamports']=None if equity is None else equity+self.rent_deposit-1_000_000_000
        s['cash_net_change_lamports']=self.cash-1_000_000_000
        s['rent_refund_executed']=False
        if not self.position:
            assert s['full_portfolio_net_pnl_lamports']==sum(e.get('net_trade_pnl_lamports',0) for e in self.events)-s['account_setup_model_cost_lamports']
        return s


def main():
    dip.COHORT=[COIN]
    dip.RULES=dict(dip.RULES,runtime_seconds=1800,first_token_account_cost_assumed_lamports=50000,pricing_venue='same_pool_PumpSwap_official_SDK_2.1.0',buy_output_haircut_fraction='0.005',sell_output_tolerance_percent='0.5',rent_model='RPC queried minimum deposit for token account length; recoverable asset, not trading expense',setup_network_model='50000 lamports once in addition to trade network assumptions')
    dip.Ledger=StreamLedger
    gate.quote=quote
    print('STREAM_FIXED_RULES '+json.dumps(dict(cohort=dip.COHORT,rules=dip.RULES,maximum_loss_guard_unchanged=True)),flush=True)
    dip.main()
    path=Path('dip-paper-result.json');r=json.loads(path.read_text())
    r['pricing_snapshot_count']=len(OBSERVATIONS)
    r['pricing_observations']=OBSERVATIONS
    r['limitations']=[x for x in r['limitations'] if not x.startswith(('Older liquid','Account setup modeled'))]+[
        'One preselected recent pool, not an unbiased sample and mint launch age not established.',
        'Own dip/rebound hypothesis, not a verified copy of the X author strategy.',
        'Both buy quantity and sell proceeds use a 0.5% adverse bound; this is not measured slippage.',
        'Each quote uses public same-pool reserves; hypothetical buys do not modify those reserves.',
        'Recoverable token-account rent is reported separately; refund requires an empty account and actual close, neither executed here.',
        'Setup and trade network fees are model assumptions; rent minimum is RPC queried, not an actual payment.',
        'No transactions constructed/simulated/signed/sent. Concentration and liquidity locking not fully audited.'
    ]
    path.write_text(json.dumps(r,indent=2));print('STREAM_PAPER_RESULT_JSON '+json.dumps(r),flush=True)

if __name__=='__main__':main()
