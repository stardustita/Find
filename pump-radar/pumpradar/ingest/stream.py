from __future__ import annotations
import asyncio, json, logging, time
from ..utils import TOTAL_SUPPLY
log = logging.getLogger("ingest.pumpportal")

def parse_trade(ev: dict, sol_price: float = 0.0) -> dict | None:
    mint = ev.get("mint")
    if not mint: return None
    vsol = ev.get("vSolInBondingCurve"); vtok = ev.get("vTokensInBondingCurve")
    if vsol is not None: vsol = float(vsol)
    if vtok is not None: vtok = float(vtok)
    mcap = ev.get("marketCapSol")
    if mcap is None and vsol and vtok:
        mcap = vsol * TOTAL_SUPPLY / vtok
    return {
        "mint": mint, "ts": float(ev.get("_ts") or time.time()), "tx": ev.get("signature"),
        "trader": ev.get("traderPublicKey"), "is_buy": ev.get("txType") == "buy",
        "sol": float(ev.get("solAmount") or 0.0), "tokens": float(ev.get("tokenAmount") or 0.0),
        "vsol": vsol, "vtok": vtok, "rsol": ev.get("realSolReserves"), "rtok": ev.get("realTokenReserves"),
        "vquote": ev.get("vQuoteReserves", vsol), "rquote": ev.get("rQuoteReserves", ev.get("realSolReserves")),
        "mcap_sol": float(mcap) if mcap is not None else None, "slot": ev.get("slot"),
        "source": ev.get("source", "pumpportal"), "lane": ev.get("lane", "sol" if vsol else "unknown"),
        "quote_mint": ev.get("quoteMint", "SOL"), "curve_std": bool(ev.get("curve_std", bool(vsol))),
    }

class PumpPortalStream:
    """Fallback/ridondanza: create+migration gratuiti. I trade richiedono key finanziata:
    il sistema li usa solo se l'utente configura esplicitamente una chiave."""
    def __init__(self, url, api_key, bus):
        self.url=url+(f"?api-key={api_key}" if api_key else ""); self.bus=bus; self.ws=None
        self.connected=False; self.reconnects=0; self.events=0
        self._subscribed=set(); self._pending_add=set(); self._pending_del=set()
    def subscribe_trades(self, mints):
        self._pending_add.update(m for m in mints if m not in self._subscribed)
    def unsubscribe_trades(self, mints):
        for m in mints:
            if m in self._subscribed: self._pending_del.add(m)
    def n_subscribed(self): return len(self._subscribed)
    async def run(self):
        import websockets
        backoff=1.0
        while True:
            try:
                async with websockets.connect(self.url, open_timeout=15, ping_interval=20, ping_timeout=20, max_size=8 << 20) as ws:
                    self.ws=ws; self.connected=True; backoff=1.0
                    await ws.send(json.dumps({"method":"subscribeNewToken"}))
                    await ws.send(json.dumps({"method":"subscribeMigration"}))
                    log.info("PumpPortal connesso (create/migration)")
                    resub=list(self._subscribed); self._subscribed.clear(); self._pending_add.update(resub)
                    while True: self._handle(await asyncio.wait_for(ws.recv(), timeout=45))
            except asyncio.CancelledError: raise
            except Exception as e:
                self.connected=False; self.reconnects+=1
                log.warning("PumpPortal down (%s) -> reconnect in %.0fs", type(e).__name__, backoff)
                await asyncio.sleep(backoff); backoff=min(30.0, backoff*1.8)
    def _handle(self, raw):
        try: ev=json.loads(raw)
        except Exception: return
        if not isinstance(ev, dict) or "txType" not in ev: return
        ev["_ts"]=time.time(); self.events+=1; tt=ev.get("txType")
        if tt=="create": self.bus.publish("create", ev)
        elif tt in ("buy","sell"): self.bus.publish("trade", ev)
        elif tt in ("migrate","complete"): self.bus.publish("migrate", ev)
    async def pump_subscriptions(self):
        while True:
            await asyncio.sleep(1.0)
            if not self.connected or self.ws is None: continue
            try:
                if self._pending_add:
                    batch=list(self._pending_add)[:50]
                    for m in batch: self._pending_add.discard(m)
                    await self.ws.send(json.dumps({"method":"subscribeTokenTrade","keys":batch})); self._subscribed.update(batch)
                if self._pending_del:
                    batch=list(self._pending_del)[:50]
                    for m in batch: self._pending_del.discard(m)
                    await self.ws.send(json.dumps({"method":"unsubscribeTokenTrade","keys":batch})); self._subscribed.difference_update(batch)
            except Exception as e: log.debug("subscription manager: %s", e)
