"""Paper trading on Alpaca with exactly the same signal code as the backtest.

Several frozen variants (results/live_variants.json) trade side by side on the same account, each with its
own share of the budget, so their live results can be compared.

`run` is called one minute after every 1-hour candle closes (10:31, 11:31, ... 15:31 and 16:01 ET):
    1. time exit: positions held for `max_hold_bars` candles are closed at market (backtest: next open)
    2. entries: the candle that just closed is checked for a pattern at a key level; a signal becomes a
       market bracket order (stop + take profit, good till cancelled). After 16:00 Alpaca queues it for the
       next open, which is where the backtest fills it too.
`sync` reads fills back from Alpaca into results/live.json for the dashboard.

Every order this bot sends has a client_order_id "cp-<variant>-<signal candle YYYYMMDDHHMM>-<symbol>", the
time exits the same id plus "-x", so other orders on the account are never touched.
"""
from __future__ import annotations

import csv
import json
import os
import re
import time as _time
from datetime import date, datetime, timedelta, timezone

from .alpaca import Alpaca, AlpacaError
from .config import ET, LIVE_BUDGET, RESULTS_DIR, UNIVERSE, Params
from .data import Bar, fetch_alpaca, to_hourly
from .engine import Backtest
from .metrics import full_report
from .strategy import CandlePatterns, floor_qty

SIGNALS_CSV = os.path.join(RESULTS_DIR, "live_signals.csv")
LIVE_JSON = os.path.join(RESULTS_DIR, "live.json")
STATE_JSON = os.path.join(RESULTS_DIR, "live_state.json")
VARIANTS_JSON = os.path.join(RESULTS_DIR, "live_variants.json")
PREFIX = "cp-"
CID = re.compile(r"^cp-(v\d+)-(\d{12})-([A-Z.]+)(-x)?$")
OPEN_STATES = ("new", "accepted", "pending_new", "held", "accepted_for_bidding", "partially_filled")
DONE_STATES = ("canceled", "expired", "rejected")
LATE_MINUTES = 15  # a signal is only acted on within this many minutes after its candle closed
SIGNAL_FIELDS = ["variant", "time", "symbol", "side", "pattern", "ref", "stop", "target", "level", "qty",
                 "status", "order_id"]


def _now() -> datetime:
    return datetime.now(ET)


def log(*a):
    print(_now().strftime("%Y-%m-%d %H:%M:%S ET"), *a, flush=True)


def load_variants() -> dict:
    """{vid: {"label", "note", "budget_share", "params": Params}} in a stable order."""
    with open(VARIANTS_JSON) as f:
        raw = json.load(f)["variants"]
    return {k: {**v, "params": Params.from_dict(v["params"])} for k, v in sorted(raw.items())}


def _state() -> dict:
    if os.path.exists(STATE_JSON):
        with open(STATE_JSON) as f:
            return json.load(f)
    return {}


def _save_state(s: dict) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(STATE_JSON, "w") as f:
        json.dump(s, f, indent=2)


def _init_state(today: date, variants: dict, save: bool = True) -> dict:
    st = _state()
    st.setdefault("live_start", str(today))
    st.setdefault("budget", float(os.environ.get("CP_BUDGET") or LIVE_BUDGET))
    vs = st.setdefault("variants", {})
    for vid, v in variants.items():
        vs.setdefault(vid, {"budget": round(st["budget"] * v["budget_share"], 2), "start": str(today)})
    if save:
        _save_state(st)
    return st


def parse_cid(cid: str | None):
    """(variant, signal candle 'YYYYMMDDHHMM', symbol, is_exit) or None for orders that are not ours."""
    m = CID.match(cid or "")
    return (m.group(1), m.group(2), m.group(3), bool(m.group(4))) if m else None


def _parse_ts(iso: str | None) -> datetime | None:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET) if iso else None


def _session(api: Alpaca, d: date) -> tuple[datetime, datetime] | None:
    cal = api.calendar(str(d), str(d))
    if not cal or cal[0]["date"] != str(d):
        return None
    hm = lambda s: datetime.combine(d, datetime.strptime(s, "%H:%M").time(), ET)
    return hm(cal[0]["open"]), hm(cal[0]["close"])


