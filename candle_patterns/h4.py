"""4-hour backtest on stocks: two candles per regular session, as on TradingView (09:30-13:30, 13:30-16:00).

    python -m candle_patterns h4-download     # 30-minute bars for the 24 stocks/ETFs (if missing) -> data/
    python -m candle_patterns h4-backtest     # walk-forward + hold-out + variants -> results/h4/

Time spans are kept as on the 1h chart and fixed before the test: levels from the last 40 candles (20 days),
close after 10 candles (5 days) at the latest; trend = 50-candle average (25 days).
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timezone

from .config import ET, RESULTS_DIR, Params
from .daily import DAILY_UNIVERSE
from .data import Bar, clean, csv_path, load_csv

H4_OUT = os.path.join(RESULTS_DIR, "h4")
H4_BASE = dict(level_lookback=40, max_hold_bars=10, trend_len=50)
H4_STARTS = (time(9, 30), time(13, 30))


def h4_params(**kw) -> Params:
    return Params(**{**H4_BASE, **kw})


def to_4h(bars: list[Bar]) -> list[Bar]:
    out, cur, key = [], None, None
    for b in clean(bars):
        et = b.et
        slot = H4_STARTS[1] if et.time() >= H4_STARTS[1] else H4_STARTS[0]
        k = (et.date(), slot)
        if k != key:
            if cur:
                out.append(cur)
            cur, key = Bar(b.symbol, int(datetime.combine(et.date(), slot, ET).timestamp()), b.o, b.h, b.l, b.c, b.v), k
        else:
            cur = Bar(b.symbol, cur.t, cur.o, max(cur.h, b.h), min(cur.l, b.l), b.c, cur.v + b.v)
    if cur:
        out.append(cur)
    return out


def download(start: date = date(2019, 1, 1)) -> None:
    from .data import update_cache
    missing = [s for s in DAILY_UNIVERSE if not os.path.exists(csv_path(s))]
    if missing:
        update_cache(missing, start)


def load() -> dict[str, list[Bar]]:
    return {s: to_4h(load_csv(s)) for s in DAILY_UNIVERSE if os.path.exists(csv_path(s))}


def run_backtest(equity: float = 50_000.0) -> dict:
    from .engine import Backtest
    from .live import load_variants
    from .metrics import full_report
    from .walkforward import run as walk_forward
    bars = load()
    if not bars:
        raise SystemExit("no bars - run `python -m candle_patterns h4-download` first")
    os.makedirs(H4_OUT, exist_ok=True)
    wf = walk_forward(bars, base=h4_params(), equity=equity, out_path=os.path.join(H4_OUT, "backtest.json"),
                      min_bars_per_day=2)
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "h4_base": H4_BASE,
           "symbols": sorted(bars), "variants": {}}
    start = date.fromisoformat(wf["walk_forward_range"][0])
    for vid, v in load_variants().items():
        bt = Backtest(bars, v["params"].with_(**H4_BASE), equity, trade_from=start, min_bars_per_day=2).run()
        rep = full_report([t.to_dict() for t in bt.trades], bt.equity_curve, equity)
        out["variants"][vid] = {"label": v.get("label", vid), "summary": rep["summary"], "by_side": rep["by_side"],
                                "by_pattern": rep["by_pattern"], "by_symbol": rep["by_symbol"], "by_year": rep["by_year"],
                                "by_exit": rep["by_exit"]}
    with open(os.path.join(H4_OUT, "variants.json"), "w") as f:
        json.dump(out, f, indent=1)
    return {"walk_forward": wf, "variants": out}
