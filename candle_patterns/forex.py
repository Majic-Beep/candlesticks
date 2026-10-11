"""Forex backtest via currency ETFs on Alpaca (FXE = EUR, FXB = GBP, FXY = JPY, FXA = AUD, FXC = CAD, FXF = CHF,
UUP = USD index), with exactly the stock pipeline: 30-minute bars -> session-anchored 1-hour candles, same engine.

    python -m candle_patterns forex-download
    python -m candle_patterns forex-backtest     # -> results/forex/

Real spot forex is not available here (Alpaca has no FX data, FMP needs a paid plan, TradingView serves only
5,000 candles per request). The ETFs trade only in the US session and are much less liquid than spot FX, so the
costs are set higher than for the stocks.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone

from .config import RESULTS_DIR, Params

FOREX_UNIVERSE = ["FXE", "FXB", "FXY", "FXA", "FXC", "FXF", "UUP"]
FOREX_COST_BPS = 5.0  # per side: wider spreads of the thin currency ETFs
FOREX_OUT = os.path.join(RESULTS_DIR, "forex")


def download(start: date = date(2019, 1, 1)) -> dict:
    from .data import update_cache
    return update_cache(FOREX_UNIVERSE, start)


def run_backtest(equity: float = 50_000.0) -> dict:
    from .data import load_universe
    from .engine import Backtest
    from .live import load_variants
    from .metrics import full_report
    from .walkforward import run as walk_forward
    bars = load_universe(FOREX_UNIVERSE)
    if not bars:
        raise SystemExit("no forex ETF bars - run `python -m candle_patterns forex-download` first")
    os.makedirs(FOREX_OUT, exist_ok=True)
    wf = walk_forward(bars, base=Params(slippage_bps=FOREX_COST_BPS), equity=equity,
                      out_path=os.path.join(FOREX_OUT, "backtest.json"))
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "cost_bps_per_side": FOREX_COST_BPS,
           "symbols": sorted(bars), "variants": {}}
    start = date.fromisoformat(wf["walk_forward_range"][0])
    for vid, v in load_variants().items():
        bt = Backtest(bars, v["params"].with_(slippage_bps=FOREX_COST_BPS), equity, trade_from=start).run()
        rep = full_report([t.to_dict() for t in bt.trades], bt.equity_curve, equity)
        out["variants"][vid] = {"label": v.get("label", vid), "summary": rep["summary"], "by_side": rep["by_side"],
                                "by_pattern": rep["by_pattern"], "by_symbol": rep["by_symbol"], "by_year": rep["by_year"],
                                "by_exit": rep["by_exit"]}
    with open(os.path.join(FOREX_OUT, "variants.json"), "w") as f:
        json.dump(out, f, indent=1)
    return {"walk_forward": wf, "variants": out}
