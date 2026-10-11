"""Command line: python -m candle_patterns <command>

  download   [--start 2019-01-01]   30-minute bars from Alpaca market data -> data/*.csv
  backtest                          walk-forward + hold-out + references -> results/backtest.json
  variants                          backtest of the frozen live variants -> results/variants_backtest.json
  run        [--dry-run]            live: after each 1h candle close - exits, then new entries
  sync                              live: read fills back -> results/live.json
  dashboard                         build docs/index.html from the results
  crypto-download                   Alpaca crypto 1-hour bars since 2021 -> data/crypto_*.csv
  crypto-backtest                   same strategy on crypto -> results/crypto/
  forex-download                    currency ETFs (FXE, FXB, FXY, ...) from Alpaca -> data/*.csv
  forex-backtest                    same strategy on the currency ETFs -> results/forex/
  daily-download                    daily stock bars since 2016 -> data/daily_*.csv
  daily-backtest                    same strategy on daily candles -> results/daily/
  futures-download                  daily bars of futures-tracking ETFs -> data/daily_*.csv
  futures-backtest                  daily candles on the futures proxies -> results/futures/
  m5-download                       5-minute stock bars since 2021 -> data/m5_*.csv
  m5-backtest                       same strategy on 5-minute candles, flat every evening -> results/m5/
"""
from __future__ import annotations

import argparse
from datetime import date

from .config import UNIVERSE


def main() -> None:
    ap = argparse.ArgumentParser(prog="candle_patterns")
    ap.add_argument("command", choices=["download", "backtest", "variants", "run", "sync", "dashboard", "crypto-download", "crypto-backtest", "forex-download", "forex-backtest", "daily-download", "daily-backtest", "futures-download", "futures-backtest", "m5-download", "m5-backtest"])
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
    elif a.command == "crypto-download":
        from .crypto import download
        download()
    elif a.command == "forex-download":
        from .forex import download
        download()
    elif a.command == "daily-download":
        from .daily import download
        download()
    elif a.command == "futures-download":
        from .daily import FUTURES_PROXIES, download
        download(symbols=list(FUTURES_PROXIES))
    elif a.command == "m5-download":
        from .intraday import download
        download()
    elif a.command in ("crypto-backtest", "forex-backtest", "daily-backtest", "futures-backtest", "m5-backtest"):
        if a.command == "crypto-backtest":
            from .crypto import run_backtest
        elif a.command == "forex-backtest":
            from .forex import run_backtest
        elif a.command == "daily-backtest":
            from .daily import run_backtest
        elif a.command == "m5-backtest":
            from .intraday import run_backtest
        else:
            from functools import partial
            from .daily import FUTURES_COST_BPS, FUTURES_OUT, FUTURES_PROXIES, run_backtest as _rb
            run_backtest = partial(_rb, symbols=list(FUTURES_PROXIES), out_dir=FUTURES_OUT, cost_bps=FUTURES_COST_BPS)
        r = run_backtest()
        for k in ("walk_forward", "holdout", "standard", "in_sample"):
            s = r["walk_forward"][k]["summary"]
            print(f"{k:13s} trades {s['trades']:5d}  return {s['total_return_pct']:7.2f}%  maxDD {s['max_drawdown_pct']:6.2f}%  "
                  f"win {s['win_rate_pct']:5.1f}%  E[R] {s['expectancy_r']:+.3f}  t {s['r_tstat']:+.2f}")
        for vid, v in r["variants"]["variants"].items():
            s = v["summary"]
            print(f"{vid} trades {s['trades']}  return {s['total_return_pct']:+.2f}%  maxDD {s['max_drawdown_pct']:.2f}%  "
                  f"E[R] {s['expectancy_r']:+.3f}  t {s['r_tstat']:+.2f}")
    elif a.command == "dashboard":
        from .dashboard import build
        print(build())


if __name__ == "__main__":
    main()
