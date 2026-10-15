'use strict';
const assert=require('node:assert/strict');
const {PublicKey}=require('@solana/web3.js');
const {unpackMint,unpackAccount,TOKEN_PROGRAM_ID,NATIVE_MINT}=require('@solana/spl-token');
const {PUMP_AMM_SDK,PUMP_AMM_PROGRAM_ID}=require('@pump-fun/pump-swap-sdk');
const cohort=require('./cost-pool-cohort.json').filter(c=>c.name!=='Apple / SOL');
let id=0;
async function rpc(method,params){
 assert(['getMultipleAccounts','getTokenLargestAccounts'].includes(method));
 const response=await fetch('https://api.mainnet-beta.solana.com',{method:'POST',redirect:'error',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:++id,method,params}),signal:AbortSignal.timeout(10000)});
 assert(response.ok,'RPC HTTP '+response.status);const p=await response.json();assert(!p.error,JSON.stringify(p.error));return p.result;
}
function account(x){assert(x&&x.data[1]==='base64');return {...x,owner:new PublicKey(x.owner),data:Buffer.from(x.data[0],'base64')};}
(async()=>{
 const result=await rpc('getMultipleAccounts',[cohort.flatMap(c=>[c.pool,c.mint]),{encoding:'base64',commitment:'confirmed'}]);
 const specs=cohort.map((c,i)=>{
  const pa=account(result.value[i*2]),ma=account(result.value[i*2+1]);assert(pa.owner.equals(PUMP_AMM_PROGRAM_ID)&&ma.owner.equals(TOKEN_PROGRAM_ID));
  const p=PUMP_AMM_SDK.decodePool(pa);assert(p.baseMint.equals(NATIVE_MINT)&&p.quoteMint.toBase58()===c.mint);
  const mint=unpackMint(new PublicKey(c.mint),ma,TOKEN_PROGRAM_ID);
  assert(mint.mintAuthority===null&&mint.freezeAuthority===null);
  return {candidate:c,supply:mint.supply,vault:p.poolQuoteTokenAccount};
 });
 const allVaults=new Set(specs.map(x=>x.vault.toBase58()));
 const v=await rpc('getMultipleAccounts',[specs.map(x=>x.vault.toBase58()),{encoding:'base64',commitment:'confirmed',minContextSlot:result.context.slot}]);
 const rows=[];
 for(let i=0;i<specs.length;i++){
  const s=specs[i],a=unpackAccount(s.vault,account(v.value[i]),TOKEN_PROGRAM_ID);
  assert(a.mint.toBase58()===s.candidate.mint&&a.owner.toBase58()===s.candidate.pool);
  const row={candidate:s.candidate,mint_supply_atoms:s.supply.toString(),verified_pool_vault:s.vault.toBase58(),pool_vault_amount_atoms:a.amount.toString(),pool_vault_fraction:Number(a.amount)/Number(s.supply),outside_known_pool_fraction:1-Number(a.amount)/Number(s.supply),vault_slot:v.context.slot};
  try{
   const top=await rpc('getTokenLargestAccounts',[s.candidate.mint,{commitment:'confirmed'}]);
   row.largest_accounts_slot=top.context.slot;row.largest_accounts=top.value.map(x=>({...x,known_pool_vault:allVaults.has(x.address)}));
   row.top10_raw_fraction=Number(top.value.slice(0,10).reduce((a,x)=>a+BigInt(x.amount),0n))/Number(s.supply);
   row.top10_non_known_pool_token_accounts_fraction=Number(top.value.filter(x=>!allVaults.has(x.address)).slice(0,10).reduce((a,x)=>a+BigInt(x.amount),0n))/Number(s.supply);
  }catch(e){row.largest_accounts_error=String(e);}
  rows.push(row);console.log('HOLDER_CHAIN_ROW '+JSON.stringify(row));
  await new Promise(r=>setTimeout(r,3000));
 }
 console.log('HOLDER_CHAIN_RESULT_JSON '+JSON.stringify({status:'completed',observed_utc:new Date().toISOString(),rows,real_trades:0,paper_trades:0,limitations:['Mint supply and pool-vault balances can be from different slots.','Only listed pool vaults classified; other accounts are unclassified, not established individual people.','Token-account concentration is not common-beneficial-owner concentration.','Pool-vault classification does not establish liquidity locking, LP ownership, organic activity or safety.']}));
})().catch(e=>{console.error(e);process.exitCode=1;});
