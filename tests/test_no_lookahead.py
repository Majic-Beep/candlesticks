"""The backtest must not use information from the future.

If the candles after day D are replaced by completely different candles, every trade decided and closed
before D has to stay exactly the same. A strategy or engine that peeks ahead fails this.
"""
import random
import unittest
from dataclasses import replace

from candle_patterns.config import Params
from candle_patterns.engine import Backtest
from candle_patterns.strategy import CandlePatterns
from tests.synth import make_bars

P = Params(max_hold_bars=14)


def scramble_after(bars, cut, seed=7):
    rnd = random.Random(seed)
    out = []
    for b in bars:
        if b.day >= cut:
            k = 1 + rnd.uniform(-0.05, 0.05)
            out.append(replace(b, o=round(b.o * k, 2), h=round(b.h * k * 1.01, 2), l=round(b.l * k * 0.99, 2), c=round(b.c * k, 2)))
        else:
            out.append(b)
    return out


def closed_before(bt, cut):
    return [t.to_dict() for t in bt.trades if t.exit_time < str(cut)]


class NoLookahead(unittest.TestCase):
    def setUp(self):
        self.bars = {s: make_bars(s, seed=i, days=220) for i, s in enumerate(["AAA", "BBB", "CCC"])}
        days = sorted({b.day for b in self.bars["AAA"]})
        self.cut = days[150]

    def test_trades_before_cut_unchanged(self):
        full = Backtest(self.bars, P).run()
        alt = Backtest({s: scramble_after(b, self.cut) for s, b in self.bars.items()}, P).run()
        self.assertGreater(len(closed_before(full, self.cut)), 30, "test data should produce trades")
        self.assertEqual(closed_before(full, self.cut), closed_before(alt, self.cut))

    def test_truncated_data_gives_same_history(self):
        full = Backtest(self.bars, P).run()
        trunc = Backtest({s: [b for b in bl if b.day < self.cut] for s, bl in self.bars.items()}, P).run()
        self.assertEqual(closed_before(full, self.cut), [t for t in closed_before(trunc, self.cut)
                                                         if t["reason"] != "end_of_data"])

    def test_signal_uses_only_closed_bars(self):
        # a signal on candle i must be the same when the stream stops right after candle i
        bars = self.bars["AAA"]
        full = CandlePatterns("AAA", P)
        sigs = {}
        for i, b in enumerate(bars):
            if (s := full.on_bar(b)):
                sigs[i] = s
        self.assertGreater(len(sigs), 30)
        for i in list(sigs)[::7]:
            st = CandlePatterns("AAA", P)
            last = None
            for b in bars[:i + 1]:
                last = st.on_bar(b)
            self.assertIsNotNone(last)
            a, b = last, sigs[i]
            self.assertEqual((a.t, a.side, a.pattern, a.stop, a.target, a.level),
                             (b.t, b.side, b.pattern, b.stop, b.target, b.level))


if __name__ == "__main__":
    unittest.main()
