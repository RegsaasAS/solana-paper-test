import unittest
from unittest.mock import patch
import safe_quote_gate as gate

TOKEN='BTqaTmgeQUHib8WYW44u7eiASjA3szmRPxBeX4oZpump'


def mint_reply(info):
    return {'result':{'context':{'slot':123},'value':{'owner':gate.TOKEN_PROGRAM,'data':{'parsed':{'type':'mint','info':info}}}}}


def good_quote():
    return {'success':True,'data':{'inputMint':gate.SOL,'outputMint':TOKEN,'inputAmount':'50000000','outputAmount':'1000000','otherAmountThreshold':'995000','routePlan':[{'poolId':'example'}]}}


class SafetyBoundaries(unittest.TestCase):
    def test_quote_at_exact_cost_ceiling_accepted(self):
        self.assertTrue(gate.cost_allowed(49_000_000))

    def test_quote_above_cost_ceiling_rejected(self):
        self.assertFalse(gate.cost_allowed(48_999_999))

    def test_observed_high_cost_quote_rejected(self):
        self.assertFalse(gate.cost_allowed(47_101_687))

    def test_untrusted_and_plain_http_endpoints_rejected_without_network(self):
        with patch.object(gate.urllib.request,'build_opener') as opener:
            for url in ('https://attacker.example/collect','http://api.geckoterminal.com/api/v2/networks/solana/trending_pools','https://api.geckoterminal.com.attacker.example/x','https://secret@api.geckoterminal.com/api/v2/networks/solana/trending_pools'):
                with self.assertRaises(ValueError): gate.read_public(url)
            opener.assert_not_called()

    def test_transaction_paths_rejected(self):
        with self.assertRaises(ValueError): gate.read_public('https://transaction-v1.raydium.io/transaction/swap-base-in')

    def test_onchain_send_rejected(self):
        with self.assertRaises(ValueError): gate.read_public('https://api.mainnet-beta.solana.com',{'method':'sendTransaction'})

    def test_missing_authority_fields_rejected(self):
        with patch.object(gate,'read_public',return_value=mint_reply({'decimals':6,'supply':'100'})):
            with self.assertRaises(ValueError): gate.confirmed_standard_mint(TOKEN)

    def test_active_freeze_authority_rejected(self):
        with patch.object(gate,'read_public',return_value=mint_reply({'decimals':6,'supply':'100','mintAuthority':None,'freezeAuthority':'active'})):
            with self.assertRaises(ValueError): gate.confirmed_standard_mint(TOKEN)

    def test_confirmed_revoked_authorities_accepted(self):
        with patch.object(gate,'read_public',return_value=mint_reply({'decimals':6,'supply':'100','mintAuthority':None,'freezeAuthority':None})):
            self.assertTrue(gate.confirmed_standard_mint(TOKEN)['freeze_authority_revoked'])

    def test_unsupported_token_program_rejected(self):
        r=mint_reply({'decimals':6,'supply':'100','mintAuthority':None,'freezeAuthority':None})
        r['result']['value']['owner']='unsupported'
        with patch.object(gate,'read_public',return_value=r):
            with self.assertRaises(ValueError): gate.confirmed_standard_mint(TOKEN)

    def test_token2022_missing_inventory_rejected(self):
        r=mint_reply({'decimals':6,'supply':'100','mintAuthority':None,'freezeAuthority':None})
        r['result']['value']['owner']=gate.TOKEN_2022_PROGRAM
        with patch.object(gate,'read_public',return_value=r):
            with self.assertRaises(ValueError): gate.confirmed_standard_mint(TOKEN)

    def test_permanent_delegate_and_transfer_hook_rejected(self):
        for name in ('permanentDelegate','transferHook','transferFeeConfig','pausable','unrecognized'):
            r=mint_reply({'decimals':6,'supply':'100','mintAuthority':None,'freezeAuthority':None,'extensions':[{'extension':name,'state':{}}]})
            r['result']['value']['owner']=gate.TOKEN_2022_PROGRAM
            with patch.object(gate,'read_public',return_value=r):
                with self.assertRaises(ValueError): gate.confirmed_standard_mint(TOKEN)

    def test_immutable_metadata_only_accepted(self):
        extensions=[{'extension':'metadataPointer','state':{'authority':None,'metadataAddress':TOKEN}},{'extension':'tokenMetadata','state':{'updateAuthority':None,'mint':TOKEN}}]
        r=mint_reply({'decimals':6,'supply':'100','mintAuthority':None,'freezeAuthority':None,'extensions':extensions})
        r['result']['value']['owner']=gate.TOKEN_2022_PROGRAM
        with patch.object(gate,'read_public',return_value=r):
            self.assertEqual(len(gate.confirmed_standard_mint(TOKEN)['permitted_extensions']),2)

    def test_mutable_metadata_rejected(self):
        extensions=[{'extension':'metadataPointer','state':{'authority':'active','metadataAddress':TOKEN}}]
        r=mint_reply({'decimals':6,'supply':'100','mintAuthority':None,'freezeAuthority':None,'extensions':extensions})
        r['result']['value']['owner']=gate.TOKEN_2022_PROGRAM
        with patch.object(gate,'read_public',return_value=r):
            with self.assertRaises(ValueError): gate.confirmed_standard_mint(TOKEN)

    def test_wrong_quote_asset_rejected(self):
        r=good_quote();r['data']['outputMint']=gate.SOL
        with patch.object(gate,'read_public',return_value=r):
            with self.assertRaises(ValueError): gate.quote(gate.SOL,TOKEN,50000000)

    def test_wrong_quote_size_rejected(self):
        r=good_quote();r['data']['inputAmount']='1'
        with patch.object(gate,'read_public',return_value=r):
            with self.assertRaises(ValueError): gate.quote(gate.SOL,TOKEN,50000000)

    def test_zero_minimum_output_rejected(self):
        r=good_quote();r['data']['otherAmountThreshold']='0'
        with patch.object(gate,'read_public',return_value=r):
            with self.assertRaises(ValueError): gate.quote(gate.SOL,TOKEN,50000000)

    def test_positive_matching_quote_accepted(self):
        with patch.object(gate,'read_public',return_value=good_quote()):
            self.assertEqual(gate.quote(gate.SOL,TOKEN,50000000)['quote']['outputAmount'],'1000000')


if __name__=='__main__':
    unittest.main()
