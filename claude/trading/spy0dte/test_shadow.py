import unittest

import shadow

BASE = {"entry_premium": 0.92, "delta": 0.23, "entry_underlying": 760.87, "stop_underlying": 759.93,
        "factors": {"trend": True, "structure": True, "key_level": True, "breadth": True,
                    "volume": False, "time": True},
        "account_value": 896, "realized_pnl": 0, "consecutive_losses": 0, "side": "call"}


class Shadow(unittest.TestCase):
    def test_stop_hit(self):
        r = shadow.run({**BASE, "bars": [["t1", 0.95, 0.90, 0.94], ["t2", 0.80, 0.60, 0.65]]})
        self.assertTrue(r["fits"])
        self.assertEqual(r["exit"]["reason"], f"stop {r['initial_stop']:.2f}")
        self.assertLess(r["pnl"], 0)

    def test_ladder_and_time_exit(self):
        bars = [["t1", 1.25, 0.95, 1.22], ["t2", 1.40, 1.20, 1.38], ["t3", 1.50, 1.30, 1.45]]
        r = shadow.run({**BASE, "exit_by_utc": "t3", "bars": bars})
        self.assertEqual(r["exit"]["reason"], "time exit")
        self.assertEqual(r["pnl"], round((1.45 - 0.92) * 100, 2))
        self.assertGreater(r["final_stop"], r["initial_stop"])

    def test_does_not_fit_tier(self):
        r = shadow.run({**BASE, "delta": 0.40, "bars": []})
        self.assertFalse(r["fits"])
        self.assertEqual(r["pnl"], 0.0)

    def test_open_marked_and_overnight_obs(self):
        r = shadow.run({**BASE, "next_open": 0.50, "bars": [["t1", 1.00, 0.90, 0.98]]})
        self.assertEqual(r["exit"]["reason"], "still open (marked)")
        self.assertEqual(r["overnight_obs"], round((0.50 - 0.92) * 100, 2))


if __name__ == "__main__":
    unittest.main()
