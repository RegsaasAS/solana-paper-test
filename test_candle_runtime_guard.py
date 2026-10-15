import unittest
from unittest.mock import patch
import candle_runtime_guard as g
from test_dip_paper import bars
class RuntimeGuard(unittest.TestCase):
    def setUp(self):g.POLLS.clear()
    def test_same_bar_later_stale_is_logged_and_rejected(self):
        g.checked_inspect(bars(),1560)
        with self.assertRaisesRegex(ValueError,'stale_bar'):g.checked_inspect(bars(),1800)
        self.assertEqual(len(g.POLLS),2);self.assertFalse(g.POLLS[-1]['usable'])
    def test_conflict_stops_fetch(self):
        rows=bars()+[[1500,98.4,99.2,98.3,98.5,10]]
        with patch.object(g,'ORIGINAL_FETCH',return_value=rows):
            with self.assertRaisesRegex(ValueError,'Conflicting'):g.checked_fetch(g.engine.COHORT[0])
        self.assertEqual(len(g.POLLS),1);self.assertEqual(g.POLLS[0]['stage'],'fetch')
    def test_exact_duplicates_do_not_invent_minutes(self):
        with patch.object(g,'ORIGINAL_FETCH',return_value=bars()+[bars()[-1]]) as f:
            clean=g.checked_fetch(g.engine.COHORT[0]);self.assertEqual(len(clean),16)
            self.assertEqual(f.call_args.args[1]%60,0)
    def test_inspection_exception_is_recorded(self):
        r=bars();r[-1][4]='NaN'
        with self.assertRaises(ValueError):g.checked_inspect(r,1560)
        self.assertEqual(g.POLLS[-1]['stage'],'inspect')
    def test_summary_includes_bad_poll(self):
        with self.assertRaises(ValueError):g.checked_inspect(bars(),1800)
        summary=g.checked_summary(g.engine.Ledger(),'completed')
        self.assertEqual(summary['unusable_candle_poll_count'],1)
if __name__=='__main__':unittest.main()
