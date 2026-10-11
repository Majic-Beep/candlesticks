"""Strategy parameters, universe and paths.

Every rule of the strategy reads its numbers from `Params`, so the backtest, the walk-forward
optimiser and the live routine trade exactly the same thing.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, replace
from datetime import time
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
RESULTS_DIR = os.path.join(ROOT, "results")
DOCS_DIR = os.path.join(ROOT, "docs")

ET = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
# One-hour candles anchored at the open, like TradingView's regular-session 1h chart:
# 09:30 10:30 11:30 12:30 13:30 14:30 and the half-hour 15:30 candle.
HOUR_STARTS = [time(9, 30), time(10, 30), time(11, 30), time(12, 30), time(13, 30), time(14, 30), time(15, 30)]
BARS_PER_DAY = len(HOUR_STARTS)  # shorter (early-close) days get no new entries

# Paper money this bot may use on the shared Alpaca account (Sneaky Pivot and other bots trade there too).
# Override with the CP_BUDGET environment variable. Total exposure never exceeds this amount.
LIVE_BUDGET = 50_000.0

# Liquid, shortable US ETFs and large caps. Deliberately disjoint from the Sneaky Pivot universe, so the two
# bots never hold the same symbol on the shared account.
UNIVERSE = ["XLF", "XLE", "XLV", "SMH", "GLD", "TLT", "JPM", "AVGO", "NFLX", "COST", "LLY", "XOM"]

ALL_PATTERNS = ("engulfing", "pin_bar", "three_bar_reversal", "three_bar_continuation", "breakout", "shrinking")


@dataclass(frozen=True)
class Params:
    # --- key levels --------------------------------------------------------------------
    pivot_strength: int = 3         # a swing high/low needs this many lower highs / higher lows on each side
    level_lookback: int = 140       # candles (about 20 trading days) in which swing points count as levels
    touch_tol_atr: float = 0.10     # a level counts as tested if price came within this many ATR
    require_level: bool = True      # False = trade the patterns anywhere (shows what the levels add)
    # --- patterns ----------------------------------------------------------------------
    patterns: tuple = ALL_PATTERNS
    atr_len: int = 14               # ATR of the 1h candles, for tolerances and buffers
    body_avg_len: int = 20          # average body size: "large" and "small" candles are measured against it
    large_body: float = 1.2         # large candle: body >= this x average body
    small_body: float = 0.6         # small (consolidation) candle: body <= this x average body
    pin_wick: float = 0.66          # pin bar: the long wick is at least this share of the candle's range
    min_shrink: int = 3             # shrinking candles: at least this many same-colour candles, each smaller
    min_consolidation: int = 3      # breakout candles: at least this many small candles before the break
    trend_filter: bool = False      # long only above the 50-candle average of closes, short only below
    trend_len: int = 50
    long_only: bool = False         # trade only the bullish patterns (variant 3)
    # --- entry / exits -----------------------------------------------------------------
    stop_buffer_atr: float = 0.05   # stop sits this far beyond the pattern's extreme
    min_risk_atr: float = 0.25      # skip setups whose stop is closer than this many ATR (costs would dominate)
    rr: float = 2.0                 # take profit at rr x risk ("twice the stop loss")
    max_hold_bars: int = 35         # close at the next open after this many candles (5 trading days)
    tick: float = 0.01
    # --- costs and sizing --------------------------------------------------------------
    slippage_bps: float = 2.0       # per side, on market and stop fills
    commission_per_share: float = 0.0
    risk_pct: float = 0.005         # equity risked per trade (entry to stop)
    max_position_pct: float = 0.25  # max notional of one position as share of equity
    max_gross_pct: float = 1.0      # all open positions together, as share of equity
    qty_step: float = 1.0           # smallest tradable quantity: whole shares for stocks, fractions for crypto

    def to_dict(self) -> dict:
        d = asdict(self)
        d["patterns"] = list(self.patterns)
        return d

    @staticmethod
    def from_dict(d: dict) -> "Params":
        d = dict(d)
        if "patterns" in d:
            d["patterns"] = tuple(d["patterns"])
        known = Params.__dataclass_fields__
        return Params(**{k: v for k, v in d.items() if k in known})

    def with_(self, **kw) -> "Params":
        return replace(self, **kw)


# Small grid searched by the walk-forward optimiser (8 combinations). Every extra combination is another
# chance to fit noise, so it only touches what the video leaves open.
PARAM_GRID = {
    "trend_filter": [False, True],
    "touch_tol_atr": [0.10, 0.25],
    "rr": [1.5, 2.0],
}


def load_dotenv(path: str = os.path.join(ROOT, ".env")) -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
