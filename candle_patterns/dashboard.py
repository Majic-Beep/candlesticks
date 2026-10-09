"""Builds docs/index.html: one self-contained page (no external scripts) with the backtest and
live results embedded as JSON. Open it locally or serve docs/ with GitHub Pages."""
from __future__ import annotations

import json
import os

from .config import DOCS_DIR, LIVE_BUDGET, RESULTS_DIR

TEMPLATE = os.path.join(os.path.dirname(__file__), "dashboard_template.html")


def _load(name: str):
    p = os.path.join(RESULTS_DIR, name)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def build(out_path: str = os.path.join(DOCS_DIR, "index.html")) -> str:
    variants = (_load("live_variants.json") or {}).get("variants") or {}
    state = _load("live_state.json") or {}
    budget = state.get("budget") or float(os.environ.get("CP_BUDGET") or LIVE_BUDGET)
    cfg_variants = {vid: {"label": v.get("label", vid), "note": v.get("note", ""), "params": v["params"],
                          "budget": (state.get("variants") or {}).get(vid, {}).get("budget")
                          or round(budget * v.get("budget_share", 1.0), 2)}
                    for vid, v in sorted(variants.items())}
    data = {"backtest": _load("backtest.json"), "live": _load("live.json"), "vbt": _load("variants_backtest.json"),
            "live_config": {"budget": budget, "live_start": state.get("live_start"), "variants": cfg_variants}}
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html.replace("/*__DATA__*/null", payload))
    return out_path
