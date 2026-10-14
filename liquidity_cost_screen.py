"""One final public cost screen; changes sampling, never trading permissions."""
import datetime as dt
import json
import pathlib
import time
import safe_quote_gate as gate


def main():
    started=time.monotonic();deadline=started+180
    available={};errors=[];tested=[]
    for page in (1,2):
        if page>1:
            time.sleep(7)
        try:
            r=gate.read_public('https://api.geckoterminal.com/api/v2/networks/solana/trending_pools?duration=1h&page='+str(page))
            for p in r.get('data',[]):
                a=p['attributes'];rel=p['relationships']
                mint=rel['base_token']['data']['id'].split('_',1)[1]
                quote_mint=rel['quote_token']['data']['id'].split('_',1)[1]
                created=dt.datetime.fromisoformat(a['pool_created_at'].replace('Z','+00:00')).timestamp()
                age=(time.time()-created)/60
                liquidity=float(a.get('reserve_in_usd') or 0)
                symbol=a.get('name','').split(' / ')[0].upper()
                if quote_mint!=gate.SOL or mint==gate.SOL or not gate.MINT.fullmatch(mint) or age<15 or liquidity<100000 or symbol in ('USDC','USDT','WSOL','SOL'):
                    continue
                candidate=dict(mint=mint,pool=a['address'],name=a['name'],liquidity_usd=a['reserve_in_usd'],pool_age_minutes=round(age,2))
                if mint not in available or liquidity>float(available[mint]['liquidity_usd']):
                    available[mint]=candidate
        except Exception as exc:
            errors.append(dict(stage='discovery',page=page,error=str(exc)))
    cohort=sorted(available.values(),key=lambda c:(-float(c['liquidity_usd']),c['mint']))[:10]
    print('LIQUIDITY_COHORT '+json.dumps(cohort),flush=True)
    for c in cohort:
        if time.monotonic()+27>deadline:
            errors.append(dict(stage='time_budget',error='Uninspected candidates remain'))
            break
        row=dict(candidate=c,passed=False)
        try:
            row['mint_checks']=gate.confirmed_standard_mint(c['mint'])
        except Exception as exc:
            row['mint_error']=str(exc)
        try:
            row['buy_quote']=gate.quote(gate.SOL,c['mint'],gate.AMOUNT_LAMPORTS)
            time.sleep(1)
            row['sell_quote']=gate.quote(c['mint'],gate.SOL,int(row['buy_quote']['quote']['otherAmountThreshold']))
            floor=int(row['sell_quote']['quote']['otherAmountThreshold'])
            row['quoted_minimum_change_fraction']=floor/gate.AMOUNT_LAMPORTS-1
            row['cost_gate_passed']=gate.cost_allowed(floor)
            row['passed']='mint_checks' in row and row['cost_gate_passed']
        except Exception as exc:
            row['quote_error']=str(exc)
        tested.append(row)
        print('LIQUIDITY_CANDIDATE '+json.dumps(row),flush=True)
        time.sleep(1)
    result=dict(purpose='broader_public_cost_feasibility_not_strategy_or_trade_performance',status='feasible_quote_found' if any(t['passed'] for t in tested) else 'no_feasible_quote_in_sample',cohort=cohort,tested=tested,errors=errors,passed_count=sum(t['passed'] for t in tested),two_way_quote_count=sum('buy_quote' in t and 'sell_quote' in t for t in tested),reference_amount_sol='0.05',maximum_quoted_loss_fraction=gate.MAX_IMMEDIATE_QUOTED_LOSS,elapsed_seconds=round(time.monotonic()-started,3),maximum_runtime_seconds=180,paper_trades=0,real_trades=0,credentials_used=False,selection='First two Solana trending pages, SOL quote, pool age>=15m, liquidity>=100000 USD, largest pool per mint, top ten by current liquidity; cohort frozen before quote observations.',limitations=['Broader sampling includes older tokens, unlike the original launch-focused guide.','Token purpose and memecoin classification not independently verified.','Not an unbiased performance sample; no strategy or returns tested.','Quotes do not incorporate a hypothetical first swap changing pool state.','Network, priority, account setup, failures and actual fills not evaluated.','Authority and extension checks are a limited profile, not a token or liquidity audit.'])
    pathlib.Path('liquidity-cost-result.json').write_text(json.dumps(result,indent=2))
    print('LIQUIDITY_COST_JSON '+json.dumps(result),flush=True)


if __name__=='__main__':
    main()
