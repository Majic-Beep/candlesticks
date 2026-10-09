"""Minimal Alpaca trading-API client. Refuses anything that is not the paper endpoint."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .config import load_dotenv


class AlpacaError(RuntimeError):
    def __init__(self, code: int, body: str):
        super().__init__(f"Alpaca HTTP {code}: {body[:300]}")
        self.code = code


class Alpaca:
    def __init__(self):
        load_dotenv()
        self.base = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
        if "paper-api." not in self.base:
            raise SystemExit(f"refusing non-paper Alpaca endpoint {self.base}")
        key, secret = (os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY", "")), (os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY", ""))
        # Without keys we rely on a proxy that injects them (Claude cloud environment).
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret} if key and secret else {}

    def _req(self, method: str, path: str, body: dict | None = None, query: dict | None = None):
        url = self.base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={**self.headers, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise AlpacaError(e.code, e.read().decode(errors="replace")) from None

    # account / calendar
    def account(self):
        return self._req("GET", "/v2/account")

    def clock(self):
        return self._req("GET", "/v2/clock")

    def calendar(self, start: str, end: str):
        return self._req("GET", "/v2/calendar", query={"start": start, "end": end})

    def asset(self, symbol: str):
        return self._req("GET", f"/v2/assets/{symbol}")

    # orders / positions
    def submit(self, **order):
        return self._req("POST", "/v2/orders", body=order)

    def orders(self, status: str = "all", after: str | None = None, limit: int = 500):
        q = {"status": status, "limit": limit, "nested": "true", "direction": "asc"}
        if after:
            q["after"] = after
        return self._req("GET", "/v2/orders", query=q)

    def order_by_client_id(self, cid: str):
        try:
            return self._req("GET", "/v2/orders:by_client_order_id", query={"client_order_id": cid})
        except AlpacaError as e:
            if e.code == 404:
                return None
            raise

    def cancel(self, order_id: str):
        try:
            self._req("DELETE", f"/v2/orders/{order_id}")
        except AlpacaError as e:
            if e.code not in (404, 422):
                raise

    def positions(self):
        return self._req("GET", "/v2/positions")
