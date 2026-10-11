"""The six candlestick patterns from "The BEST Candlestick Pattern Guide You'll EVER FIND", traded at key levels.

Mechanised rules (1-hour candles, regular US session only):

Key levels: swing highs and swing lows of the last `level_lookback` candles. A swing high is a candle whose
    high is above the highs of `pivot_strength` candles on each side, so it is known only `pivot_strength`
    candles later. Old resistance below price acts as support and vice versa, so every swing price is a level.
    Swing points inside the pattern itself do not count.
A pattern is "at a level" when a level lies between its extreme (minus `touch_tol_atr` x ATR) and its
    close: price tested or crossed the level and closed on the trade side of it.

The six patterns (bullish; bearish is the mirror image). "Large" and "small" compare a candle's body with the
average body of the `body_avg_len` candles before it.
    engulfing               red candle, then a green candle whose body covers the red body and is bigger
    pin_bar                 green candle whose lower wick is at least `pin_wick` of its range
    three_bar_reversal      large red, smaller red, large green closing above the first red's open
    three_bar_continuation  large green, small pullback candle that keeps above the first low,
                            large green closing above both highs
    breakout                at least `min_consolidation` small candles, then a large green candle closing
                            above all of them
    shrinking               at least `min_shrink` red candles, each body smaller than the one before,
                            then a large green candle

Trade: market order at the next candle's open (the video enters at the close of the pattern), stop beyond
    the pattern's extreme (`stop_buffer_atr` x ATR), take profit at `rr` x the planned risk, close after
    `max_hold_bars` candles at the latest. Long and short on the same candle = no trade.
    With `long_only` the bearish patterns are not traded at all.

The class only ever sees candles that are already closed (`on_bar` is called after a candle is complete),
so it cannot look into the future. tests/test_no_lookahead.py checks that.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

from .config import Params
from .data import Bar


@dataclass
class Signal:
    symbol: str
    t: int               # start of the pattern's last candle; the entry is at the next candle's open
    side: int            # +1 long, -1 short
    pattern: str
    ref: float           # close of the signal candle: stop and target distances are measured from it
    stop: float
    target: float
    level: float         # the key level the pattern formed at (nan without a level filter)
    atr: float
    params: Params = field(repr=False)

    @property
    def risk(self) -> float:
        return abs(self.ref - self.stop)


def body(b: Bar) -> float:
    return abs(b.c - b.o)


def green(b: Bar) -> bool:
    return b.c > b.o


def red(b: Bar) -> bool:
    return b.c < b.o


def _flip(b: Bar) -> Bar:
    """Mirror a candle (prices negated) so the bearish rules are the bullish rules applied to the mirror."""
    return Bar(b.symbol, b.t, -b.o, -b.l, -b.h, -b.c, b.v)


def bullish_patterns(bars: list[Bar], avg: float, p: Params) -> list[tuple[str, int]]:
    """Bullish patterns that end with bars[-1]. Returns (name, number of candles in the pattern)."""
    out = []
    c = bars[-1]
    if not green(c) or avg <= 0:
        return out
    big = lambda b: body(b) >= p.large_body * avg
    small = lambda b: body(b) <= p.small_body * avg
    if len(bars) >= 2:
        a = bars[-2]
        if red(a) and c.c >= a.o and c.o <= a.c and body(c) > body(a):
            out.append(("engulfing", 2))
    rng = c.h - c.l
    if rng > 0 and (min(c.o, c.c) - c.l) >= p.pin_wick * rng:
        out.append(("pin_bar", 1))
    if len(bars) >= 3:
        a, m = bars[-3], bars[-2]
        if red(a) and big(a) and red(m) and body(m) < body(a) and big(c) and c.c > a.o:
            out.append(("three_bar_reversal", 3))
        if green(a) and big(a) and small(m) and m.l > a.l and big(c) and c.c > max(a.h, m.h):
            out.append(("three_bar_continuation", 3))
    if big(c):
        n = 0
        while n < len(bars) - 1 and n < 20 and small(bars[-2 - n]):
            n += 1
        if n >= p.min_consolidation and c.c > max(b.h for b in bars[-1 - n:-1]):
            out.append(("breakout", n + 1))
        n = 0
        while n < len(bars) - 1 and red(bars[-2 - n]) and (n == 0 or body(bars[-2 - n]) > body(bars[-1 - n])):
            n += 1
        if n >= p.min_shrink:
            out.append(("shrinking", n + 1))
    return out


KEEP_BARS = 400  # memory: more than any rule ever looks back


class CandlePatterns:
    """Streaming strategy for one symbol. Feed it closed 1-hour candles in time order."""

    def __init__(self, symbol: str, params: Params | Callable[[int], Params]):
        self.symbol = symbol
        self._params = params if callable(params) else (lambda _t, p=params: p)
        self.bars: list[Bar] = []
        self.trs: list[float] = []
        self.pivots: list[tuple[int, float]] = []   # (candle index, price) of confirmed swing points
        self.n = 0                                   # candles seen so far (index of the next candle)

    def params_for(self, t: int) -> Params:
        return self._params(t)

    def on_bar(self, bar: Bar, tradable: bool = True) -> Optional[Signal]:
        """`tradable` is calendar knowledge known before the open (full session, no early close)."""
        p = self.params_for(bar.t)
        prev = self.bars[-1] if self.bars else None
        self.trs.append(bar.h - bar.l if prev is None else max(bar.h, prev.c) - min(bar.l, prev.c))
        self.bars.append(bar)
        self.n += 1
        if len(self.bars) > KEEP_BARS:
            drop = len(self.bars) - KEEP_BARS
            self.bars, self.trs = self.bars[drop:], self.trs[drop:]
        self._confirm_pivot(p.pivot_strength)
        if not tradable:
            return None
        return self._evaluate(p)

    def _idx(self, i: int) -> int:
        """Absolute candle index of self.bars[i] (i negative)."""
        return self.n + i

    def _confirm_pivot(self, k: int) -> None:
        if len(self.bars) < 2 * k + 1:
            return
        j = -k - 1
        c = self.bars[j]
        left, right = self.bars[j - k:j], self.bars[j + 1:]
        if all(c.h > b.h for b in left + right):
            self.pivots.append((self._idx(j), c.h))
        if all(c.l < b.l for b in left + right):
            self.pivots.append((self._idx(j), c.l))
        cutoff = self.n - 1000
        if self.pivots and self.pivots[0][0] < cutoff:
            self.pivots = [x for x in self.pivots if x[0] >= cutoff]

    def _evaluate(self, p: Params) -> Optional[Signal]:
        need = max(p.atr_len, p.body_avg_len, p.trend_len) + 2
        if len(self.bars) < need:
            return None
        bars = self.bars
        atr = sum(self.trs[-p.atr_len:]) / p.atr_len
        avg = sum(body(b) for b in bars[-p.body_avg_len - 1:-1]) / p.body_avg_len
        sma = sum(b.c for b in bars[-p.trend_len:]) / p.trend_len
        c = bars[-1]
        window = bars[-25:]
        cands = []
        for side, seq in ((1, window), (-1, [_flip(b) for b in window])):
            if side < 0 and p.long_only:
                continue
            found = [(n, k) for n, k in bullish_patterns(seq, avg, p) if n in p.patterns]
            if not found:
                continue
            name, k = found[0]  # one label per candle, in the order of ALL_PATTERNS
            span = bars[-k:]
            ext = min(b.l for b in span) if side > 0 else max(b.h for b in span)
            level = self._level(side, ext, c.c, p.touch_tol_atr * atr, self.n - k, p)
            if p.require_level and level is None:
                continue
            if p.trend_filter and (c.c - sma) * side <= 0:
                continue
            stop = round(ext - side * p.stop_buffer_atr * atr, 2)
            risk = (c.c - stop) * side
            if risk < p.min_risk_atr * atr:
                continue
            target = round(c.c + side * p.rr * risk, 2)
            cands.append(Signal(self.symbol, c.t, side, name, c.c, stop, target,
                                level if level is not None else math.nan, atr, p))
        return cands[0] if len(cands) == 1 else None

    def _level(self, side: int, ext: float, close: float, tol: float, first_idx: int, p: Params) -> Optional[float]:
        """Closest key level between the pattern's extreme (with tolerance) and its close."""
        lo_idx = self.n - p.level_lookback
        best = None
        for idx, price in self.pivots:
            if idx < lo_idx or idx >= first_idx:
                continue
            ok = (ext - tol <= price <= close) if side > 0 else (close <= price <= ext + tol)
            if ok and (best is None or abs(price - ext) < abs(best - ext)):
                best = price
        return best


def floor_qty(x: float) -> int:
    return max(0, int(math.floor(x + 1e-9)))
