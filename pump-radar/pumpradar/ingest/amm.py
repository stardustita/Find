from __future__ import annotations
import asyncio, base64, json, logging, time
from collections import Counter
from .pumpevent import AMM_PROGRAM, DISC_AMM_BUY, DISC_AMM_POOL, DISC_AMM_SELL, decode_amm_pool, decode_amm_trade
log = logging.getLogger("ingest.amm")
def _b64(s):
    s=s.strip(); s += "="*((4-len(s)%4)%4); return base64.b64decode(s)
class AmmFeed:
    def __init__(self, bus, urls):
        self.bus=bus; self.urls=[u for u in urls if u] or ["wss://api.mainnet-beta.solana.com"]
        self.n=Counter(); self.connected=False; self.reconnects=0; self.idx=0; self.t0=time.time()
    async def run(self):
        import websockets
        backoff=1.0
        while True:
            url=self.urls[self.idx % len(self.urls)]
            try:
                async with websockets.connect(url, open_timeout=15, ping_interval=15, ping_timeout=20, max_size=8 << 20) as ws:
                    await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"logsSubscribe","params":[{"mentions":[AMM_PROGRAM]},{"commitment":"confirmed"}]}))
                    self.connected=True; backoff=1.0; log.info("AMM feed connesso: %s", url)
                    while True:
                        self._handle(await asyncio.wait_for(ws.recv(), timeout=90))
            except asyncio.CancelledError: raise
            except Exception as e:
                self.connected=False; self.reconnects+=1; self.idx+=1
                log.warning("AMM feed down (%s) -> failover in %.0fs", type(e).__name__, backoff)
                await asyncio.sleep(backoff); backoff=min(30.0, backoff*1.7)
    def _handle(self, raw):
        self.n["notif"]+=1
        try: ev=json.loads(raw)
        except Exception: self.n["bad_json"]+=1; return
        params=ev.get("params") or {}
        if not params: return
        value=(params.get("result") or {}).get("value") or {}
        if value.get("err"): self.n["tx_failed"]+=1; return
        now=time.time(); slot=value.get("slot"); sig=value.get("signature")
        for line in value.get("logs") or ():
            if not line.startswith("Program data: "): continue
            try: d=_b64(line[14:])
            except Exception: self.n["bad_b64"]+=1; continue
            head=d[:8]
            if head==DISC_AMM_POOL:
                p=decode_amm_pool(d)
                if p is None: self.n["bad_pool"]+=1; continue
                self.n["pool"]+=1; self.bus.publish("pool_created", {"_ts":now, **p, "signature":sig})
            elif head in (DISC_AMM_BUY, DISC_AMM_SELL):
                t=decode_amm_trade(d)
                if t is None: self.n["bad_trade"]+=1; continue
                self.n["trade"]+=1; self.n["buy" if t["is_buy"] else "sell"]+=1
                self.bus.publish("amm_trade", {"_ts":now, **t, "slot":slot, "signature":sig})
    def health(self):
        el=max(1e-9,time.time()-self.t0)
        return {"connected":self.connected,"reconnects":self.reconnects,"trades_per_s":round(self.n["trade"]/el,1),"pools_created":self.n["pool"],"counts":dict(self.n)}
