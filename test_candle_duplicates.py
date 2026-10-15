import unittest
from candle_duplicates import normalize
class Duplicates(unittest.TestCase):
    def test_identical_rows_only(self):
        r=[60,1,2,1,2,3];clean,d=normalize([r,r,[120,2,2,2,2,0]])
        self.assertEqual(len(clean),2);self.assertEqual(d['redundant_rows'],1)
    def test_conflict_is_not_silently_selected(self):
        clean,d=normalize([[60,1,2,1,2,3],[60,1,2,1,1,3]])
        self.assertIsNone(clean);self.assertEqual(d['conflicting_minutes'],1)
    def test_nonminute_fails(self):
        with self.assertRaises(ValueError):normalize([[61,1,2,1,2,3]])
if __name__=='__main__':unittest.main()
