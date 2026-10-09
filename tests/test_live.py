"""Two variants on one account: hourly run (entries, time exits) and sync against a fake Alpaca."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from candle_patterns import live
from candle_patterns.config import ET, Params
from tests.test_patterns import day, flat_history, next_weekday

PIN = (99.6, 99.95, 98.9, 99.9)  # pin bar at the 99.0 swing low of flat_history()
QUIET = (100.0, 100.1, 99.9, 100.0)


class FakeAlpaca:
    def __init__(self, positions=(), foreign_orders=()):
        self.orders_ = list(foreign_orders)
        self.positions_ = list(positions)
        self.n = 0

    def calendar(self, a, b):
        return [{"date": a, "open": "09:30", "close": "16:00"}]

    def positions(self):
        return self.positions_

    def asset(self, s):
        return {"shortable": True, "easy_to_borrow": True}

    def orders(self, status="all", after=None, limit=500):
        if status == "open":
            return [o for o in self.orders_ if o["status"] in live.OPEN_STATES]
        return self.orders_

    def order_by_client_id(self, cid):
        return next((o for o in self.orders_ if o.get("client_order_id") == cid), None)

    def submit(self, **o):
        self.n += 1
        legs = []
        if o.get("order_class") == "bracket":
            legs = [{"id": f"o{self.n}t", "status": "held", "limit_price": o["take_profit"]["limit_price"]},
                    {"id": f"o{self.n}s", "status": "held", "stop_price": o["stop_loss"]["stop_price"]}]
        o = {**o, "id": f"o{self.n}", "status": "accepted", "filled_qty": "0", "legs": legs,
             "submitted_at": "2026-10-13T14:00:00Z"}
        self.orders_.append(o)
        return o

    def cancel(self, oid):
        for o in self.orders_:
            for x in [o] + (o.get("legs") or []):
                if x["id"] == oid:
                    x["status"] = "canceled"

    def fill(self, o, price, at):
        o.update(status="filled", filled_qty=o["qty"], filled_avg_price=str(price), filled_at=at)


VARIANTS = {"variants": {
    "v1": {"label": "V1", "budget_share": 0.5, "params": Params(slippage_bps=0, stop_buffer_atr=0, trend_len=20).to_dict()},
    "v2": {"label": "V2", "budget_share": 0.5, "params": Params(slippage_bps=0, stop_buffer_atr=0, trend_len=20,
                                                                 max_hold_bars=3).to_dict()}}}


class Live(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        for k in ("SIGNALS_CSV", "LIVE_JSON", "STATE_JSON", "VARIANTS_JSON"):
            p = mock.patch.object(live, k, os.path.join(d, os.path.basename(getattr(live, k))))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(live, "RESULTS_DIR", d)
        p.start()
        self.addCleanup(p.stop)
        with open(live.VARIANTS_JSON, "w") as f:
            json.dump(VARIANTS, f)
        hist, d0 = flat_history()
        self.day = next_weekday(d0)
        self.bars = hist + day(self.day, [PIN] + [QUIET] * 6)
        self.api = FakeAlpaca()

    def at(self, h, m):
        return datetime(self.day.year, self.day.month, self.day.day, h, m, tzinfo=ET)

    def run_at(self, when, bars=None):
        bars = self.bars if bars is None else bars
        visible = [b for b in bars if b.t < when.timestamp()]
        with mock.patch.object(live, "Alpaca", return_value=self.api), \
             mock.patch.object(live, "_now", return_value=when), \
             mock.patch.object(live, "fetch_recent", return_value={"X": visible}):
            live.cmd_run(["X"])

    def test_signal_becomes_one_bracket_per_variant(self):
        self.run_at(self.at(10, 31))
        ours = [o for o in self.api.orders_ if o["client_order_id"].startswith("cp-")]
        self.assertEqual(sorted(o["client_order_id"] for o in ours),
                         [f"cp-v1-{self.day:%Y%m%d}0930-X", f"cp-v2-{self.day:%Y%m%d}0930-X"])
        o = ours[0]
        self.assertEqual((o["type"], o["time_in_force"], o["order_class"], o["side"]), ("market", "gtc", "bracket", "buy"))
        self.assertEqual((o["stop_loss"]["stop_price"], o["take_profit"]["limit_price"]), ("98.90", "101.90"))
        self.assertEqual(int(o["qty"]), 62)  # min(25,000 x 0.5 % / 1.0 risk, 25 % of 25,000 / 99.9)
        self.run_at(self.at(10, 35))  # a repeated run does not send it again
        self.assertEqual(len([o for o in self.api.orders_ if o["client_order_id"].startswith("cp-")]), 2)

    def test_late_run_sends_nothing(self):
        self.run_at(self.at(10, 50))
        self.assertEqual(self.api.orders_, [])

    def test_foreign_symbol_is_skipped(self):
        self.api.positions_ = [{"symbol": "X", "qty": "10"}]
        self.run_at(self.at(10, 31))
        self.assertEqual(self.api.orders_, [])

    def test_time_exit_after_max_hold(self):
        self.run_at(self.at(10, 31))
        for o in list(self.api.orders_):
            self.api.fill(o, 99.9, f"{self.day}T14:31:00Z")  # 10:31 ET
        self.run_at(self.at(12, 31))  # v2 held 2 candles (10:30, 11:30): not yet
        self.assertFalse(any(o["client_order_id"].endswith("-x") for o in self.api.orders_))
        self.run_at(self.at(13, 31))  # 3 candles -> v2 closes, v1 (35) keeps its position
        x = [o for o in self.api.orders_ if o["client_order_id"].endswith("-x")]
        self.assertEqual([o["client_order_id"] for o in x], [f"cp-v2-{self.day:%Y%m%d}0930-X-x"])
        self.assertEqual((x[0]["side"], x[0]["qty"], x[0]["type"]), ("sell", "62", "market"))
        v2 = next(o for o in self.api.orders_ if o["client_order_id"] == f"cp-v2-{self.day:%Y%m%d}0930-X")
        self.assertTrue(all(l["status"] == "canceled" for l in v2["legs"]))

    def test_sync_reads_target_and_time_exits(self):
        self.run_at(self.at(10, 31))
        v1, v2 = sorted((o for o in self.api.orders_ if o["client_order_id"].startswith("cp-")), key=lambda o: o["client_order_id"])
        self.api.fill(v1, 99.9, f"{self.day}T14:31:00Z")
        self.api.fill(v2, 99.9, f"{self.day}T14:31:00Z")
        v1["legs"][0].update(status="filled", filled_avg_price="101.90", filled_at=f"{self.day}T17:00:00Z", filled_qty="62")
        self.api.orders_.append({"id": "x1", "client_order_id": v2["client_order_id"] + "-x", "symbol": "X", "side": "sell",
                                 "status": "filled", "qty": "62", "filled_qty": "62", "filled_avg_price": "100.40",
                                 "filled_at": f"{self.day}T17:31:00Z", "legs": []})
        with mock.patch.object(live, "Alpaca", return_value=self.api), mock.patch.object(live, "_now", return_value=self.at(16, 1)):
            out = live.cmd_sync(simulate=False)
        t1 = out["variants"]["v1"]["report"]["trades"]
        t2 = out["variants"]["v2"]["report"]["trades"]
        self.assertEqual((t1[0]["reason"], t1[0]["pnl"], t1[0]["r"], t1[0]["pattern"]), ("target", 124.0, 2.0, "pin_bar"))
        self.assertEqual((t2[0]["reason"], t2[0]["pnl"]), ("time", 31.0))


if __name__ == "__main__":
    unittest.main()
