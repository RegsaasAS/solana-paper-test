import unittest
from decimal import Decimal as D
from signal_test import PaperEngine, inspect_signal

META={'lot_decimals':8,'ordermin':'0.05','costmin':'0.5'}

def bars():
    rows=[[i*60,'100','100.1','99.9','100','100','10',8] for i in range(5)]
    rows.append([300,'100','100.5','100','100.4','100.2','20',14])
    rows.append([360,'100.4','101','100.4','101','100.7','1000',20])
    return rows

def book(price='100.4'):
    return {'asks':[[str(D(price)+D('.01')),'100',0]],'bids':[[price,'100',0]]}

class TestSignal(unittest.TestCase):
    def start(self):
        e=PaperEngine(META,0,3600)
        e.observe(inspect_signal(bars(),370),0)
        self.assertIsNone(e.tick(book(),9))
        self.assertEqual(e.tick(book(),10)['side'],'BUY')
        return e

    def test_unfinished_candle_never_used(self):
        rows=bars(); rows[5][4]='100'; rows[5][6]='10'
        self.assertFalse(inspect_signal(rows,370)['eligible'])

    def test_future_close_never_used(self):
        self.assertFalse(inspect_signal(bars(),359)['eligible'])

    def test_volume_confirmation_required(self):
        rows=bars();rows[5][6]='11'
        self.assertFalse(inspect_signal(rows,370)['eligible'])

    def test_stale_candle_refused(self):
        self.assertEqual(inspect_signal(bars(),1000)['reason'],'stale_candle')

    def test_repeated_signal_cannot_duplicate_entry(self):
        e=self.start(); e.observe(inspect_signal(bars(),370),20)
        e.tick(book(),21)
        self.assertEqual(len(e.trades),1)

    def test_gross_gain_does_not_imply_net_take_profit(self):
        e=self.start();self.assertIsNone(e.tick(book('101.4'),20))
        self.assertEqual(e.tick(book('104'),30)['reason'],'net_take_profit')

    def test_stop_loss_and_accounting(self):
        e=self.start(); row=e.tick(book('98'),20)
        self.assertEqual(row['reason'],'net_stop_loss')
        self.assertEqual(e.cash,D('100')+sum((D(t['cash_change_usdt']) for t in e.trades),D(0)))
        self.assertIsNone(e.position)

    def test_time_exit(self):
        e=self.start();self.assertEqual(e.tick(book(),310)['reason'],'five_minute_time_exit')

    def test_missing_exit_liquidity_preserves_unresolved_position(self):
        e=self.start();thin={'asks':[['100.41','100',0]],'bids':[['100.4','0.001',0]]}
        with self.assertRaises(RuntimeError):e.tick(thin,310)
        self.assertIsNotNone(e.position)
        self.assertEqual(len(e.trades),1)

    def test_no_entry_near_session_end(self):
        e=PaperEngine(META,0,200)
        e.observe(inspect_signal(bars(),370),0)
        self.assertIsNone(e.tick(book(),10));self.assertEqual(e.trades,[])

    def test_entry_expired(self):
        e=PaperEngine(META,0,3600);e.observe(inspect_signal(bars(),370),0)
        self.assertIsNone(e.tick(book(),100));self.assertIsNone(e.position)

    def test_no_signal_is_valid_and_has_no_fabricated_pnl(self):
        e=PaperEngine(META,0,3600);v=e.summary('completed',60,[],book(),book())
        self.assertEqual(v['full_portfolio_net_pnl_usdt'],'0')
        self.assertEqual(v['completed_roundtrips'],0)
        self.assertFalse(v['adequate_sample'])

if __name__=='__main__':unittest.main()
