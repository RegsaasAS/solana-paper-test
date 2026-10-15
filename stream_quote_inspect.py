"""Inspect pinned official package as data; execute none of its code."""
import base64,hashlib,io,json,tarfile,urllib.parse,urllib.request
import safe_quote_gate as gate
POOL='D9NCkN3unPTVLtA56Y68J2cXisje9yyYe61gMM2HCHwJ'
MINT='9a98oQHtxfqmr4EyzsP6wfw69uYAK3JbUeVEuNW1pump'
VERSION='2.1.0'
def registry_read(url,limit):
    p=urllib.parse.urlparse(url)
    if p.scheme!='https' or p.hostname!='registry.npmjs.org' or p.username or p.password or p.port not in (None,443):raise ValueError('Registry outside fixed scope')
    with urllib.request.build_opener(gate.NoRedirect).open(urllib.request.Request(url,headers={'User-Agent':'ReadOnlySdkInspection/1.0'}),timeout=12) as response:
        data=response.read(limit+1)
        if len(data)>limit:raise ValueError('Response too large')
        return data

def main():
    r=dict(pool=POOL,mint=MINT,errors=[],package_code_executed=False,transactions_built=0,real_trades=0)
    try:
        p=gate.read_public('https://api.mainnet-beta.solana.com',dict(jsonrpc='2.0',id=1,method='getAccountInfo',params=[POOL,dict(encoding='base64',commitment='confirmed')]))
        v=p['result']['value']
        if not v:raise ValueError('Pool missing')
        data=base64.b64decode(v['data'][0],validate=True)
        r['pool_account']=dict(owner=v['owner'],slot=p['result']['context']['slot'],bytes=len(data),data_base64=v['data'][0],pump_program_matches=v['owner']=='pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA')
        r['mint_checks']=gate.confirmed_standard_mint(MINT)
    except Exception as exc:r['errors'].append(dict(stage='chain',error=str(exc)))
    try:
        m=json.loads(registry_read('https://registry.npmjs.org/@pump-fun%2fpump-swap-sdk/'+VERSION,1000000))
        if m['name']!='@pump-fun/pump-swap-sdk' or m['version']!=VERSION:raise ValueError('Package identity mismatch')
        url=m['dist']['tarball']
        if urllib.parse.urlparse(url).path!='/@pump-fun/pump-swap-sdk/-/pump-swap-sdk-'+VERSION+'.tgz':raise ValueError('Unexpected tarball path')
        blob=registry_read(url,20000000);integrity='sha512-'+base64.b64encode(hashlib.sha512(blob).digest()).decode()
        if integrity!=m['dist']['integrity']:raise ValueError('Integrity mismatch')
        files={}
        with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as archive:
            for member in archive.getmembers():
                if member.isfile() and member.size<1000000 and member.name.endswith(('.d.ts','README.md')):
                    files[member.name]=archive.extractfile(member).read().decode('utf-8','replace')
        r['package']=dict(name=m['name'],version=m['version'],registry_integrity=integrity,tarball_sha256=hashlib.sha256(blob).hexdigest(),dependencies=m.get('dependencies'),review=files)
    except Exception as exc:r['errors'].append(dict(stage='package',error=str(exc)))
    r['status']='completed' if not r['errors'] else 'partial'
    print('STREAM_INSPECT_RESULT_JSON '+json.dumps(r),flush=True)
if __name__=='__main__':main()
