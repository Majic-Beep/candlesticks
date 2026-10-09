"""Command line: python -m candle_patterns <command>

  download   [--start 2019-01-01]   30-minute bars from Alpaca market data -> data/*.csv
  backtest                          walk-forward + hold-out + references -> results/backtest.json
  variants                          backtest of the frozen live variants -> results/variants_backtest.json
  run        [--dry-run]            live: after each 1h candle close - exits, then new entries
  sync                              live: read fills back -> results/live.json
  dashboard                         build docs/index.html from the results
"""
from __future__ import annotations

import argparse
from datetime import date

from .config import UNIVERSE


def main() -> None:
    ap = argparse.ArgumentParser(prog="candle_patterns")
    ap.add_argument("command", choices=["download", "backtest", "variants", "run", "sync", "dashboard"])
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--symbols", default=",".join(UNIVERSE))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--train-months", type=int, default=12)
    ap.add_argument("--test-months", type=int, default=3)
    ap.add_argument("--holdout-months", type=int, default=6)
    ap.add_argument("--equity", type=float, default=None, help="start capital of the backtest (default: live budget)")
    a = ap.parse_args()
    symbols = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]

    if a.command == "download":
        from .data import update_cache
        bars = update_cache(symbols, date.fromisoformat(a.start))
        for s, b in bars.items():
            print(f"{s}: {len(b)} bars" + (f" {b[0].day} .. {b[-1].day}" if b else ""))
    elif a.command == "backtest":
        from .config import LIVE_BUDGET
        from .data import load_universe
        from .walkforward import run
        r = run(load_universe(symbols), train_months=a.train_months, test_months=a.test_months,
                holdout_months=a.holdout_months, equity=a.equity or LIVE_BUDGET)
        for k in ("walk_forward", "holdout", "standard", "in_sample"):
            s = r[k]["summary"]
            print(f"{k:13s} trades {s['trades']:5d}  return {s['total_return_pct']:7.2f}%  maxDD {s['max_drawdown_pct']:6.2f}%  "
                  f"sharpe {s['sharpe']:5.2f}  win {s['win_rate_pct']:5.1f}%  E[R] {s['expectancy_r']:+.3f}  t {s['r_tstat']:+.2f}")
        print("final params:", r["final_params"])
    elif a.command == "variants":
        from .variants import run as variants
        for vid, v in variants()["variants"].items():
            s = v["summary"]
            print(f"{vid} trades {s['trades']}  return {s['total_return_pct']:+.2f}%  maxDD {s['max_drawdown_pct']:.2f}%  "
                  f"E[R] {s['expectancy_r']:+.3f}  t {s['r_tstat']:+.2f}")
    elif a.command == "run":
        from .live import cmd_run
        cmd_run(symbols, a.dry_run)
    elif a.command == "sync":
        from .live import cmd_sync
        cmd_sync()
    elif a.command == "dashboard":
        from .dashboard import build
        print(build())


if __name__ == "__main__":
    main()
