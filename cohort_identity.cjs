'use strict';
const assert=require('node:assert/strict');
const {PublicKey}=require('@solana/web3.js');
const {NATIVE_MINT}=require('@solana/spl-token');
const {PUMP_AMM_SDK,PUMP_AMM_PROGRAM_ID}=require('@pump-fun/pump-swap-sdk');
const cohort=require('./cost-pool-cohort.json').filter(c=>c.name!=='Apple / SOL');
(async()=>{
 const response=await fetch('https://api.mainnet-beta.solana.com',{method:'POST',redirect:'error',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'getMultipleAccounts',params:[cohort.map(c=>c.pool),{encoding:'base64',commitment:'confirmed'}]}),signal:AbortSignal.timeout(10000)});
 assert(response.ok,'RPC HTTP '+response.status);
 const r=await response.json();assert(!r.error,JSON.stringify(r.error));assert(r.result.value.length===cohort.length);
 const rows=cohort.map((c,i)=>{
   const raw=r.result.value[i];assert(raw && raw.data[1]==='base64');
   const account={...raw,owner:new PublicKey(raw.owner),data:Buffer.from(raw.data[0],'base64')};
   if(!account.owner.equals(PUMP_AMM_PROGRAM_ID))return {candidate:c,program_owner:raw.owner,status:'unsupported_program'};
   const p=PUMP_AMM_SDK.decodePool(account),mint=new PublicKey(c.mint);
   const normal=p.baseMint.equals(mint)&&p.quoteMint.equals(NATIVE_MINT);
   const reversed=p.baseMint.equals(NATIVE_MINT)&&p.quoteMint.equals(mint);
   return {candidate:c,program_owner:raw.owner,account_bytes:account.data.length,chain_base_mint:p.baseMint.toBase58(),chain_quote_mint:p.quoteMint.toBase58(),normal,reversed,status:normal?'normal_pair':reversed?'reversed_pair':'different_pair'};
 });
 console.log('COHORT_IDENTITY_RESULT_JSON '+JSON.stringify({status:'completed',observed_utc:new Date().toISOString(),slot:r.result.context.slot,rows,real_trades:0,paper_trades:0}));
})().catch(e=>{console.error(e);process.exitCode=1;});
