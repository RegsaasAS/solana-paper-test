import unittest
import dip_paper as d
C=d.COHORT[0]
def bars():
    r=[[600+i*60,100,101,99,100,10] for i in range(16)]
    r[2][2]=110;r[14]=[1440,100,100,98,98,10];r[15]=[1500,98.4,99.2,98.3,99,10]
    return r
def quotes(f=49_300_000,q=1_000_000):
    return ({'quote':dict(inputMint=d.gate.SOL,outputMint=C['mint'],inputAmount=50_000_000,otherAmountThreshold=q)}, {'quote':dict(inputMint=C['mint'],outputMint=d.gate.SOL,inputAmount=q,otherAmountThreshold=f)})
class Signal(unittest.TestCase):
    def test_closed_rebound(self):self.assertTrue(d.inspect(bars(),1560)['eligible'])
    def test_live_bar_excluded(self):
        r=bars();r[-1][4]=98;r.append([1560,98,102,98,101,10])
        self.assertFalse(d.inspect(r,1590)['eligible'])
    def test_stale_and_gap(self):
        self.assertEqual(d.inspect(bars(),1651)['reason'],'stale_bar')
        r=bars();r[7][0]+=1;self.assertEqual(d.inspect(r,1560)['reason'],'bar_gap')
    def test_nonfinite(self):
        r=bars();r[2][2]='NaN'
        with self.assertRaises(ValueError):d.inspect(r,1560)
    def test_no_dip(self):
        r=bars();r[2][2]=101;r[14][4]=99;self.assertFalse(d.inspect(r,1560)['eligible'])
class Accounting(unittest.TestCase):
    def test_full_cost_conservation(self):
        b=d.Ledger();buy,sell=quotes();self.assertTrue(b.enter(C,buy,sell,0));b.close(sell,'test')
        s=b.summary('completed');self.assertEqual(s['cash_lamports'],996_200_000)
        self.assertEqual(s['cash_lamports'],1_000_000_000+sum(e['cash_change_lamports'] for e in s['events']))
        self.assertEqual(s['full_portfolio_net_pnl_lamports'],-3_800_000)
    def test_setup_once(self):
        b=d.Ledger();buy,sell=quotes()
        for i in range(2):b.enter(C,buy,sell,i*400);b.close(sell,'test')
        self.assertEqual(b.summary('completed')['account_setup_model_cost_lamports'],3_000_000)
    def test_boundary_includes_network_cost(self):
        b=d.Ledger();buy,sell=quotes(49_098_999);self.assertFalse(b.enter(C,buy,sell,0));self.assertEqual(b.events,[])
        buy,sell=quotes(49_099_000);self.assertTrue(b.enter(C,buy,sell,0))
    def test_bad_quote_no_mutation(self):
        for kind in ('zero','size','output'):
            b=d.Ledger();buy,sell=quotes()
            if kind=='zero':buy['quote']['otherAmountThreshold']=0
            elif kind=='size':sell['quote']['inputAmount']=1
            else:sell['quote']['outputMint']='wrong'
            with self.assertRaises(ValueError):b.enter(C,buy,sell,0)
            self.assertEqual(b.cash,1_000_000_000);self.assertEqual(b.events,[])
    def test_single_position(self):
        b=d.Ledger();buy,sell=quotes();b.enter(C,buy,sell,0)
        with self.assertRaises(ValueError):b.enter(C,buy,sell,10)
    def test_exit_rules(self):
        b=d.Ledger();buy,sell=quotes();b.enter(C,buy,sell,0)
        self.assertIsNone(b.exit_reason(sell,299));self.assertEqual(b.exit_reason(sell,300),'five_minute_exit')
        _,sell=quotes(48_000_000);self.assertEqual(b.exit_reason(sell,10),'net_stop_loss')
        _,sell=quotes(52_000_000);self.assertEqual(b.exit_reason(sell,10),'net_take_profit')
    def test_unresolved_no_fake_profit(self):
        b=d.Ledger();buy,sell=quotes();b.enter(C,buy,sell,0)
        self.assertIsNone(b.summary('unresolved_position')['full_portfolio_net_pnl_lamports'])
        self.assertEqual(b.summary('unresolved_position',sell)['full_portfolio_net_pnl_lamports'],-3_800_000)
if __name__=='__main__':unittest.main()
