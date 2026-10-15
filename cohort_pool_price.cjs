'use strict';
// Public account reads and offline pricing only. No wallet, Connection or instruction builders.
const assert = require('node:assert/strict');
const BN = require('bn.js');
const {PublicKey} = require('@solana/web3.js');
const {unpackMint,unpackAccount,getExtensionTypes,getAccountLen,ExtensionType,TOKEN_PROGRAM_ID,TOKEN_2022_PROGRAM_ID,NATIVE_MINT} = require('@solana/spl-token');
const {PUMP_AMM_SDK,PUMP_AMM_PROGRAM_ID,PUMP_FEE_PROGRAM_ID,GLOBAL_CONFIG_PDA,PUMP_AMM_FEE_CONFIG_PDA,buyQuoteInput,buyBaseInput,sellBaseInput,computeFeesBps} = require('@pump-fun/pump-swap-sdk');
const POOL=new PublicKey(process.argv[3]);
const MINT=new PublicKey(process.argv[4]);
let requests=0;
async function rpc(method,params){
  assert(['getAccountInfo','getMultipleAccounts','getMinimumBalanceForRentExemption'].includes(method));
  const response=await fetch('https://api.mainnet-beta.solana.com',{method:'POST',redirect:'error',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:++requests,method,params}),signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw Error('Public RPC HTTP '+response.status);
  const p=await response.json();if(p.error)throw Error(JSON.stringify(p.error));return p.result;
}
function account(v){
  assert(v && v.data[1]==='base64');
  return {...v,owner:new PublicKey(v.owner),data:Buffer.from(v.data[0],'base64')};
}
function encoded(obj){return Object.fromEntries(Object.entries(obj).map(([k,v])=>[k,BN.isBN(v)?v.toString():v]));}
async function snapshot(sellQuantity=null){
  const first=await rpc('getAccountInfo',[POOL.toBase58(),{encoding:'base64',commitment:'confirmed'}]);
  const initial=account(first.value);assert(initial.owner.equals(PUMP_AMM_PROGRAM_ID));
  const initialPool=PUMP_AMM_SDK.decodePool(initial);
  const reversed=initialPool.baseMint.equals(NATIVE_MINT)&&initialPool.quoteMint.equals(MINT);
  assert(reversed || (initialPool.baseMint.equals(MINT)&&initialPool.quoteMint.equals(NATIVE_MINT)));
  const keys=[POOL,GLOBAL_CONFIG_PDA,PUMP_AMM_FEE_CONFIG_PDA,MINT,initialPool.poolBaseTokenAccount,initialPool.poolQuoteTokenAccount,NATIVE_MINT];
  const result=await rpc('getMultipleAccounts',[keys.map(k=>k.toBase58()),{encoding:'base64',commitment:'confirmed',minContextSlot:first.context.slot}]);
  const [pa,ga,fa,ma,ba,qa,wa]=result.value.map(account);
  assert(pa.owner.equals(PUMP_AMM_PROGRAM_ID) && ga.owner.equals(PUMP_AMM_PROGRAM_ID) && fa.owner.equals(PUMP_FEE_PROGRAM_ID));
  assert(ma.owner.equals(TOKEN_PROGRAM_ID)||ma.owner.equals(TOKEN_2022_PROGRAM_ID));
  const pool=PUMP_AMM_SDK.decodePool(pa),globalConfig=PUMP_AMM_SDK.decodeGlobalConfig(ga),feeConfig=PUMP_AMM_SDK.decodeFeeConfig(fa);
  assert(pool.baseMint.equals(initialPool.baseMint)&&pool.quoteMint.equals(initialPool.quoteMint));
  assert(pool.poolBaseTokenAccount.equals(keys[4])&&pool.poolQuoteTokenAccount.equals(keys[5]));
  assert((globalConfig.disableFlags&24)===0,'Pool program has buys or sells disabled');
  const mint=unpackMint(MINT,ma,ma.owner);
  assert(mint.isInitialized && mint.mintAuthority===null && mint.freezeAuthority===null);
  const extensions=getExtensionTypes(mint.tlvData);
  assert(extensions.every(t=>[ExtensionType.MetadataPointer,ExtensionType.TokenMetadata].includes(t)),'Unsupported mint extension');
  const base=unpackAccount(keys[4],ba,reversed?TOKEN_PROGRAM_ID:ma.owner),quote=unpackAccount(keys[5],qa,reversed?ma.owner:TOKEN_PROGRAM_ID);
  assert(base.mint.equals(pool.baseMint)&&quote.mint.equals(pool.quoteMint));
  const pricingBaseMint=reversed?unpackMint(NATIVE_MINT,wa,TOKEN_PROGRAM_ID):mint;
  assert(base.owner.equals(POOL)&&quote.owner.equals(POOL));
  const baseReserve=new BN(base.amount.toString()),quoteReserve=new BN(quote.amount.toString());
  const effective=quoteReserve.add(pool.virtualQuoteReserves),buckets=pool.protocolFees.add(pool.creatorFees);
  assert(baseReserve.gtn(0)&&effective.gtn(0)&&quoteReserve.gte(buckets));
  const args={baseReserve,quoteReserve,virtualQuoteReserves:pool.virtualQuoteReserves,feeBucketsTotal:buckets,globalConfig,feeConfig,baseMintAccount:pricingBaseMint,baseMint:pool.baseMint,coinCreator:pool.coinCreator,creator:pool.creator,quoteMint:pool.quoteMint,isMayhemMode:pool.isMayhemMode,creatorFeeBps:pool.creatorFeeBps};
  const amount=new BN(50000000);
  let buy,exactBuy,sell,conservativeBuyQuantity;
  if(!reversed){
    buy=buyQuoteInput({...args,quote:amount,slippage:0});
    exactBuy=buyBaseInput({...args,base:buy.base,slippage:0});
    conservativeBuyQuantity=buy.base.muln(995).divn(1000);
    sell=sellBaseInput({...args,base:sellQuantity===null?conservativeBuyQuantity:new BN(sellQuantity),slippage:0.5});
  }else{
    const rawBuy=sellBaseInput({...args,base:amount,slippage:0.5});
    buy={base:rawBuy.uiQuote,rawSellBaseInput:encoded(rawBuy)};
    conservativeBuyQuantity=rawBuy.minQuote;
    exactBuy={not_applicable:'SOL is pool base, acquired token is pool quote'};
    const rawSell=buyQuoteInput({...args,quote:sellQuantity===null?conservativeBuyQuantity:new BN(sellQuantity),slippage:0});
    sell={uiQuote:rawSell.base,minQuote:rawSell.base.muln(995).divn(1000),rawBuyQuoteInput:encoded(rawSell)};
  }
  assert(buy.base.gtn(0)&&conservativeBuyQuantity.gtn(0));
  assert(sell.uiQuote.gtn(0)&&sell.minQuote.lte(sell.uiQuote));
  const fees=computeFeesBps({globalConfig,feeConfig,creator:pool.creator,baseMintSupply:new BN(pricingBaseMint.supply.toString()),baseMint:pool.baseMint,baseReserve,quoteReserve:effective,quoteMint:pool.quoteMint,isMayhemMode:pool.isMayhemMode,creatorFeeBps:pool.creatorFeeBps});
  const tokenAccountBytes=getAccountLen(ma.owner.equals(TOKEN_2022_PROGRAM_ID)?[ExtensionType.ImmutableOwner]:[]);
  const deposit=await rpc("getMinimumBalanceForRentExemption",[tokenAccountBytes,{commitment:"confirmed"}]);
  assert(Number.isSafeInteger(deposit)&&deposit>0);
  return {pool_orientation:reversed?'SOL_base_token_quote':'token_base_SOL_quote',conservative_buy_quantity_atoms:conservativeBuyQuantity.toString(), token_account_bytes:tokenAccountBytes, refundable_rent_deposit_lamports:deposit, sell_quantity_atoms:(sellQuantity===null?conservativeBuyQuantity:new BN(sellQuantity)).toString(), observed_utc:new Date().toISOString(),slot:result.context.slot,all_quote_accounts_same_slot:true,pool:POOL.toBase58(),mint:MINT.toBase58(),pool_account_bytes:pa.data.length,base_reserve_atoms:baseReserve.toString(),raw_quote_reserve_lamports:quoteReserve.toString(),signed_virtual_quote_reserves:pool.virtualQuoteReserves.toString(),effective_quote_reserve_lamports:effective.toString(),fee_buckets_lamports:buckets.toString(),mint_extensions:extensions.map(x=>ExtensionType[x]),reported_fee_bps:encoded(fees),creator_fee_has_recipient:!pool.coinCreator.equals(PublicKey.default),is_mayhem_mode:pool.isMayhemMode,input_lamports:amount.toString(),buy:encoded(buy),exact_base_buy:encoded(exactBuy),sell:encoded(sell),same_frozen_state_expected_roundtrip_change_lamports:sell.uiQuote.sub(amount).toString(),same_frozen_state_stressed_sell_change_lamports:sell.minQuote.sub(amount).toString(),assumed_network_lamports_per_side:50000,expected_same_quantity_with_network_change_lamports:sell.uiQuote.sub(amount).subn(100000).toString(),stressed_sell_same_quantity_with_network_change_lamports:sell.minQuote.sub(amount).subn(100000).toString()};
}
module.exports={snapshot};
if(require.main===module){
 const qty=process.argv[2];
 if(qty!=="buy"&&!/^[1-9][0-9]{0,24}$/.test(qty||""))throw Error("Expected buy or positive sell quantity");
 snapshot(qty==="buy"?null:qty).then(x=>console.log("STREAM_SNAPSHOT_JSON "+JSON.stringify(x))).catch(e=>{console.error(e);process.exitCode=1;});
}
