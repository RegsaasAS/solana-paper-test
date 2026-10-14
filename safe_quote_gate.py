"""Public, read-only feasibility gate. No browser, credentials or order APIs."""
import datetime as dt
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

SOL = 'So11111111111111111111111111111111111111112'
TOKEN_PROGRAM = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
TOKEN_2022_PROGRAM = 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'
AMOUNT_LAMPORTS = 50_000_000
MAX_IMMEDIATE_QUOTED_LOSS = 0.02
MAX_IMMEDIATE_QUOTED_LOSS_BPS = 200
ALLOWED_HOSTS = {'api.geckoterminal.com', 'transaction-v1.raydium.io', 'api.mainnet-beta.solana.com'}
MINT = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_public(url, payload=None):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
        raise ValueError('Endpoint outside public-data allowlist')
    if parsed.port not in (None,443) or parsed.fragment:
        raise ValueError('Unexpected endpoint port or fragment')
    paths={'api.geckoterminal.com':{'/api/v2/networks/solana/trending_pools'}, 'transaction-v1.raydium.io':{'/compute/swap-base-in'}, 'api.mainnet-beta.solana.com':{'','/'}}
    if parsed.path not in paths[parsed.hostname]:
        raise ValueError('Endpoint is not an approved read path')
    if payload is not None and (parsed.hostname != 'api.mainnet-beta.solana.com' or payload.get('method') != 'getAccountInfo'):
        raise ValueError('Only read-only mint lookup may use POST')
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={'Accept':'application/json', 'Content-Type':'application/json', 'User-Agent':'ReadOnlyPaperFeasibility/1.0'})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=8) as response:
        body = response.read(2_000_001)
        if len(body)>2_000_000:
            raise ValueError('Oversized data response')
        return json.loads(body)


def confirmed_standard_mint(mint):
    if not MINT.fullmatch(mint):
        raise ValueError('Invalid mint identifier')
    r = read_public('https://api.mainnet-beta.solana.com', {'jsonrpc':'2.0','id':1,'method':'getAccountInfo','params':[mint,{'encoding':'jsonParsed','commitment':'confirmed'}]})
    if r.get('error'):
        raise ValueError('Public RPC error: '+json.dumps(r['error']))
    value = r.get('result',{}).get('value')
    if not value:
        raise ValueError('Mint account missing from public RPC response')
    print('PUBLIC_MINT_OBSERVATION '+json.dumps({'mint':mint,'owner':value.get('owner'),'parsed':value.get('data',{}).get('parsed')}),flush=True)
    owner=value.get('owner')
    if owner not in (TOKEN_PROGRAM,TOKEN_2022_PROGRAM):
        raise ValueError('Unsupported token program: '+str(value.get('owner')))
    parsed = value.get('data',{}).get('parsed',{})
    info = parsed.get('info',{})
    if parsed.get('type')!='mint' or not {'mintAuthority','freezeAuthority','decimals','supply'} <= info.keys():
        raise ValueError('Mint safety fields not confirmed')
    if info['mintAuthority'] is not None or info['freezeAuthority'] is not None:
        raise ValueError('Mint or freeze authority remains enabled')
    if int(info['supply'])<=0 or not isinstance(info['decimals'],int):
        raise ValueError('Invalid mint supply/decimals')
    extension_names=[]
    if owner==TOKEN_2022_PROGRAM:
        extensions=info.get('extensions')
        if not isinstance(extensions,list):
            raise ValueError('Token-2022 extension inventory missing')
        for extension in extensions:
            name=extension.get('extension');state=extension.get('state')
            if name not in ('metadataPointer','tokenMetadata') or not isinstance(state,dict) or name in extension_names:
                raise ValueError('Unsupported, duplicated or unparsed Token-2022 extension: '+str(name))
            if name=='metadataPointer' and ('authority' not in state or state['authority'] is not None or state.get('metadataAddress')!=mint):
                raise ValueError('Metadata pointer not confirmed immutable and self-referencing')
            if name=='tokenMetadata' and ('updateAuthority' not in state or state['updateAuthority'] is not None or state.get('mint')!=mint):
                raise ValueError('Token metadata not confirmed immutable and matching')
            extension_names.append(name)
    return dict(decimals=info['decimals'],slot=r['result']['context']['slot'],mint_authority_revoked=True,freeze_authority_revoked=True,token_program=owner,permitted_extensions=extension_names)


def quote(input_mint, output_mint, amount):
    if not MINT.fullmatch(input_mint) or not MINT.fullmatch(output_mint) or int(amount)<=0:
        raise ValueError('Invalid quote parameters')
    params=urllib.parse.urlencode(dict(inputMint=input_mint,outputMint=output_mint,amount=str(amount),slippageBps=50,txVersion='V0'))
    began=time.monotonic()
    r=read_public('https://transaction-v1.raydium.io/compute/swap-base-in?'+params)
    if r.get('success') is not True:
        raise ValueError('Quote unavailable: '+str(r.get('msg','unknown')))
    q=r.get('data',{})
    if q.get('inputMint')!=input_mint or q.get('outputMint')!=output_mint or int(q.get('inputAmount',0))!=int(amount):
        raise ValueError('Quote identity/quantity mismatch')
    out=int(q.get('outputAmount',0)); floor=int(q.get('otherAmountThreshold',0))
    if not 0<floor<=out or not q.get('routePlan'):
        raise ValueError('Missing positive output, minimum or route')
    return dict(received_utc=dt.datetime.now(dt.timezone.utc).isoformat(),latency_seconds=round(time.monotonic()-began,3),quote=q)