# ------------------------------------------------------------------ candles
def closed_candles(bars30: list[Bar], now: datetime, session_close: datetime | None) -> list[Bar]:
    """1-hour candles whose end is not after `now`. A candle ends 60 minutes after its start, the 15:30
    candle at 16:00, and every candle at the latest at today's (possibly early) close."""
    out = []
    for c in to_hourly(bars30):
        end = c.et + timedelta(minutes=60)
        end = min(end, datetime.combine(c.day, datetime.min.time(), ET).replace(hour=16))
        if session_close is not None and c.day == session_close.date():
            end = min(end, session_close)
        if end <= now:
            out.append(c)
    return out


def fetch_recent(symbols: list[str], now: datetime, days: int = 60) -> dict[str, list[Bar]]:
    """30-minute bars of the last `days` days: SIP where the free plan allows it (older than 15 minutes),
    IEX for the last minutes."""
    start = datetime.combine(now.date() - timedelta(days=days), datetime.min.time(), ET)
    cut = now - timedelta(minutes=16)
    sip = fetch_alpaca(symbols, start, cut)
    iex = fetch_alpaca(symbols, cut - timedelta(hours=2), now, feed="iex")
    out = {}
    for s in symbols:
        have = {b.t for b in sip.get(s, [])}
        out[s] = sorted(sip.get(s, []) + [b for b in iex.get(s, []) if b.t not in have and b.t >= cut.timestamp() - 1800],
                        key=lambda b: b.t)
    return out


def full_days(candles: list[Bar], today: date, today_full: bool) -> set[date]:
    from collections import Counter
    from .config import BARS_PER_DAY
    days = {d for d, n in Counter(c.day for c in candles).items() if n >= BARS_PER_DAY and d != today}
    return days | ({today} if today_full else set())


def latest_signal(symbol: str, params: Params, candles: list[Bar], tradable: set[date]):
    """The signal of the last closed candle, computed exactly as in the backtest (None if there is none)."""
    st = CandlePatterns(symbol, params)
    sig = None
    for c in candles:
        sig = st.on_bar(c, tradable=c.day in tradable)
    return sig if sig is not None and candles and sig.t == candles[-1].t else None


# ------------------------------------------------------------------ positions of this bot
def our_orders(api: Alpaca, since: datetime) -> list[dict]:
    after = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out, seen = [], set()
    while True:
        page = api.orders("all", after)
        new = [o for o in page if o["id"] not in seen]
        if not new:
            break
        for o in new:
            seen.add(o["id"])
            if parse_cid(o.get("client_order_id")):
                out.append(o)
        if len(page) < 500:
            break
        after = page[-1]["submitted_at"]
    return out


def open_entries(orders: list[dict]) -> list[dict]:
    """Entry orders whose position is still open (filled, no exit leg filled, no time exit) or still pending."""
    exits = {o["client_order_id"][:-2]: o for o in orders if o["client_order_id"].endswith("-x")}
    out = []
    for o in orders:
        p = parse_cid(o["client_order_id"])
        if p[3] or o["status"] in DONE_STATES:
            continue
        legs = o.get("legs") or []
        if any(l["status"] == "filled" for l in legs):
            continue
        x = exits.get(o["client_order_id"])
        if x and x["status"] not in DONE_STATES:
            continue
        out.append(o)
    return out


def candles_held(o: dict, candles: list[Bar]) -> int:
    """Closed 1-hour candles since the entry, counting the candle in which it was filled."""
    filled = _parse_ts(o.get("filled_at"))
    if filled is None:
        return 0
    return sum(1 for c in candles if c.et + timedelta(minutes=60) > filled)


