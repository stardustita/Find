from __future__ import annotations
import time
from collections import deque
from dataclasses import dataclass, field

@dataclass
class TokenState:
    mint: str
    name: str = ""
    symbol: str = ""
    uri: str = ""
    creator: str = ""
    created_at: float = 0.0
    lane: str = "unknown"
    quote_mint: str = "SOL"
    curve_std: bool = True
    mayhem: bool = False
    pool: str = "pump"

    trades: deque = field(default_factory=lambda: deque(maxlen=6000))
    buyers: dict = field(default_factory=dict)
    sellers: dict = field(default_factory=dict)
    slots_buyers: dict = field(default_factory=dict)

    vsol: float = 30.0
    vtok: float = 1_073_000_000.0
    rsol: float = 0.0
    rtok: float = 793_100_000.0
    vquote: float = 30.0
    rquote: float = 0.0
    mcap_sol: float | None = 0.0
    last_ts: float = 0.0

    meta: dict = field(default_factory=dict)
    narrative: dict = field(default_factory=dict)
    state: str = "new"
    persist: bool = False
    bonded_at: float = 0.0
    peak_mcap: float = 0.0
    min_mcap: float = 0.0
    n_trades: int = 0
    n_buys: int = 0
    n_sells: int = 0
    buy_sol_total: float = 0.0
    sell_sol_total: float = 0.0
    signals: list = field(default_factory=list)
    last_score: float = 0.0
    last_tier: str = ""
    _last_snap: float = 0.0

    def age(self, now: float | None = None) -> float:
        now = now or time.time()
        return max(0.0, now - (self.created_at or now))

    def observe(self, tr: dict) -> None:
        self.trades.append(tr)
        self.n_trades += 1
        self.last_ts = float(tr.get("ts") or self.last_ts or time.time())
        for key in ("vsol", "vtok", "rsol", "rtok", "vquote", "rquote"):
            if tr.get(key) is not None:
                setattr(self, key, float(tr[key]))
        if tr.get("mcap_sol") is not None:
            self.mcap_sol = float(tr["mcap_sol"])
            if self.mcap_sol:
                self.peak_mcap = max(self.peak_mcap, self.mcap_sol)
                self.min_mcap = min(self.min_mcap or self.mcap_sol, self.mcap_sol)
        if tr.get("lane"):
            self.lane = str(tr["lane"])
        if tr.get("quote_mint"):
            self.quote_mint = str(tr["quote_mint"])
        if tr.get("curve_std") is not None:
            self.curve_std = bool(tr["curve_std"])
        trader = tr.get("trader")
        if not trader:
            return
        book = self.buyers if tr.get("is_buy") else self.sellers
        rec = book.setdefault(trader, {"sol": 0.0, "tokens": 0.0, "first_ts": self.last_ts, "last_ts": self.last_ts, "n": 0})
        rec["sol"] += float(tr.get("sol") or 0.0)
        rec["tokens"] += float(tr.get("tokens") or 0.0)
        rec["n"] += 1
        rec["last_ts"] = self.last_ts
        if tr.get("is_buy"):
            self.n_buys += 1
            self.buy_sol_total += float(tr.get("sol") or 0.0)
            if tr.get("slot") is not None:
                self.slots_buyers.setdefault(tr["slot"], set()).add(trader)
        else:
            self.n_sells += 1
            self.sell_sol_total += float(tr.get("sol") or 0.0)

    def window(self, seconds: float, now: float | None = None) -> list[dict]:
        now = now or self.last_ts or time.time()
        cutoff = now - seconds
        out = []
        for tr in reversed(self.trades):
            if float(tr.get("ts") or 0) < cutoff:
                break
            out.append(tr)
        out.reverse()
        return out
