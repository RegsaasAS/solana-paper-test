import unittest
import fresh_paper_window as s
import dip_paper as d
class Ledger(unittest.TestCase):
    def setUp(self):
        self.old=d.RULES
        d.RULES=dict(d.RULES,first_token_account_cost_assumed_lamports=50000)
    def tearDown(self):d.RULES=self.old
    def quotes(self,proceeds=49_300_000):
        buy=dict(snapshot={'refundable_rent_deposit_lamports':2074080},quote=dict(inputMint=d.gate.SOL,outputMint=s.COIN['mint'],inputAmount=50000000,otherAmountThreshold=1000))
        sell=dict(quote=dict(inputMint=s.COIN['mint'],outputMint=d.gate.SOL,inputAmount=1000,otherAmountThreshold=proceeds))
        return buy,sell
    def test_rent_is_asset_not_profit_or_expense(self):
        b=s.StreamLedger();buy,sell=self.quotes();self.assertTrue(b.enter(s.COIN,buy,sell,0));b.close(sell,'test');r=b.summary('completed')
        self.assertEqual(r['cash_lamports'],997075920)
        self.assertEqual(r['full_portfolio_net_pnl_lamports'],-850000)
        self.assertEqual(r['recoverable_account_rent_lamports'],2074080)
        self.assertEqual(r['cash_lamports'],10**9+sum(e['cash_change_lamports'] for e in r['events']))
        b.enter(s.COIN,buy,sell,400);b.close(sell,'test');r=b.summary('completed')
        self.assertEqual(r['recoverable_account_rent_lamports'],2074080)
        self.assertEqual(r['account_setup_model_cost_lamports'],50000)
        self.assertEqual(r['full_portfolio_net_pnl_lamports'],-1650000)
    def test_reject_cost_before_any_cash_change(self):
        b=s.StreamLedger();buy,sell=self.quotes(48_900_000)
        self.assertFalse(b.enter(s.COIN,buy,sell,0));self.assertEqual(b.events,[])
    def test_unknown_open_position_value_is_unknown(self):
        b=s.StreamLedger();buy,sell=self.quotes();b.enter(s.COIN,buy,sell,0)
        self.assertIsNone(b.summary('unresolved_position')['full_portfolio_net_pnl_lamports'])
if __name__=='__main__':unittest.main()
