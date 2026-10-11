"""Event-driven backtester.

1-hour candles of all symbols are replayed in time order, one timestamp at a time. For every candle:
  1. the simulated broker matches orders and positions that already existed *before* this candle against
     its open/high/low/close,
  2. only then is the closed candle handed to the strategy, which may send a market order for the *next*
     candle's open.
The strategy never receives a candle before it has closed and never sees a later one, so the result is what
you would have got trading it live with the same data.

Fill rules (conservative):
  - entry: market at the next candle's open (often the next morning), plus slippage. Stop and target were
    fixed from the signal candle's close, as in the live bracket order. If the open is already beyond the
    stop or the target, the trade is skipped (the live bot would not send a bracket that is already broken).
  - stop beats target when both are inside one candle.
  - stop fills at the stop or a worse opening gap, plus slippage; target fills at the limit or a better gap.
  - after `max_hold_bars` candles the position is closed at the next candle's open, plus slippage.
  - size is fixed when the signal is taken, from realised equity at that moment.
The daily equity curve marks open positions to the last close.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from typing import Callable, Optional

from .config import BARS_PER_DAY, ET, Params
from .data import Bar
from .strategy import CandlePatterns, Signal, floor_qty


@dataclass
class Trade:
    symbol: str
    day: str             # day of the entry
    side: str
    pattern: str
    signal_time: str
    entry_time: str
    entry: float
    stop: float
    target: float
    level: Optional[float]
    exit_time: str
    exit: float
    reason: str
    qty: float
    bars: int
    pnl: float
    r: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Position:
    sig: Signal
    qty: float
    entry: float
    entry_time: str
    bars: int = 0


def _hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _fmt(t: int) -> str:
    return datetime.fromtimestamp(t, ET).strftime("%Y-%m-%d %H:%M")


class Backtest:
    def __init__(self, bars: dict[str, list[Bar]], params: Params | Callable[[int], Params],
                 equity: float = 100_000.0, trade_from: Optional[date] = None, trade_until: Optional[date] = None,
                 min_bars_per_day: int = BARS_PER_DAY):
        self.bars = bars
        self.params = params if callable(params) else (lambda _t, p=params: p)
        self.start_equity = equity
        self.cash = equity
        self.trade_from = trade_from
        self.trade_until = trade_until
        self.min_bars_per_day = min_bars_per_day  # 1 for daily candles
        self.trades: list[Trade] = []
        self.signals: list[dict] = []
        self.skipped: Counter = Counter()
        self.equity_curve: list[tuple[str, float]] = []

    def _in_window(self, d: date) -> bool:
        return (self.trade_from is None or d >= self.trade_from) and (self.trade_until is None or d <= self.trade_until)

    def run(self) -> "Backtest":
        # calendar: new entries only on days with a full regular session (early closes are skipped)
        full_days = {s: {d for d, n in Counter(b.day for b in bl).items() if n >= self.min_bars_per_day}
                     for s, bl in self.bars.items()}
        strategies = {s: CandlePatterns(s, self.params) for s in self.bars}
        timeline: dict[int, list[Bar]] = defaultdict(list)
        for bl in self.bars.values():
            for b in bl:
                timeline[b.t].append(b)

        pending: dict[str, tuple[Signal, int]] = {}
        positions: dict[str, _Position] = {}
        last_bar: dict[str, Bar] = {}
        cur_day: Optional[date] = None

        for t in sorted(timeline):
            group = timeline[t]
            day = group[0].day
            if cur_day is not None and day != cur_day:
                self._end_of_day(cur_day, positions, last_bar)
            cur_day = day
            for bar in group:
                s = bar.symbol
                self._match(bar, pending, positions)
                last_bar[s] = bar
                sig = strategies[s].on_bar(bar, tradable=day in full_days[s])
                if sig is None or not self._in_window(day):
                    continue
                if sig.params.last_entry and bar.clock > _hhmm(sig.params.last_entry):
                    continue  # intraday: too late in the day for a new trade
                if s in positions or s in pending:
                    self.skipped["position open"] += 1
                    continue
                p = sig.params
                equity = self.cash
                risk_qty = equity * p.risk_pct / sig.risk
                cap_qty = equity * p.max_position_pct / sig.ref
                used = sum(x.qty * x.entry for x in positions.values()) + sum(q * g.ref for g, q in pending.values())
                gross_qty = max(0.0, equity * p.max_gross_pct - used) / sig.ref
                qty = floor_qty(min(risk_qty, cap_qty, gross_qty), p.qty_step)
                self.signals.append({"symbol": s, "time": _fmt(sig.t), "side": "long" if sig.side > 0 else "short",
                                     "pattern": sig.pattern, "ref": sig.ref, "stop": sig.stop, "target": sig.target,
                                     "qty": qty})
                if qty >= p.qty_step:
                    pending[s] = (sig, qty)
                else:
                    self.skipped["size < 1 or budget used"] += 1
        if cur_day is not None:
            self._end_of_day(cur_day, positions, last_bar)
        for s, pos in list(positions.items()):  # still open at the end of the data
            b = last_bar[s]
            self._close(pos, positions, b, b.c, "end_of_data", slip=True)
        return self

    # ------------------------------------------------------------------ matching
    def _match(self, bar: Bar, pending: dict, positions: dict) -> None:
        s = bar.symbol
        pos = positions.get(s)
        if pos is not None:
            p = pos.sig.params
            if p.flat_at and (bar.clock >= _hhmm(p.flat_at) or str(bar.day) != pos.entry_time[:10]):
                self._close(pos, positions, bar, bar.o, "eod", slip=True)
            elif pos.bars >= p.max_hold_bars:
                self._close(pos, positions, bar, bar.o, "time", slip=True)
            else:
                self._check_exit(pos, positions, bar)
            return
        if s not in pending:
            return
        sig, qty = pending.pop(s)
        p = sig.params
        side = sig.side
        if p.flat_at and (bar.day != datetime.fromtimestamp(sig.t, ET).date() or bar.clock >= _hhmm(p.flat_at)):
            self.skipped["intraday entry would fall on another day"] += 1
            return
        if (bar.o - sig.stop) * side <= 0 or (sig.target - bar.o) * side <= 0:
            self.skipped["opened beyond stop or target"] += 1
            return
        fill = bar.o * (1 + side * p.slippage_bps / 1e4)
        pos = _Position(sig, qty, fill, _fmt(bar.t))
        positions[s] = pos
        self._check_exit(pos, positions, bar)

    def _check_exit(self, pos: _Position, positions: dict, bar: Bar) -> None:
        sig = pos.sig
        side = sig.side
        pos.bars += 1
        if (bar.l <= sig.stop) if side > 0 else (bar.h >= sig.stop):
            raw = min(sig.stop, bar.o) if side > 0 else max(sig.stop, bar.o)
            self._close(pos, positions, bar, raw, "stop", slip=True)
        elif (bar.h >= sig.target) if side > 0 else (bar.l <= sig.target):
            raw = max(sig.target, bar.o) if side > 0 else min(sig.target, bar.o)
            self._close(pos, positions, bar, raw, "target", slip=False)

    def _close(self, pos: _Position, positions: dict, bar: Bar, raw: float, reason: str, slip: bool) -> None:
        sig, p = pos.sig, pos.sig.params
        side = sig.side
        px = raw * (1 - side * p.slippage_bps / 1e4) if slip else raw
        pnl = (px - pos.entry) * side * pos.qty - 2 * p.commission_per_share * pos.qty
        r = (px - pos.entry) * side / sig.risk if sig.risk > 0 else 0.0
        self.cash += pnl
        self.trades.append(Trade(sig.symbol, pos.entry_time[:10], "long" if side > 0 else "short", sig.pattern,
                                 _fmt(sig.t), pos.entry_time, round(pos.entry, 4), sig.stop, sig.target,
                                 None if sig.level != sig.level else round(sig.level, 4), _fmt(bar.t),
                                 round(px, 4), reason, pos.qty, pos.bars, round(pnl, 2), round(r, 4)))
        del positions[sig.symbol]

    def _end_of_day(self, day: date, positions: dict, last_bar: dict) -> None:
        if not self._in_window(day):
            return
        open_pnl = sum((last_bar[s].c - x.entry) * x.sig.side * x.qty for s, x in positions.items())
        self.equity_curve.append((str(day), round(self.cash + open_pnl, 2)))
