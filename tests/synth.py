"""Synthetic 1-hour candles for tests (random walk, full regular sessions on weekdays)."""
import random
from datetime import date, datetime, timedelta

from candle_patterns.config import ET, HOUR_STARTS
from candle_patterns.data import Bar


def make_bars(symbol="TEST", start=date(2024, 1, 2), days=150, seed=1, price=100.0, vol=0.008):
    rnd = random.Random(seed)
    out, d, n = [], start, 0
    while n < days:
        if d.weekday() < 5:
            price *= 1 + rnd.gauss(0, vol)  # overnight gap
            for st in HOUR_STARTS:
                t0 = datetime(d.year, d.month, d.day, st.hour, st.minute, tzinfo=ET)
                o = price
                c = o * (1 + rnd.gauss(0, vol))
                h = max(o, c) * (1 + abs(rnd.gauss(0, vol / 2)))
                l = min(o, c) * (1 - abs(rnd.gauss(0, vol / 2)))
                out.append(Bar(symbol, int(t0.timestamp()), round(o, 2), round(h, 2), round(l, 2), round(c, 2), 1000))
                price = c
            n += 1
        d += timedelta(days=1)
    return out
