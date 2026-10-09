"""Backtest of the frozen live variants side by side: python -m candle_patterns variants

Each variant trades its own live budget over the same period. This is the historical baseline the live
results are compared with. V2's parameters were chosen on data up to the live start, so its history is partly
in-sample; V1 uses the video rules fixed before any data was seen.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone

from .config import LIVE_BUDGET, RESULTS_DIR, UNIVERSE
from .data import load_universe
from .engine import Backtest
from .live import load_variants
from .metrics import breakdown, full_report

OUT = os.path.join(RESULTS_DIR, "variants_backtest.json")


def run(start: date = date(2020, 2, 1)) -> dict:
    bars = load_universe(UNIVERSE)
    if not bars:
        raise SystemExit("no bars loaded - run `python -m candle_patterns download` first")
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "start": str(start), "variants": {}}
    for vid, v in load_variants().items():
        budget = round(LIVE_BUDGET * v.get("budget_share", 1.0), 2)
        bt = Backtest(bars, v["params"], budget, trade_from=start).run()
        trades = [t.to_dict() for t in bt.trades]
        rep = full_report(trades, bt.equity_curve, budget)
        out["variants"][vid] = {"label": v.get("label", vid), "note": v.get("note", ""), "budget": budget,
                                "summary": rep["summary"], "equity": rep["equity"], "by_year": rep["by_year"],
                                "by_side": rep["by_side"], "by_pattern": rep["by_pattern"],
                                "by_exit": breakdown(trades, lambda t: t["reason"])}
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    return out
