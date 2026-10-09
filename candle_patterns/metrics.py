"""Performance statistics for a list of trades and a daily equity curve."""
from __future__ import annotations

import math
from collections import defaultdict


def _mean(x):
    return sum(x) / len(x) if x else 0.0


def _std(x):
    if len(x) < 2:
        return 0.0
    m = _mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def drawdown_series(equity: list[float]) -> list[float]:
    peak, out = -math.inf, []
    for e in equity:
        peak = max(peak, e)
        out.append(e / peak - 1 if peak > 0 else 0.0)
    return out


def summarize(trades: list[dict], curve: list[tuple[str, float]], start_equity: float) -> dict:
    eq = [start_equity] + [e for _, e in curve]
    rets = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq)) if eq[i - 1] > 0]
    years = len(curve) / 252 if curve else 0
    final = eq[-1]
    dd = drawdown_series(eq)
    pnl = [t["pnl"] for t in trades]
    rs = [t["r"] for t in trades]
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p <= 0]
    sd = _std(rets)
    downside = [r for r in rets if r < 0]
    dsd = math.sqrt(sum(r * r for r in downside) / len(rets)) if rets else 0.0
    r_sd = _std(rs)
    out = {
        "start_equity": start_equity,
        "final_equity": round(final, 2),
        "net_profit": round(final - start_equity, 2),
        "total_return_pct": round((final / start_equity - 1) * 100, 2) if start_equity else 0.0,
        "cagr_pct": round(((final / start_equity) ** (1 / years) - 1) * 100, 2) if years > 0 and final > 0 else 0.0,
        "max_drawdown_pct": round(min(dd) * 100, 2) if dd else 0.0,
        "sharpe": round(_mean(rets) / sd * math.sqrt(252), 2) if sd > 0 else 0.0,
        "sortino": round(_mean(rets) / dsd * math.sqrt(252), 2) if dsd > 0 else 0.0,
        "trades": len(trades),
        "trading_days": len(curve),
        "win_rate_pct": round(len(wins) / len(pnl) * 100, 1) if pnl else 0.0,
        "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0 else None,
        "avg_win": round(_mean(wins), 2),
        "avg_loss": round(_mean(losses), 2),
        "expectancy_r": round(_mean(rs), 3),
        "r_tstat": round(_mean(rs) / (r_sd / math.sqrt(len(rs))), 2) if len(rs) > 1 and r_sd > 0 else 0.0,
        "best_trade": round(max(pnl), 2) if pnl else 0.0,
        "worst_trade": round(min(pnl), 2) if pnl else 0.0,
    }
    out["calmar"] = round(out["cagr_pct"] / -out["max_drawdown_pct"], 2) if out["max_drawdown_pct"] < 0 else None
    return out


def breakdown(trades: list[dict], key) -> list[dict]:
    groups = defaultdict(list)
    for t in trades:
        groups[key(t)].append(t)
    rows = []
    for k in sorted(groups):
        g = groups[k]
        pnl = [t["pnl"] for t in g]
        rows.append({"key": k, "trades": len(g), "pnl": round(sum(pnl), 2),
                     "win_rate_pct": round(sum(1 for p in pnl if p > 0) / len(g) * 100, 1),
                     "expectancy_r": round(_mean([t["r"] for t in g]), 3)})
    return rows


def full_report(trades: list[dict], curve: list[tuple[str, float]], start_equity: float) -> dict:
    eq = [e for _, e in curve]
    return {
        "summary": summarize(trades, curve, start_equity),
        "equity": [{"d": d, "e": e} for d, e in curve],
        "drawdown": [{"d": d, "dd": round(x * 100, 3)} for (d, _), x in zip(curve, drawdown_series(eq))],
        "by_symbol": breakdown(trades, lambda t: t["symbol"]),
        "by_side": breakdown(trades, lambda t: t["side"]),
        "by_pattern": breakdown(trades, lambda t: t["pattern"]),
        "by_exit": breakdown(trades, lambda t: t["reason"]),
        "by_month": breakdown(trades, lambda t: t["day"][:7]),
        "by_year": breakdown(trades, lambda t: t["day"][:4]),
        "trades": trades,
    }
