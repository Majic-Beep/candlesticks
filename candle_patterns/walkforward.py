"""Walk-forward test with a sealed hold-out period.

    |--- development period -------------------------------------------|--- hold-out ---|
    | train 12m | test 3m |
          | train 12m | test 3m |
                ...                                      | train | test |
                                                          final params ->  traded once

- Parameters for every test window are chosen only from the train window before it.
- The stitched test windows form the walk-forward result: every trade in it was made with
  parameters that were picked without seeing that trade's data.
- The last `holdout_months` are never used for any choice. The parameters chosen on the last
  train window are traded over them once, as the final check.
- "Standard" runs the video rules with the default parameters, fixed before any data was seen,
  over the whole period. "In-sample" is the best grid point on the whole development period;
  it is shown only to make the optimism of hindsight visible.
"""
from __future__ import annotations

import itertools
import json
import os
from datetime import date, datetime, timezone

from .config import ET, PARAM_GRID, RESULTS_DIR, Params
from .data import Bar
from .engine import Backtest
from .metrics import full_report


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, 1)


def grid_params(base: Params, grid: dict) -> list[Params]:
    keys = list(grid)
    return [base.with_(**dict(zip(keys, vals))) for vals in itertools.product(*(grid[k] for k in keys))]


def _label(p: Params, grid: dict) -> str:
    return ", ".join(f"{k}={getattr(p, k)}" for k in grid)


def _mean_r(trades, lo: date, hi: date):
    """Mean R of the trades entered on or after `lo` and already closed before `hi`: positions are held for
    up to a week, so a trade that is still open at `hi` would leak later prices into a choice made at `hi`."""
    rs = [t.r for t in trades if lo <= date.fromisoformat(t.day) and date.fromisoformat(t.exit_time[:10]) < hi]
    return (sum(rs) / len(rs) if rs else None), len(rs)


def _bars_before(bars: dict[str, list[Bar]], cut: date) -> dict[str, list[Bar]]:
    return {s: [b for b in bl if b.day < cut] for s, bl in bars.items()}


def run(bars: dict[str, list[Bar]], base: Params = Params(), grid: dict = PARAM_GRID, train_months: int = 12,
        test_months: int = 3, holdout_months: int = 6, min_train_trades: int = 30, equity: float = 100_000.0,
        out_path: str = os.path.join(RESULTS_DIR, "backtest.json")) -> dict:
    days = sorted({b.day for bl in bars.values() for b in bl})
    if not days:
        raise SystemExit("no bars loaded - run `python -m candle_patterns download` first")
    first, last = days[0], days[-1]
    holdout_start = add_months(date(last.year, last.month, 1), -holdout_months + 1)
    wf_start = add_months(date(first.year, first.month, 1), train_months + 1)  # +1 month warm-up for levels
    if wf_start >= holdout_start:
        raise SystemExit(f"not enough history: need > {train_months + holdout_months + 1} months, "
                         f"have {first} .. {last}")
    dev = _bars_before(bars, holdout_start)

    # 1) every grid point once over the development period (R-multiples do not depend on sizing)
    combos = grid_params(base, grid)
    runs = [Backtest(dev, p, equity).run() for p in combos]

    # 2) choose per window from the preceding train window only
    windows, schedule = [], []
    ws = wf_start
    while ws < holdout_start:
        we = min(add_months(ws, test_months), holdout_start)
        tr_lo = add_months(ws, -train_months)
        best, best_score, scores = None, None, []
        for p, r in zip(combos, runs):
            m, n = _mean_r(r.trades, tr_lo, ws)
            scores.append({"params": _label(p, grid), "train_expectancy_r": None if m is None else round(m, 3),
                           "train_trades": n})
            if m is not None and n >= min_train_trades and (best_score is None or m > best_score):
                best, best_score = p, m
        chosen = best or base
        schedule.append((ws, we, chosen))
        windows.append({"train": [str(tr_lo), str(ws)], "test": [str(ws), str(we)],
                        "chosen": _label(chosen, grid), "train_expectancy_r": None if best_score is None else round(best_score, 3),
                        "scores": scores})
        ws = we

    def params_for_day(t: int) -> Params:
        d = datetime.fromtimestamp(t, ET).date()
        for lo, hi, p in schedule:
            if lo <= d < hi:
                return p
        return schedule[-1][2] if d >= schedule[-1][1] else schedule[0][2]

    wf = Backtest(dev, params_for_day, equity, trade_from=wf_start).run()

    # 3) final parameters: chosen on the last train window before the hold-out, then sealed
    final, final_score = None, None
    for p, r in zip(combos, runs):
        m, n = _mean_r(r.trades, add_months(holdout_start, -train_months), holdout_start)
        if m is not None and n >= min_train_trades and (final_score is None or m > final_score):
            final, final_score = p, m
    final = final or base
    hold = Backtest(bars, final, equity, trade_from=holdout_start).run()

    # 4) references
    std = Backtest(bars, base, equity, trade_from=wf_start).run()
    is_scores = [(_mean_r(r.trades, wf_start, holdout_start)[0] or -9, p, r) for p, r in zip(combos, runs)]
    _, is_p, _ = max(is_scores, key=lambda x: x[0])
    ins = Backtest(dev, is_p, equity, trade_from=wf_start).run()

    def rep(bt: Backtest) -> dict:
        r = full_report([t.to_dict() for t in bt.trades], bt.equity_curve, equity)
        r["signals"] = len(bt.signals)
        return r

    variants = []
    for p, r in zip(combos, runs):
        ts = [t for t in r.trades if wf_start <= date.fromisoformat(t.day) < holdout_start]
        rep_ = full_report([t.to_dict() for t in ts], [], equity)["summary"]
        variants.append({"params": _label(p, grid), "trades": rep_["trades"], "expectancy_r": rep_["expectancy_r"],
                         "r_tstat": rep_["r_tstat"], "win_rate_pct": rep_["win_rate_pct"],
                         "pnl": round(sum(t.pnl for t in ts), 2)})

    result = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "symbols": sorted(bars),
        "data_range": [str(first), str(last)],
        "walk_forward_range": [str(wf_start), str(holdout_start)],
        "holdout_range": [str(holdout_start), str(last)],
        "train_months": train_months, "test_months": test_months, "holdout_months": holdout_months,
        "grid": grid,
        "base_params": base.to_dict(),
        "final_params": final.to_dict(),
        "in_sample_params": is_p.to_dict(),
        "windows": windows,
        "variants": variants,
        "walk_forward": rep(wf),
        "holdout": rep(hold),
        "standard": rep(std),
        "in_sample": rep(ins),
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, separators=(",", ":"))
    with open(os.path.join(os.path.dirname(out_path), "live_params.json"), "w") as f:
        json.dump({"chosen_on": [str(add_months(holdout_start, -train_months)), str(holdout_start)],
                   "params": final.to_dict()}, f, indent=2)
    return result
