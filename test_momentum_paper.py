import unittest
import momentum_paper as m
class Momentum(unittest.TestCase):
    def bars(self):
        r=[dict(time=i*60,open='100',high='101',low='99',close='100',samples=6,max_gap=10) for i in range(6)]
        r[-1].update(open='105.5',high='106',low='105',close='106')
        return r
    def test_closed_breakout(self):self.assertTrue(m.signal(self.bars(),360)['eligible'])
    def test_live_bar_cannot_signal(self):self.assertFalse(m.signal(self.bars(),359)['eligible'])
    def test_momentum_and_last_minute_must_both_pass(self):
        r=self.bars();r[-1].update(open='106',close='106');self.assertFalse(m.signal(r,360)['eligible'])
        r=self.bars();r[2]['close']='105.5';self.assertFalse(m.signal(r,360)['eligible'])
    def test_previous_high_cannot_be_ignored(self):
        r=self.bars();r[0]['high']='107';self.assertFalse(m.signal(r,360)['eligible'])
    def test_gap_stale_and_sparse_rejected(self):
        r=self.bars();r[2]['time']+=60;self.assertEqual(m.signal(r,360)['reason'],'sampled_bar_gap')
        self.assertEqual(m.signal(self.bars(),451)['reason'],'stale_sampled_bar')
        r=self.bars();r[2]['samples']=3;self.assertEqual(m.signal(r,360)['reason'],'insufficient_samples')
if __name__=='__main__':unittest.main()