def cost_allowed(sell_floor):
    # Integer comparison makes a quote exactly at the 2% ceiling deterministic.
    return int(sell_floor)*10000 >= AMOUNT_LAMPORTS*(10000-MAX_IMMEDIATE_QUOTED_LOSS_BPS)


def main():
    started=time.monotonic(); deadline=started+180
    cohort=[]; tested=[]; errors=[]
    try:
        r=read_public('https://api.geckoterminal.com/api/v2/networks/solana/trending_pools?duration=1h')
        seen=set()
        for p in r.get('data',[]):
            a=p['attributes'];rel=p['relationships']
            mint=rel['base_token']['data']['id'].split('_',1)[1]
            quote_mint=rel['quote_token']['data']['id'].split('_',1)[1]
            created=dt.datetime.fromisoformat(a['pool_created_at'].replace('Z','+00:00')).timestamp()
            age=(time.time()-created)/60
            if quote_mint==SOL and mint!=SOL and mint not in seen and MINT.fullmatch(mint) and 15<=age<=4320 and float(a.get('reserve_in_usd') or 0)>=12000:
                seen.add(mint)
                cohort.append(dict(mint=mint,pool=a['address'],name=a['name'],liquidity_usd=a['reserve_in_usd'],pool_age_minutes=round(age,2)))
        cohort=sorted(cohort,key=lambda x:x['pool'])[:5]
        print('QUOTE_GATE_COHORT '+json.dumps(cohort),flush=True)
        for c in cohort:
            if time.monotonic()+26>deadline:
                errors.append(dict(stage='time_budget',error='Remaining candidates not inspected'))
                break
            row=dict(candidate=c,passed=False)
            try:
                row['mint_checks']=confirmed_standard_mint(c['mint'])
            except Exception as exc:
                row['mint_error']=str(exc)
            # Reading a public quote has no trading side effects. A missing mint
            # check still prevents passage even if both quotes are available.
            try:
                row['buy_quote']=quote(SOL,c['mint'],AMOUNT_LAMPORTS)
                time.sleep(1)
                row['sell_quote']=quote(c['mint'],SOL,int(row['buy_quote']['quote']['otherAmountThreshold']))
            except Exception as exc:
                row['quote_error']=str(exc)
            row['data_gate_passed']='mint_checks' in row and 'buy_quote' in row and 'sell_quote' in row
            if 'buy_quote' in row and 'sell_quote' in row:
                sell_floor=int(row['sell_quote']['quote']['otherAmountThreshold'])
                row['immediate_quoted_minimum_return_fraction']=sell_floor/AMOUNT_LAMPORTS-1
                row['cost_gate_passed']=cost_allowed(sell_floor)
                if not row['cost_gate_passed']:
                    row['cost_rejection']='Quoted immediate liquidation loss exceeds 2% practical cost ceiling before unmodeled network/setup costs'
            row['passed']=row['data_gate_passed'] and row.get('cost_gate_passed',False)
            tested.append(row)
            print('QUOTE_GATE_CANDIDATE '+json.dumps(row),flush=True)
    except Exception as exc:
        errors.append(dict(stage='discovery',error=str(exc)))
    passed=[t for t in tested if t['passed']]
    data_passed=sum(t['data_gate_passed'] for t in tested)
    status='quote_gate_passed' if passed else ('blocked_by_quoted_costs' if data_passed else 'blocked_no_qualified_quotes')
    result=dict(purpose='read_only_size_specific_quote_and_mint_gate_not_execution_or_profit',status=status,cohort=cohort,tested=tested,errors=errors,passed_count=len(passed),data_gate_pass_count=data_passed,maximum_immediate_quoted_loss_fraction=MAX_IMMEDIATE_QUOTED_LOSS,two_way_quote_count=sum('buy_quote' in t and 'sell_quote' in t for t in tested),confirmed_mint_count=sum('mint_checks' in t for t in tested),reference_quote_amount_sol='0.05',elapsed_seconds=round(time.monotonic()-started,3),paper_trades=0,real_trades=0,accounts_created=0,credentials_used=False,limitations=['Trending-pool cohort is a data-feasibility sample, not an unbiased profitability sample.','Pool age is not verified token launch age.','Authority checks do not establish token or liquidity safety.','Token-2022 accepted only with explicit inventory containing at most immutable self-referencing metadata extensions.','Quotes are read-only estimates, not actual fills; sell quote does not incorporate a hypothetical buy changing pool state.','Network, priority and account creation costs are not evaluated at this gate.','The 2% cost ceiling is a practical test guard, not a demonstrated investment edge.'])
    pathlib.Path('safe-gate-result.json').write_text(json.dumps(result,indent=2))
    print('SAFE_GATE_JSON '+json.dumps(result),flush=True)


if __name__=='__main__':
    main()
