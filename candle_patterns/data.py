"""Price data: Alpaca 30-minute bars, CSV cache and 1-hour candles anchored at the 09:30 open.

Only regular-session bars (09:30-16:00 New York) are kept. Timestamps are bar *start* times in Unix
seconds (UTC). Two 30-minute bars make one 1-hour candle (09:30, 10:30, ... 14:30); the 15:30 candle is the
last half hour, as on TradingView's regular-session chart.
"""
from __future__ import annotations

import csv
import json
import os
import time as _time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from .config import DATA_DIR, ET, HOUR_STARTS, load_dotenv

DATA_URL = os.environ.get("ALPACA_DATA_URL", "https://data.alpaca.markets")


@dataclass(frozen=True)
class Bar:
    symbol: str
    t: int          # bar start, unix seconds UTC
    o: float
    h: float
    l: float
    c: float
    v: float

    @property
    def et(self) -> datetime:
        return datetime.fromtimestamp(self.t, ET)

    @property
    def day(self) -> date:
        return self.et.date()

    @property
    def clock(self) -> time:
        return self.et.time()


def is_rth(t: int) -> bool:
    c = datetime.fromtimestamp(t, ET).time()
    return time(9, 30) <= c < time(16, 0)


def clean(bars: list[Bar]) -> list[Bar]:
    """Sort, de-duplicate and keep regular-session bars only."""
    seen, out = set(), []
    for b in sorted(bars, key=lambda b: b.t):
        if b.t in seen or not is_rth(b.t):
            continue
        seen.add(b.t)
        out.append(b)
    return out


def to_hourly(bars: list[Bar]) -> list[Bar]:
    """Group intraday bars (any size that divides 30 minutes) into session-anchored 1-hour candles.
    A candle is emitted only for the hour slots that have data; it starts at the slot start."""
    out: list[Bar] = []
    cur, key = None, None
    for b in clean(bars):
        et = b.et
        mins = et.hour * 60 + et.minute - (9 * 60 + 30)
        slot = HOUR_STARTS[min(mins // 60, len(HOUR_STARTS) - 1)]
        k = (et.date(), slot)
        if k != key:
            if cur:
                out.append(cur)
            start = datetime.combine(et.date(), slot, ET)
            cur, key = Bar(b.symbol, int(start.timestamp()), b.o, b.h, b.l, b.c, b.v), k
        else:
            cur = Bar(b.symbol, cur.t, cur.o, max(cur.h, b.h), min(cur.l, b.l), b.c, cur.v + b.v)
    if cur:
        out.append(cur)
    return out


# ---------------------------------------------------------------- CSV cache (30-minute bars)
def csv_path(symbol: str) -> str:
    return os.path.join(DATA_DIR, f"{symbol}_30m.csv")


def save_csv(symbol: str, bars: list[Bar]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(csv_path(symbol), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "o", "h", "l", "c", "v"])
        for b in bars:
            w.writerow([b.t, b.o, b.h, b.l, b.c, b.v])


def load_csv(symbol: str, path: str | None = None) -> list[Bar]:
    with open(path or csv_path(symbol), newline="") as f:
        rows = list(csv.DictReader(f))
    return clean([Bar(symbol, int(float(r["t"])), float(r["o"]), float(r["h"]), float(r["l"]),
                      float(r["c"]), float(r.get("v") or 0)) for r in rows])


def bars_from_rows(symbol: str, rows: list[dict]) -> list[Bar]:
    return clean([Bar(symbol, int(r["t"]), float(r["o"]), float(r["h"]), float(r["l"]),
                      float(r["c"]), float(r.get("v", 0))) for r in rows])


def load_tradingview_json(path: str) -> dict[str, list[Bar]]:
    """Bars saved from the TradingView `get_ohlcv` tool (30m or 15m interval):
    {"XLF": [{t,o,h,l,c,v}, ...], ...} or {"XLF": {"bars": [...]}}. Returned as 1-hour candles."""
    with open(path) as f:
        raw = json.load(f)
    return {s: to_hourly(bars_from_rows(s, p["bars"] if isinstance(p, dict) else p)) for s, p in raw.items()}


# ---------------------------------------------------------------- Alpaca market data
def _alpaca_headers() -> dict:
    load_dotenv()
    key = os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        raise RuntimeError("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY missing (.env or environment)")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_alpaca(symbols: list[str], start: datetime, end: datetime | None = None,
                 feed: str = "sip") -> dict[str, list[Bar]]:
    """Download split/dividend-adjusted 30-minute bars. The free plan allows SIP history that is older than
    15 minutes; if SIP is refused we fall back to the IEX feed."""
    end = end or datetime.now(timezone.utc) - timedelta(minutes=16)
    headers = _alpaca_headers()
    out: dict[str, list[Bar]] = {s: [] for s in symbols}
    token, retries = None, 0
    while True:
        q = {"symbols": ",".join(symbols), "timeframe": "30Min", "start": _iso(start), "end": _iso(end),
             "limit": 10000, "adjustment": "all", "feed": feed, "sort": "asc"}
        if token:
            q["page_token"] = token
        req = urllib.request.Request(f"{DATA_URL}/v2/stocks/bars?{urllib.parse.urlencode(q)}", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                page = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 403 and feed == "sip":
                return fetch_alpaca(symbols, start, end, feed="iex")
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
        for sym, rows in (page.get("bars") or {}).items():
            for r in rows:
                t = int(datetime.fromisoformat(r["t"].replace("Z", "+00:00")).timestamp())
                out[sym].append(Bar(sym, t, r["o"], r["h"], r["l"], r["c"], r["v"]))
        token = page.get("next_page_token")
        if not token:
            break
    return {s: clean(b) for s, b in out.items()}


def update_cache(symbols: list[str], start: date) -> dict[str, list[Bar]]:
    """Download everything from `start` and write data/<SYM>_30m.csv."""
    out = {}
    for s in symbols:  # one symbol at a time, so a broken connection loses little
        b = fetch_alpaca([s], datetime(start.year, start.month, start.day, tzinfo=ET))[s]
        if b:
            save_csv(s, b)
        out[s] = b
        print(f"{s}: {len(b)} bars", flush=True)
    return out


def load_universe(symbols: list[str]) -> dict[str, list[Bar]]:
    """1-hour candles for every symbol that has a cached CSV."""
    return {s: to_hourly(load_csv(s)) for s in symbols if os.path.exists(csv_path(s))}
