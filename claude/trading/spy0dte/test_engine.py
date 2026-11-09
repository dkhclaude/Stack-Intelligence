import unittest

import engine as e
import notify as n

ALL = {f: True for f in e.FACTORS}


def factors(k):
    return {f: i < k for i, f in enumerate(e.FACTORS)}


class Score(unittest.TestCase):
    def test_tiers(self):
        expected = {0: None, 1: None, 2: None, 3: ("T1", 10), 4: ("T2", 15), 5: ("T3", 25), 6: ("T4", 35)}
        for k, exp in expected.items():
            r = e.score(factors(k))
            self.assertEqual(r["score"], k)
            self.assertEqual(r["tier"], exp and exp[0])
            self.assertEqual(r["max_risk"], exp[1] if exp else 0)

    def test_unknown_factor(self):
        with self.assertRaises(ValueError):
            e.score({"vibes": True})

    def test_time_and_volume(self):
        self.assertTrue(e.in_time_window("06:45"))
        self.assertTrue(e.in_time_window("09:00"))
        self.assertFalse(e.in_time_window("09:01"))
        self.assertTrue(e.volume_factor(150, [100] * 10))
        self.assertFalse(e.volume_factor(149, [100] * 10))
        self.assertFalse(e.volume_factor(500, [100] * 9))


class Limits(unittest.TestCase):
    def test_daily_loss(self):
        self.assertEqual(e.daily_loss_limit(0), 40)
        self.assertEqual(e.daily_loss_limit(-20), 40)
        self.assertEqual(e.daily_loss_limit(30), 55)
        self.assertEqual(e.daily_loss_limit(500), 75)

    def test_streak_cap(self):
        eff = e.effective_tier(e.score(ALL), 2)
        self.assertEqual((eff["tier"], eff["max_risk"], eff["capped"]), ("T1", 10, True))
        self.assertEqual(e.effective_tier(e.score(ALL), 1)["tier"], "T4")


class Size(unittest.TestCase):
    base = dict(factors=factors(5), entry_premium=0.40, delta=0.20, entry_underlying=600.0,
                stop_underlying=599.0, account_value=500, realized_pnl=0, consecutive_losses=0, side="call")

    def test_delta_stop_and_size(self):
        r = e.size(self.base)
        self.assertEqual(r["option_stop"], 0.20)       # 0.40 - 0.20*1.00
        self.assertEqual(r["risk_per_contract"], 20.0)
        self.assertEqual(r["contracts"], 1)            # T3 $25 / $20
        self.assertTrue(r["trade"])

    def test_skip_when_stop_does_not_fit(self):
        r = e.size({**self.base, "factors": factors(3), "stop_underlying": 598.0})  # $40/contract vs $10
        self.assertFalse(r["trade"])
        self.assertIn("per-trade cap", r["reason"])

    def test_account_cap(self):
        r = e.size({**self.base, "factors": ALL, "stop_underlying": 599.8, "account_value": 100})
        self.assertEqual(r["contracts"], 0)           # 30% of $100 = $30 < $40 premium
        self.assertIn("30%", r["reason"])

    def test_daily_room_limits_risk(self):
        r = e.size({**self.base, "realized_pnl": -30})  # limit 40, room 10 < $20/contract
        self.assertFalse(r["trade"])
        r = e.size({**self.base, "realized_pnl": -40})
        self.assertIn("daily loss limit", r["reason"])

    def test_wrong_side_stop(self):
        self.assertFalse(e.size({**self.base, "stop_underlying": 601})["trade"])
        put = {**self.base, "side": "put", "stop_underlying": 601}
        self.assertTrue(e.size(put)["trade"])

    def test_no_trade_low_score(self):
        self.assertFalse(e.size({**self.base, "factors": factors(2)})["trade"])


class Exits(unittest.TestCase):
    def test_ladder(self):
        self.assertFalse(e.next_stop(0.40, 0.50, 0.20)["move"])          # +25%
        self.assertEqual(e.next_stop(0.40, 0.52, 0.20)["stop"], 0.40)    # +30% -> BE
        self.assertEqual(e.next_stop(0.40, 0.60, 0.40)["stop"], 0.50)    # +50% -> +25%
        self.assertEqual(e.next_stop(0.40, 0.72, 0.50)["stop"], 0.56)    # +80% -> +40%
        self.assertEqual(e.next_stop(0.40, 0.80, 0.56)["stop"], 0.60)    # +100% -> 75% of peak

    def test_never_down(self):
        r = e.next_stop(0.40, 0.52, 0.45)
        self.assertFalse(r["move"])
        self.assertEqual(r["stop"], 0.45)

    def test_trail_min_step(self):
        self.assertFalse(e.next_stop(0.40, 0.82, 0.60)["move"])          # 0.61 is +0.01
        self.assertEqual(e.next_stop(0.40, 0.84, 0.60)["stop"], 0.63)    # +0.03

    def test_scale_out(self):
        self.assertEqual(e.scale_out(1, 0.40, 0.70, False), 0)
        self.assertEqual(e.scale_out(2, 0.40, 0.60, False), 1)
        self.assertEqual(e.scale_out(3, 0.40, 0.60, False), 1)
        self.assertEqual(e.scale_out(4, 0.40, 0.59, False), 0)
        self.assertEqual(e.scale_out(4, 0.40, 0.60, True), 0)


class Notify(unittest.TestCase):
    def test_fill_requires_score(self):
        with self.assertRaises(ValueError):
            n.format_message("fill", {"symbol": "SPY"})
        t, b = n.format_message("fill", {"symbol": "SPY 600C", "side": "buy", "qty": 1, "price": 0.4,
                                         "score": 5, "tier": "T3", "factors": ["trend", "volume"]})
        self.assertIn("score 5/6 T3", b)
        self.assertIn("trend, volume", b)


if __name__ == "__main__":
    unittest.main()
