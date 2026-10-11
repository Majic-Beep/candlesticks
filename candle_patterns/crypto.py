"""Crypto backtest: the same strategy and engine on Alpaca crypto 1-hour candles (24/7, UTC hours).

    python -m candle_patterns crypto-download   # 1-hour bars since 2021 -> data/crypto_<SYM>_1h.csv
    python -m candle_patterns crypto-backtest   # walk-forward + hold-out -> results/crypto/backtest.json

Differences to the stock version: no trading session (every hour is a candle, every day is tradable), clock-hour
candles, and higher costs (Alpaca crypto taker fee plus spread, `CRYPTO_COST_BPS` per side on every fill).
Alpaca paper trading does not allow crypto shorts, so only long variants could be paper-traded.
"""
from __future__ import annotations

import csv
import json
import os
import time as _time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .config import DATA_DIR, RESULTS_DIR, Params
from .data import DATA_URL, Bar, _alpaca_headers, _iso

CRYPTO_UNIVERSE = ["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "LTC/USD", "LINK/USD", "AVAX/USD"]
CRYPTO_COST_BPS = 30.0  # per side: Alpaca taker fee 0.25 % + spread/slippage
CRYPTO_QTY_STEP = 0.0001  # crypto is traded in fractions
CRYPTO_OUT = os.path.join(RESULTS_DIR, "crypto")


def crypto_params(**kw) -> Params:
    """Stock parameters with crypto costs; the targets are limit orders but pay the fee as well."""
    return Params(slippage_bps=CRYPTO_COST_BPS, qty_step=CRYPTO_QTY_STEP, **kw)


def _path(sym: str) -> str:
    return os.path.join(DATA_DIR, f"crypto_{sym.replace('/', '')}_1h.csv")


def fetch_crypto(symbols: list[str], start: datetime, end: datetime | None = None) -> dict[str, list[Bar]]:
    end = end or datetime.now(timezone.utc)
    out: dict[str, list[Bar]] = {s: [] for s in symbols}
    token, retries = None, 0
    while True:
        q = {"symbols": ",".join(symbols), "timeframe": "1Hour", "start": _iso(start), "end": _iso(end), "limit": 10000}
        if token:
            q["page_token"] = token
        req = urllib.request.Request(f"{DATA_URL}/v1beta3/crypto/us/bars?{urllib.parse.urlencode(q)}",
                                     headers=_alpaca_headers())
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                page = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                _time.sleep(5)
                continue
            raise RuntimeError(f"Alpaca crypto data HTTP {e.code}: {e.read().decode()[:300]}") from None
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            retries += 1
            if retries > 4:
                raise RuntimeError(f"Alpaca crypto data unreachable: {e}") from None
            _time.sleep(2 ** retries)
            continue
        retries = 0
        for sym, rows in (page.get("bars") or {}).items():
            for r in rows:
                t = int(datetime.fromisoformat(r["t"].replace("Z", "+00:00")).timestamp())
                out[sym].append(Bar(sym, t, r["o"], r["h"], r["l"], r["c"], r["v"]))
        token = page.get("next_page_token")
        if not token:
            break
    return {s: sorted({b.t: b for b in bl}.values(), key=lambda b: b.t) for s, bl in out.items()}


def download(symbols=CRYPTO_UNIVERSE, start: datetime = datetime(2021, 1, 1, tzinfo=timezone.utc)) -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    out = {}
    for s in symbols:
        bars = fetch_crypto([s], start)[s]
        with open(_path(s), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "o", "h", "l", "c", "v"])
            for b in bars:
                w.writerow([b.t, b.o, b.h, b.l, b.c, b.v])
        out[s] = bars
        print(f"{s}: {len(bars)} bars", flush=True)
    return out


def load(symbols=CRYPTO_UNIVERSE) -> dict[str, list[Bar]]:
    out = {}
    for s in symbols:
        if os.path.exists(_path(s)):
            with open(_path(s), newline="") as f:
                out[s] = [Bar(s, int(r["t"]), float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]),
                              float(r["v"])) for r in csv.DictReader(f)]
    return out


def coverage(bars: dict[str, list[Bar]]) -> dict:
    """Share of the hours of each year that have a candle (Alpaca crypto data has gaps in thin hours)."""
    rep = {}
    for s, bl in bars.items():
        years = {}
        for b in bl:
            y = datetime.fromtimestamp(b.t, timezone.utc).year
            years[y] = years.get(y, 0) + 1
        rep[s] = {y: round(n / (24 * (366 if y % 4 == 0 else 365)), 3) for y, n in sorted(years.items())}
    return rep


def drop_before_gaps(bars: list[Bar], max_gap_hours: int = 72) -> list[Bar]:
    """Keep only the candles after the last data gap longer than `max_gap_hours` (SOL had no Alpaca data for
    most of 2023/24); a position must never stay open across such a hole."""
    start = 0
    for i in range(1, len(bars)):
        if bars[i].t - bars[i - 1].t > max_gap_hours * 3600:
            start = i
    return bars[start:]


def run_backtest(equity: float = 50_000.0) -> dict:
    from .engine import Backtest
    from .live import load_variants
    from .metrics import full_report
    from .walkforward import run as walk_forward
    bars = {s: drop_before_gaps(b) for s, b in load().items()}
    if not bars:
        raise SystemExit("no crypto bars - run `python -m candle_patterns crypto-download` first")
    os.makedirs(CRYPTO_OUT, exist_ok=True)
    wf = walk_forward(bars, base=crypto_params(), equity=equity, out_path=os.path.join(CRYPTO_OUT, "backtest.json"))
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "cost_bps_per_side": CRYPTO_COST_BPS,
           "symbols": sorted(bars), "start": {s: str(datetime.fromtimestamp(b[0].t, timezone.utc).date()) for s, b in bars.items()},
           "variants": {}}
    start = datetime.fromisoformat(wf["walk_forward_range"][0]).date()
    for vid, v in load_variants().items():
        p = v["params"].with_(slippage_bps=CRYPTO_COST_BPS, qty_step=CRYPTO_QTY_STEP)
        bt = Backtest(bars, p, equity, trade_from=start).run()
        rep = full_report([t.to_dict() for t in bt.trades], bt.equity_curve, equity)
        out["variants"][vid] = {"label": v.get("label", vid), "summary": rep["summary"], "by_side": rep["by_side"],
                                "by_pattern": rep["by_pattern"], "by_symbol": rep["by_symbol"], "by_year": rep["by_year"],
                                "by_exit": rep["by_exit"]}
    with open(os.path.join(CRYPTO_OUT, "variants.json"), "w") as f:
        json.dump(out, f, indent=1)
    return {"walk_forward": wf, "variants": out}
