from __future__ import annotations
import asyncio, base64, json, logging, time
from collections import Counter
from .pumpevent import (DISC_COMPLETE, DISC_CREATE, DISC_TRADE, PUMP_PROGRAM, TOTAL_SUPPLY, classify_lane, decode_complete, decode_create, decode_trade)

log = logging.getLogger("ingest.onchain")

def _b64(s: str) -> bytes:
    s = s.strip(); s += "=" * ((4 - len(s) % 4) % 4)
    return base64.b64decode(s)

class OnchainFeed:
    def __init__(self, bus, urls, sol_price_fn=None):
        self.bus = bus
        self.urls = [u for u in urls if u] or ["wss://api.mainnet-beta.solana.com"]
        self.sol_price_fn = sol_price_fn or (lambda: 0.0)
        self.n = Counter(); self.connected = False; self.reconnects = 0; self.idx = 0
        self.t0 = time.time(); self.quote_prices: dict[str, float] = {}

    async def run(self):
        import websockets
        backoff = 1.0
        while True:
            url = self.urls[self.idx % len(self.urls)]
            try:
                async with websockets.connect(url, open_timeout=15, ping_interval=15, ping_timeout=20, max_size=8 << 20) as ws:
                    await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"logsSubscribe","params":[{"mentions":[PUMP_PROGRAM]},{"commitment":"confirmed"}]}))
                    self.connected = True; backoff = 1.0
                    log.info("on-chain feed connesso: %s", url)
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=90)
                        self._handle(raw)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.connected = False; self.reconnects += 1; self.idx += 1
                log.warning("feed down (%s: %s) -> failover in %.0fs", type(e).__name__, str(e)[:100], backoff)
                await asyncio.sleep(backoff); backoff = min(30.0, backoff * 1.7)

    def _handle(self, raw: str):
        self.n["notif"] += 1
        try: ev = json.loads(raw)
        except Exception: self.n["bad_json"] += 1; return
        params = ev.get("params") or {}
        if not params: self.n["rpc_msg"] += 1; return
        value = (params.get("result") or {}).get("value") or {}
        if value.get("err"): self.n["tx_failed"] += 1; return
        now = time.time(); slot = value.get("slot"); sig = value.get("signature")
        for line in value.get("logs") or ():
            if not line.startswith("Program data: "): continue
            try: d = _b64(line[14:])
            except Exception: self.n["bad_b64"] += 1; continue
            head = d[:8]
            if head == DISC_TRADE: self._on_trade(d, now, slot, sig)
            elif head == DISC_CREATE: self._on_create(d, now, slot, sig)
            elif head == DISC_COMPLETE:
                k = decode_complete(d)
                if k:
                    self.n["complete"] += 1
                    self.bus.publish("migrate", {"_ts": now, "mint": k["mint"], "txType":"migrate", "quote_mint": k["quote_mint"], "curve": k["curve"], "source":"rpc"})

    def _on_trade(self, d, now, slot, sig):
        t = decode_trade(d)
        if t is None: self.n["bad_trade"] += 1; return
        lane = classify_lane(t["quote_mint"], t["vsol"], t["vtok"], t["rtok"], t["rsol"])
        if lane == "invalid": self.n["invalid"] += 1; return
        self.n[f"lane_{lane}"] += 1; self.n["trade"] += 1
        if lane == "sol":
            amount = t["sol_amount"]; vquote, rquote = t["vsol"], t["rsol"]
            mcap = t["vsol"] * TOTAL_SUPPLY / t["vtok"] if t["vtok"] else 0.0
        else:
            amount = t["quote_amount"] or t["sol_amount"]; vquote, rquote = t["vquote"], t["rquote"]
            mcap = (t["vsol"] * TOTAL_SUPPLY / t["vtok"]) if (lane in ("alt", "shallow") and t["vtok"]) else None
            if lane == "cross":
                px = self.quote_prices.get(t["quote_mint"])
                if px and t["vtok"]:
                    mcap = TOTAL_SUPPLY * (t["vquote"] / t["vtok"]) * px
        self.bus.publish("trade", {
            "_ts": now, "mint": t["mint"], "txType": "buy" if t["is_buy"] else "sell",
            "signature": sig, "traderPublicKey": t["trader"], "solAmount": amount,
            "tokenAmount": t["token_amount"], "vSolInBondingCurve": t["vsol"],
            "vTokensInBondingCurve": t["vtok"], "realSolReserves": t["rsol"],
            "realTokenReserves": t["rtok"], "vQuoteReserves": vquote, "rQuoteReserves": rquote,
            "marketCapSol": mcap, "quoteMint": t["quote_mint"], "lane": lane,
            "curve_std": lane == "sol", "ix": t["ix"], "feeSol": t["fee"], "slot": slot, "source": "rpc"})

    def _on_create(self, d, now, slot, sig):
        c = decode_create(d)
        if c is None: self.n["bad_create"] += 1; return
        lane = classify_lane(c["quote_mint"], c["vsol"], c["vtok"], c["rtok"], 0.0)
        if lane == "invalid": self.n["invalid_create"] += 1; return
        self.n["create"] += 1
        mcap = c["vsol"] * TOTAL_SUPPLY / c["vtok"] if c["vtok"] and lane == "sol" else None
        self.bus.publish("create", {
            "_ts": now, "mint": c["mint"], "txType":"create", "traderPublicKey": c["creator"] or c["user"],
            "solAmount": 0.0, "vSolInBondingCurve": c["vsol"] or 30.0,
            "vTokensInBondingCurve": c["vtok"] or 1_073_000_000.0,
            "realTokenReserves": c["rtok"], "marketCapSol": mcap,
            "name": c["name"], "symbol": c["symbol"], "uri": c["uri"],
            "is_mayhem_mode": c["mayhem"], "cashback": c["cashback"],
            "quoteMint": c["quote_mint"], "lane": lane, "curve_std": lane == "sol",
            "pool":"pump", "bondingCurveKey": c["curve"], "signature": sig, "source":"rpc"})

    def health(self):
        el = max(1e-9, time.time() - self.t0); n = self.n; tot = n["trade"] or 1
        return {"connected": self.connected, "reconnects": self.reconnects,
                "notif_per_s": round(n["notif"]/el, 1), "trades_per_s": round(n["trade"]/el, 2),
                "counts": dict(n), "lanes_pct": {"sol": round(n["lane_sol"]/tot*100,1),
                "alt": round(n["lane_alt"]/tot*100,1), "shallow": round(n["lane_shallow"]/tot*100,1),
                "cross": round(n["lane_cross"]/tot*100,1)}, "quote_prices_known": len(self.quote_prices)}
