"""Daily-candle backtest on stocks: the same six patterns and engine on one candle per trading day.

    python -m candle_patterns daily-download     # Alpaca daily bars since 2016 -> data/daily_<SYM>.csv
    python -m candle_patterns daily-backtest     # walk-forward + hold-out + variants -> results/daily/

The bar-count parameters are translated to days and fixed before the test: levels from the last 60 days,
trend = 50-day average, close after 20 days at the latest. Entry at the next day's open, as on the 1h chart.
"""
from __future__ import annotations

import csv
import json
import os
import time as _time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from .config import DATA_DIR, RESULTS_DIR, UNIVERSE, Params
from .data import DATA_URL, Bar, _alpaca_headers

SNEAKY_PIVOT_UNIVERSE = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "AMD", "GOOGL"]
DAILY_UNIVERSE = UNIVERSE + SNEAKY_PIVOT_UNIVERSE
DAILY_OUT = os.path.join(RESULTS_DIR, "daily")
DAILY_BASE = dict(level_lookback=60, max_hold_bars=20, trend_len=50)


def daily_params(**kw) -> Params:
    return Params(**{**DAILY_BASE, **kw})


def _path(sym: str) -> str:
    return os.path.join(DATA_DIR, f"daily_{sym}.csv")


def fetch_daily(symbol: str, start: date) -> list[Bar]:
    out, token, retries = [], None, 0
    end = datetime.now(timezone.utc) - timedelta(minutes=16)
    while True:
        q = {"symbols": symbol, "timeframe": "1Day", "start": f"{start}T00:00:00Z", "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "limit": 10000, "adjustment": "all", "feed": "sip", "sort": "asc"}
        if token:
            q["page_token"] = token
        req = urllib.request.Request(f"{DATA_URL}/v2/stocks/bars?{urllib.parse.urlencode(q)}", headers=_alpaca_headers())
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                page = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                _time.sleep(5)
                continue
            raise RuntimeError(f"Alpaca data HTTP {e.code}: {e.read().decode()[:300]}") from None
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            retries += 1
            if retries > 4:
                raise RuntimeError(f"Alpaca data unreachable: {e}") from None
            _time.sleep(2 ** retries)
            continue
        retries = 0
        for r in (page.get("bars") or {}).get(symbol, []):
            # daily bars are stamped at midnight New York time; shift to the 09:30 open so `day` is right
            d = datetime.fromisoformat(r["t"].replace("Z", "+00:00"))
            t = int((d + timedelta(hours=9, minutes=30)).timestamp())
            out.append(Bar(symbol, t, r["o"], r["h"], r["l"], r["c"], r["v"]))
        token = page.get("next_page_token")
        if not token:
            break
    return out


def download(start: date = date(2016, 1, 1)) -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    out = {}
    for s in DAILY_UNIVERSE:
        bars = fetch_daily(s, start)
        with open(_path(s), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "o", "h", "l", "c", "v"])
            for b in bars:
                w.writerow([b.t, b.o, b.h, b.l, b.c, b.v])
        out[s] = bars
        print(f"{s}: {len(bars)} days" + (f" {bars[0].day} .. {bars[-1].day}" if bars else ""), flush=True)
    return out


def load() -> dict[str, list[Bar]]:
    out = {}
    for s in DAILY_UNIVERSE:
        if os.path.exists(_path(s)):
            with open(_path(s), newline="") as f:
                out[s] = [Bar(s, int(r["t"]), float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"]))
                          for r in csv.DictReader(f)]
    return out


def run_backtest(equity: float = 50_000.0) -> dict:
    from .engine import Backtest
    from .live import load_variants
    from .metrics import full_report
    from .walkforward import run as walk_forward
    bars = load()
    if not bars:
        raise SystemExit("no daily bars - run `python -m candle_patterns daily-download` first")
    os.makedirs(DAILY_OUT, exist_ok=True)
    wf = walk_forward(bars, base=daily_params(), equity=equity, out_path=os.path.join(DAILY_OUT, "backtest.json"),
                      min_bars_per_day=1)
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "daily_base": DAILY_BASE,
           "symbols": sorted(bars), "variants": {}}
    start = date.fromisoformat(wf["walk_forward_range"][0])
    for vid, v in load_variants().items():
        p = v["params"].with_(**DAILY_BASE)
        bt = Backtest(bars, p, equity, trade_from=start, min_bars_per_day=1).run()
        rep = full_report([t.to_dict() for t in bt.trades], bt.equity_curve, equity)
        out["variants"][vid] = {"label": v.get("label", vid), "summary": rep["summary"], "by_side": rep["by_side"],
                                "by_pattern": rep["by_pattern"], "by_symbol": rep["by_symbol"], "by_year": rep["by_year"],
                                "by_exit": rep["by_exit"]}
    with open(os.path.join(DAILY_OUT, "variants.json"), "w") as f:
        json.dump(out, f, indent=1)
    return {"walk_forward": wf, "variants": out}