# ------------------------------------------------------------------ commands
def cmd_run(symbols=UNIVERSE, dry_run: bool = False) -> None:
    api, variants = Alpaca(), load_variants()
    now = _now()
    today = now.date()
    sess = _session(api, today)
    if sess is None:
        log("market closed today - nothing to do")
        return
    if now < sess[0] + timedelta(minutes=60):
        log("first candle not closed yet - nothing to do")
        return
    st = _init_state(today, variants, save=not dry_run)
    data = fetch_recent(symbols, now)
    candles = {s: closed_candles(b, now, sess[1]) for s, b in data.items()}
    orders = our_orders(api, now - timedelta(days=21))
    positions = {p["symbol"]: float(p["qty"]) for p in api.positions()}

    # 1) time exits
    open_ = open_entries(orders)
    for o in open_:
        vid, _, sym, _ = parse_cid(o["client_order_id"])
        if vid not in variants or float(o.get("filled_qty") or 0) <= 0:
            continue
        held = candles_held(o, candles.get(sym, []))
        if held < variants[vid]["params"].max_hold_bars:
            continue
        qty = int(float(o["filled_qty"]))
        log(f"[{vid}] {sym}: held {held} candles -> time exit {qty}")
        if dry_run:
            continue
        for l in o.get("legs") or []:
            if l["status"] in OPEN_STATES:
                api.cancel(l["id"])
        _time.sleep(2)
        try:
            api.submit(symbol=sym, qty=str(qty), side="sell" if o["side"] == "buy" else "buy", type="market",
                       time_in_force="day", client_order_id=o["client_order_id"] + "-x")
            positions[sym] = positions.get(sym, 0) - qty * (1 if o["side"] == "buy" else -1)
        except AlpacaError as e:
            log(f"[{vid}] {sym}: time exit FAILED {e}")
    open_ = open_entries(our_orders(api, now - timedelta(days=21))) if not dry_run else open_

    # 2) entries on the candle that just closed
    last_close = max((c.t for cl in candles.values() for c in cl), default=None)
    if last_close is None:
        log("no candles")
        return
    last_end = min(datetime.fromtimestamp(last_close, ET) + timedelta(minutes=60), sess[1])
    if now - last_end > timedelta(minutes=LATE_MINUTES):
        log(f"last candle closed at {last_end:%H:%M}, now {now:%H:%M} - too late for entries")
        return
    tradable_today = sess[1].hour == 16 and sess[1].minute == 0
    ours = {}  # symbol -> side held or pending by any variant
    for o in open_:
        ours.setdefault(o["symbol"], set()).add(1 if o["side"] == "buy" else -1)
    foreign = {s for s, q in positions.items() if abs(q) > 0}
    foreign |= {o["symbol"] for o in api.orders("open") if not (o.get("client_order_id") or "").startswith(PREFIX)}
    foreign -= set(ours)  # our own bracket legs are open orders without our prefix
    order_of_variants = list(variants)
    if (last_close // 3600) % 2:  # opposite-side conflicts between variants: priority alternates
        order_of_variants.reverse()
    rows = []
    for vid in order_of_variants:
        params = variants[vid]["params"]
        vstate = st["variants"][vid]
        budget = vstate["budget"] + _realised_pnl(vid)
        gross_cap = min(budget, vstate["budget"]) * params.max_gross_pct  # never more than the start budget
        mine = [o for o in open_ if parse_cid(o["client_order_id"])[0] == vid]
        used = sum(float(o["qty"]) * _price(o) for o in mine)
        used += sum(float(r["qty"]) * r["ref"] for r in rows if r["variant"] == vid and r["status"] == "submitted")
        for s in symbols:
            cl = candles.get(s) or []
            if not cl or cl[-1].t != last_close:
                continue
            sig = latest_signal(s, params, cl, full_days(cl, today, tradable_today))
            if sig is None:
                continue
            qty = floor_qty(min(budget * params.risk_pct / sig.risk, budget * params.max_position_pct / sig.ref,
                                max(0.0, gross_cap - used) / sig.ref))
            stamp = datetime.fromtimestamp(sig.t, ET).strftime("%Y%m%d%H%M")
            cid = f"{PREFIX}{vid}-{stamp}-{s}"
            row = {"variant": vid, "time": datetime.fromtimestamp(sig.t, ET).strftime("%Y-%m-%d %H:%M"), "symbol": s,
                   "side": "long" if sig.side > 0 else "short", "pattern": sig.pattern, "ref": sig.ref,
                   "stop": sig.stop, "target": sig.target, "level": sig.level, "qty": qty, "status": "", "order_id": ""}
            if s in foreign:
                row["status"] = "skipped: symbol held or traded by another bot"
            elif any(parse_cid(o["client_order_id"])[0] == vid and o["symbol"] == s for o in open_):
                row["status"] = "skipped: position already open"
            elif ours.get(s, {sig.side}) != {sig.side}:
                row["status"] = "skipped: other variant holds the opposite side"
            elif qty < 1:
                row["status"] = "skipped: size < 1 share or budget used up"
            elif sig.side < 0 and not _shortable(api, s):
                row["status"] = "skipped: not easy to borrow"
            elif api.order_by_client_id(cid):
                row["status"] = "already submitted"
            elif dry_run:
                row["status"] = "dry-run"
            else:
                try:
                    o = api.submit(symbol=s, qty=str(qty), side="buy" if sig.side > 0 else "sell", type="market",
                                   time_in_force="gtc", order_class="bracket", client_order_id=cid,
                                   take_profit={"limit_price": f"{sig.target:.2f}"},
                                   stop_loss={"stop_price": f"{sig.stop:.2f}"})
                    row["status"], row["order_id"] = "submitted", o["id"]
                    used += qty * sig.ref
                    ours.setdefault(s, set()).add(sig.side)
                except AlpacaError as e:
                    row["status"] = f"rejected: {e}"
            log(f"[{vid}] {s} {row['side']} {sig.pattern} ref {sig.ref} stop {sig.stop} target {sig.target} "
                f"qty {qty} -> {row['status']}")
            rows.append(row)
    if not rows:
        log(f"no signals on the {datetime.fromtimestamp(last_close, ET):%H:%M} candle")
    if not dry_run:
        _append_signals(rows)


def _price(o: dict) -> float:
    """Fill price of an entry, or for a pending one the price of its stop leg (close enough for the cap)."""
    if o.get("filled_avg_price"):
        return float(o["filled_avg_price"])
    return next((float(l["stop_price"]) for l in o.get("legs") or [] if l.get("stop_price")), 0.0)


def _shortable(api: Alpaca, s: str) -> bool:
    try:
        a = api.asset(s)
        return bool(a.get("shortable") and a.get("easy_to_borrow"))
    except AlpacaError:
        return False


def _append_signals(rows: list[dict]) -> None:
    if not rows:
        return
    os.makedirs(RESULTS_DIR, exist_ok=True)
    new = not os.path.exists(SIGNALS_CSV)
    with open(SIGNALS_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SIGNAL_FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)


def _read_signals() -> dict:
    if not os.path.exists(SIGNALS_CSV):
        return {}
    with open(SIGNALS_CSV, newline="") as f:
        return {(r["variant"], r["time"], r["symbol"]): r for r in csv.DictReader(f)}


def _realised_pnl(vid: str) -> float:
    if not os.path.exists(LIVE_JSON):
        return 0.0
    with open(LIVE_JSON) as f:
        v = (json.load(f).get("variants") or {}).get(vid) or {}
    return sum(t["pnl"] for t in (v.get("report") or {}).get("trades", []))


def _et(iso: str | None) -> str:
    d = _parse_ts(iso)
    return d.strftime("%Y-%m-%d %H:%M") if d else ""


def cmd_sync(simulate: bool = True) -> dict:
    api, st, variants = Alpaca(), _state(), load_variants()
    start = st.get("live_start")
    if not start:
        log("no live trading yet")
        return {}
    orders = our_orders(api, datetime.fromisoformat(start).replace(tzinfo=ET) - timedelta(days=1))
    exits = {o["client_order_id"][:-2]: o for o in orders if o["client_order_id"].endswith("-x")}
    signals = _read_signals()
    per = {vid: {"trades": [], "open": []} for vid in variants}
    for o in orders:
        vid, stamp, sym, is_exit = parse_cid(o["client_order_id"])
        if is_exit or vid not in per or float(o.get("filled_qty") or 0) <= 0:
            continue
        side = 1 if o["side"] == "buy" else -1
        qty, entry = float(o["filled_qty"]), float(o["filled_avg_price"])
        legs = o.get("legs") or []
        stop_leg = next((l for l in legs if l.get("stop_price")), None)
        tgt_leg = next((l for l in legs if l.get("limit_price") and not l.get("stop_price")), None)
        stop = float(stop_leg["stop_price"]) if stop_leg else entry
        exit_o, reason = None, None
        for l in legs:
            if l["status"] == "filled":
                exit_o, reason = l, "stop" if l.get("stop_price") else "target"
        x = exits.get(o["client_order_id"])
        if exit_o is None and x is not None and x["status"] == "filled":
            exit_o, reason = x, "time"
        sig_time = datetime.strptime(stamp, "%Y%m%d%H%M").strftime("%Y-%m-%d %H:%M")
        sig = signals.get((vid, sig_time, sym), {})
        base = {"variant": vid, "symbol": sym, "day": _et(o["filled_at"])[:10], "side": "long" if side > 0 else "short",
                "pattern": sig.get("pattern", ""), "signal_time": sig_time, "entry_time": _et(o["filled_at"]),
                "entry": entry, "stop": stop, "target": float(tgt_leg["limit_price"]) if tgt_leg else None,
                "qty": int(qty), "planned_ref": float(sig["ref"]) if sig.get("ref") else None}
        if exit_o is None:
            per[vid]["open"].append(base)
            continue
        px = float(exit_o["filled_avg_price"])
        ref = base["planned_ref"] or entry
        risk = abs(ref - stop) or 1e-9
        per[vid]["trades"].append({**base, "exit_time": _et(exit_o["filled_at"]), "exit": px, "reason": reason,
                                   "pnl": round((px - entry) * side * qty, 2), "r": round((px - entry) * side / risk, 4)})
    today = _now().date()
    bars = None
    if simulate:
        try:
            raw = fetch_alpaca(UNIVERSE, datetime.combine(date.fromisoformat(start) - timedelta(days=60),
                                                          datetime.min.time(), ET))
            bars = {s: to_hourly(b) for s, b in raw.items()}
        except Exception as e:  # data host may be blocked
            log("simulation skipped:", e)
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "live_start": start,
           "budget": st["budget"], "variants": {}, "signals": list(signals.values())}
    for vid, v in variants.items():
        vb = st["variants"].get(vid, {}).get("budget", st["budget"] * v["budget_share"])
        trades = sorted(per[vid]["trades"], key=lambda t: t["exit_time"])
        curve = _curve(trades, vb, date.fromisoformat(start), today)
        sim = None
        if bars is not None:
            bt = Backtest(bars, v["params"], vb, trade_from=date.fromisoformat(start)).run()
            sim = full_report([t.to_dict() for t in bt.trades], bt.equity_curve, vb)
        out["variants"][vid] = {"label": v.get("label", vid), "note": v.get("note", ""), "budget": vb,
                                "params": v["params"].to_dict(), "open": per[vid]["open"],
                                "report": full_report(trades, curve, vb), "simulated": sim}
        log(f"[{vid}] synced {len(trades)} closed / {len(per[vid]['open'])} open trades, "
            f"live PnL {sum(t['pnl'] for t in trades):+,.2f}")
    with open(LIVE_JSON, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    return out


def _curve(trades: list[dict], budget: float, start: date, end: date) -> list[tuple[str, float]]:
    by_day = {}
    for t in trades:
        by_day[t["exit_time"][:10]] = by_day.get(t["exit_time"][:10], 0) + t["pnl"]
    curve, cum, d = [], budget, start
    while d <= end:
        if d.weekday() < 5:
            cum += by_day.get(str(d), 0)
            curve.append((str(d), round(cum, 2)))
        d += timedelta(days=1)
    return curve
