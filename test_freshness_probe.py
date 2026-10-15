import unittest
from freshness_probe import observation
from test_dip_paper import bars
class Heartbeat(unittest.TestCase):
    def test_same_bar_becoming_stale_is_visible(self):
        first=observation(bars(),1560,None)
        stale=observation(bars(),1800,first['latest_closed_bar_time'])
        self.assertTrue(first['usable']);self.assertFalse(stale['usable'])
        self.assertTrue(stale['repeated']);self.assertEqual(stale['reason'],'stale_bar')
        self.assertEqual(stale['age_after_close_seconds'],240)
    def test_forward_and_backward_timestamps(self):
        self.assertTrue(observation(bars(),1560,1440)['advanced'])
        self.assertFalse(observation(bars(),1560,1560)['advanced'])
if __name__=='__main__':unittest.main()
