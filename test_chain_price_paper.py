import unittest
import chain_price_paper as c
from test_dip_paper import bars
class ChainPrice(unittest.TestCase):
    def sample_bars(self):return [dict(time=int(r[0]),open=str(r[1]),high=str(r[2]),low=str(r[3]),close=str(r[4]),samples=6,max_gap=10) for r in bars()]
    def test_signal_uses_closed_sampled_prices(self):
        r=self.sample_bars();self.assertTrue(c.signal(r,1560)['eligible'])
        self.assertFalse(c.signal(r,1559)['eligible'])
    def test_insufficient_sampling_not_volume(self):
        r=self.sample_bars();r[-1]['samples']=3;self.assertEqual(c.signal(r,1560)['reason'],'insufficient_samples')
        r[-1]['samples']=6;r[4]['max_gap']=30;self.assertEqual(c.signal(r,1560)['reason'],'insufficient_samples')
    def test_stale_context_rejected(self):
        s=dict(pool=c.C['pool'],mint=c.C['mint'],slot=10,buy={'base':'100'})
        c.validate_snapshot(s,9)
        with self.assertRaises(ValueError):c.validate_snapshot(s,10)
    def test_cost_boundary_includes_network(self):
        self.assertFalse(c.immediate_cost_passes({'sell':{'minQuote':'49098999'}}))
        self.assertTrue(c.immediate_cost_passes({'sell':{'minQuote':'49099000'}}))
if __name__=='__main__':unittest.main()
