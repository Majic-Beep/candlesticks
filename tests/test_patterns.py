"""Hand-built candles for each of the six patterns (bullish and the mirrored bearish case) and for the fills."""
import unittest
from datetime import date, datetime, timedelta

from candle_patterns.config import ET, HOUR_STARTS, Params
from candle_patterns.data import Bar, to_hourly
from candle_patterns.engine import Backtest
from candle_patterns.strategy import CandlePatterns, _flip, bullish_patterns

P = Params()
AVG = 1.0  # average body used by the pattern tests


def bars(rows, sym="X"):
    t0 = int(datetime(2024, 3, 4, 9, 30, tzinfo=ET).timestamp())
    return [Bar(sym, t0 + 3600 * i, o, h, l, c, 1) for i, (o, h, l, c) in enumerate(rows)]


def names(rows):
    return [n for n, _ in bullish_patterns(bars(rows), AVG, P)]


def mirror(rows):
    return [n for n, _ in bullish_patterns([_flip(b) for b in bars(rows)], AVG, P)]


def neg(rows):
    """Bearish twin of a bullish example: prices negated and shifted up."""
    return [(200 - o, 200 - l, 200 - h, 200 - c) for o, h, l, c in rows]


CASES = {
    "engulfing": [(100.0, 100.1, 99.3, 99.4), (99.3, 100.4, 99.2, 100.3)],
    "pin_bar": [(100.0, 100.2, 99.8, 100.0), (100.0, 100.3, 98.0, 100.2)],
    "three_bar_reversal": [(102.0, 102.1, 100.4, 100.5), (100.5, 100.6, 99.8, 100.0), (100.0, 102.5, 99.9, 102.3)],
    "three_bar_continuation": [(100.0, 101.6, 99.9, 101.5), (101.5, 101.7, 101.0, 101.3), (101.3, 103.2, 101.2, 103.0)],
    "breakout": [(100.0, 100.4, 99.8, 100.2), (100.2, 100.5, 99.9, 100.0), (100.0, 100.3, 99.7, 100.1),
                 (100.1, 102.0, 100.0, 101.8)],
    "shrinking": [(103.0, 103.1, 101.4, 101.5), (101.5, 101.6, 100.5, 100.6), (100.6, 100.7, 100.0, 100.2),
                  (100.2, 101.8, 100.1, 101.6)],
}


class Patterns(unittest.TestCase):
    def test_each_bullish_pattern(self):
        for name, rows in CASES.items():
            with self.subTest(name):
                self.assertIn(name, names(rows))

    def test_each_bearish_pattern_is_the_mirror(self):
        for name, rows in CASES.items():
            with self.subTest(name):
                self.assertIn(name, mirror(neg(rows)))
                self.assertNotIn(name, names(neg(rows)))

    def test_no_pattern_on_red_last_candle(self):
        self.assertEqual(names([(100, 101, 99, 100.5), (100.5, 100.6, 99, 99.2)]), [])

    def test_shrinking_needs_smaller_bodies(self):
        rows = [(101.5, 101.6, 100.9, 101.0), (101.0, 101.1, 100.0, 100.1), (100.1, 100.2, 99.0, 99.2),
                (99.2, 101.0, 99.1, 100.8)]  # bodies grow: 0.5, 0.9, 0.9
        self.assertNotIn("shrinking", names(rows))

    def test_breakout_needs_close_above_box(self):
        rows = CASES["breakout"][:-1] + [(99.0, 100.45, 98.9, 100.4)]  # large body but closes inside the box
        self.assertNotIn("breakout", names(rows))


def day(d, rows, sym="X"):
    out = []
    for st, (o, h, l, c) in zip(HOUR_STARTS, rows):
        t = datetime(d.year, d.month, d.day, st.hour, st.minute, tzinfo=ET)
        out.append(Bar(sym, int(t.timestamp()), o, h, l, c, 1))
    return out


