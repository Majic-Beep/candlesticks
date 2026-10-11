"""5-minute backtest on stocks: the same six patterns and engine on 5-minute candles, flat every evening.

    python -m candle_patterns m5-download     # Alpaca 5-minute bars since 2021 -> data/m5_<SYM>.csv
    python -m candle_patterns m5-backtest     # walk-forward + hold-out + variants -> results/m5/

Bar-count parameters stay as on the 1h chart (levels from the last 140 candles, trend = 50 candles, close after
35 candles at the latest), which here means levels from about two days, a 4-hour trend and at most 3 hours in a
trade. Intraday only: no new signal after the 15:45 candle, open positions closed at the open of the 15:55 candle.
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

from .config import DATA_DIR, ET, RESULTS_DIR, UNIVERSE, Params
from .data import DATA_URL, Bar, _alpaca_headers, _iso, clean

M5_OUT = os.path.join(RESULTS_DIR, "m5")
M5_BASE = dict(last_entry="15:45", flat_at="15:55")
BARS_PER_DAY_M5 = 78  # 09:30 .. 15:55; shorter (early-close) days get no new entries


def m5_params(**kw) -> Params:
    return Params(**{**M5_BASE, **kw})


def _path(sym: str) -> str:
    return os.path.join(DATA_DIR, f"m5_{sym}.csv")


def fetch(symbol: str, start: date) -> list[Bar]:
    out, token, retries = [], None, 0
    end = datetime.now(timezone.utc) - timedelta(minutes=16)
    while True:
        q = {"symbols": symbol, "timeframe": "5Min", "start": _iso(datetime(start.year, start.month, start.day, tzinfo=ET)),
             "end": _iso(end), "limit": 10000, "adjustment": "all", "feed": "sip", "sort": "asc"}
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
            t = int(datetime.fromisoformat(r["t"].replace("Z", "+00:00")).timestamp())
            out.append(Bar(symbol, t, r["o"], r["h"], r["l"], r["c"], r["v"]))
        token = page.get("next_page_token")
        if not token:
            break
    return clean(out)


def download(start: date = date(2021, 1, 1), symbols: list[str] = UNIVERSE) -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    out = {}
    for s in symbols:
        bars = fetch(s, start)
        with open(_path(s), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "o", "h", "l", "c", "v"])
            for b in bars:
                w.writerow([b.t, b.o, b.h, b.l, b.c, b.v])
        out[s] = bars
        print(f"{s}: {len(bars)} bars" + (f" {bars[0].day} .. {bars[-1].day}" if bars else ""), flush=True)
    return out


def load(symbols: list[str] = UNIVERSE) -> dict[str, list[Bar]]:
    out = {}
    for s in symbols:
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
        raise SystemExit("no 5-minute bars - run `python -m candle_patterns m5-download` first")
    os.makedirs(M5_OUT, exist_ok=True)
    wf = walk_forward(bars, base=m5_params(), equity=equity, out_path=os.path.join(M5_OUT, "backtest.json"),
                      min_bars_per_day=BARS_PER_DAY_M5)
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "m5_base": M5_BASE,
           "symbols": sorted(bars), "variants": {}}
    start = date.fromisoformat(wf["walk_forward_range"][0])
    for vid, v in load_variants().items():
        bt = Backtest(bars, v["params"].with_(**M5_BASE), equity, trade_from=start, min_bars_per_day=BARS_PER_DAY_M5).run()
        rep = full_report([t.to_dict() for t in bt.trades], bt.equity_curve, equity)
        out["variants"][vid] = {"label": v.get("label", vid), "summary": rep["summary"], "by_side": rep["by_side"],
                                "by_pattern": rep["by_pattern"], "by_symbol": rep["by_symbol"], "by_year": rep["by_year"],
                                "by_exit": rep["by_exit"]}
    with open(os.path.join(M5_OUT, "variants.json"), "w") as f:
        json.dump(out, f, indent=1)
    return {"walk_forward": wf, "variants": out}