def flat_history(n=12):
    """n quiet days around 100 with a clear swing low at 99.0 on the last day."""
    out, d, k = [], date(2024, 3, 1), 0
    while k < n:
        if d.weekday() < 5:
            rows = [(100.0, 100.3, 99.7, 100.1), (100.1, 100.4, 99.8, 99.9)] * 3 + [(99.9, 100.2, 99.6, 100.0)]
            if k == n - 1:
                rows[1] = (100.0, 100.2, 99.0, 99.8)  # swing low, confirmed by the next three candles
            out += day(d, rows)
            k += 1
        d += timedelta(days=1)
    return out, d


def next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


Q = Params(slippage_bps=0, stop_buffer_atr=0, risk_pct=0.01, max_position_pct=1.0, trend_len=20, patterns=("pin_bar",))


class Engine(unittest.TestCase):
    def setup_day(self, follow):
        hist, d = flat_history()
        d = next_weekday(d)
        # pin bar at the 99.0 swing low: low 98.9, close 99.9 -> stop 98.9, risk 1.0, target 101.9
        pin = (99.6, 99.95, 98.9, 99.9)
        return hist + day(d, [pin] + follow + [(100.0, 100.1, 99.9, 100.0)] * (6 - len(follow)))

    def test_long_to_target(self):
        t = Backtest({"X": self.setup_day([(99.9, 102.0, 99.8, 101.5)])}, Q).run().trades
        self.assertEqual(len(t), 1)
        self.assertEqual((t[0].side, t[0].pattern, t[0].reason, t[0].entry, t[0].exit), ("long", "pin_bar", "target", 99.9, 101.9))
        self.assertAlmostEqual(t[0].r, 2.0, places=3)

    def test_stop_beats_target_in_one_candle(self):
        t = Backtest({"X": self.setup_day([(99.9, 102.0, 98.5, 101.0)])}, Q).run().trades
        self.assertEqual((t[0].reason, t[0].exit), ("stop", 98.9))

    def test_gap_through_stop_fills_at_open(self):
        t = Backtest({"X": self.setup_day([(99.9, 100.0, 99.2, 99.3), (98.0, 98.2, 97.5, 98.1)])}, Q).run().trades
        self.assertEqual((t[0].reason, t[0].exit), ("stop", 98.0))

    def test_time_exit(self):
        t = Backtest({"X": self.setup_day([(99.9, 100.2, 99.5, 100.0)])}, Q.with_(max_hold_bars=3)).run().trades
        self.assertEqual((t[0].reason, t[0].bars), ("time", 3))

    def test_no_level_no_trade(self):
        hist, d = flat_history()
        rows = [(98.0, 98.25, 97.3, 98.2)] + [(98.2, 98.3, 98.1, 98.2)] * 6  # pin far below every level
        self.assertEqual(Backtest({"X": hist + day(next_weekday(d), rows)}, Q).run().trades, [])


class Hourly(unittest.TestCase):
    def test_thirty_minute_bars_to_session_hours(self):
        t0 = datetime(2024, 3, 4, 9, 30, tzinfo=ET)
        b30 = [Bar("X", int((t0 + timedelta(minutes=30 * i)).timestamp()), 100 + i, 101 + i, 99 + i, 100.5 + i, 10)
               for i in range(13)]
        h = to_hourly(b30)
        self.assertEqual([b.clock.strftime("%H:%M") for b in h], [s.strftime("%H:%M") for s in HOUR_STARTS])
        self.assertEqual((h[0].o, h[0].h, h[0].l, h[0].c, h[0].v), (100, 102, 99, 101.5, 20))
        self.assertEqual((h[-1].o, h[-1].c), (112, 112.5))


class LongOnly(unittest.TestCase):
    def test_long_only_never_shorts_and_keeps_the_longs(self):
        from tests.synth import make_bars
        bars = make_bars("X", days=200, seed=3)
        both, longs = CandlePatterns("X", Params()), CandlePatterns("X", Params(long_only=True))
        sb = [s for b in bars if (s := both.on_bar(b))]
        sl = [s for b in bars if (s := longs.on_bar(b))]
        self.assertTrue(any(s.side < 0 for s in sb), "test data should produce shorts")
        self.assertTrue(sl and all(s.side > 0 for s in sl))
        self.assertTrue({s.t for s in sb if s.side > 0} <= {s.t for s in sl})


if __name__ == "__main__":
    unittest.main()
