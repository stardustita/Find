from __future__ import annotations
import asyncio, hashlib, json, logging, time, urllib.request, urllib.parse
log = logging.getLogger("ingest.enrich")
SOL_MINT="So11111111111111111111111111111111111111112"
UA={"User-Agent":"pumpradar/1.0 (+local research)"}

def _get_json_sync(url, params=None, timeout=12):
    if params: url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req=urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def _get_bytes_sync(url, timeout=12):
    req=urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(65536)

def _post_json_sync(url, payload, timeout=12):
    data=json.dumps(payload).encode(); req=urllib.request.Request(url, data=data, headers={**UA,"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8","replace"))

def _unwrap_prices(data):
    """Jupiter Price API restituisce {"data": {mint: {...}}}: scarta l'involucro."""
    if isinstance(data, dict):
        inner=data.get("data")
        if isinstance(inner, dict): return inner
        return data
    return {}

class Enricher:
    def __init__(self, settings, store=None):
        self.s=settings; self.store=store; self.sol_price=0.0; self.sol_price_ts=0.0
        self._meta_cache={}; self.image_hashes={}
    async def _get_json(self, url, params=None):
        return await asyncio.to_thread(_get_json_sync, url, params)
    async def refresh_sol_price(self):
        try:
            data=_unwrap_prices(await self._get_json(self.s.jup_price_url, {"ids":SOL_MINT}))
            for mint,v in data.items():
                if isinstance(v, dict):
                    p=v.get("usdPrice") or v.get("price")
                    if p: self.sol_price=float(p); self.sol_price_ts=time.time(); break
        except Exception as e: log.debug("SOL price: %s", e)
        return self.sol_price or 150.0
    async def sol_price_loop(self, interval=60.0):
        while True:
            await self.refresh_sol_price(); await asyncio.sleep(interval)
    def _resolve_uri(self, uri):
        if uri.startswith("ipfs://"):
            return self.s.ipfs_gateways[0] + uri.replace("ipfs://", "")
        return uri
    async def fetch_metadata(self, uri):
        if not uri: return {}
        if uri in self._meta_cache: return self._meta_cache[uri]
        out={}
        try:
            j=await self._get_json(self._resolve_uri(uri))
            if isinstance(j, dict):
                out={"name":j.get("name"),"symbol":j.get("symbol"),"description":(j.get("description") or "")[:600],
                     "twitter":j.get("twitter") or j.get("x") or "","telegram":j.get("telegram") or "",
                     "website":j.get("website") or "","image":j.get("image") or ""}
                img=out.get("image")
                if img:
                    try:
                        content=await asyncio.to_thread(_get_bytes_sync, self._resolve_uri(img))
                        h=hashlib.sha1(content).hexdigest()[:16]; out["image_hash"]=h
                        self.image_hashes[h]=self.image_hashes.get(h,0)+1
                    except Exception: pass
        except Exception as e: log.debug("metadata %s: %s", str(uri)[:40], e)
        if out: self._meta_cache[uri]=out
        return out
    def image_reuse(self, h):
        return self.image_hashes.get(h,0) if h else 0
    async def prices_usd(self, mints):
        mints=[m for m in mints if m]
        if not mints: return {}
        try:
            data=_unwrap_prices(await self._get_json(self.s.jup_price_url, {"ids":",".join(mints[:50])}))
            out={}
            if isinstance(data, dict):
                for mint,v in data.items():
                    if isinstance(v, dict) and (v.get("usdPrice") or v.get("price")):
                        out[mint]=float(v.get("usdPrice") or v.get("price"))
            return out
        except Exception as e: log.debug("prices_usd: %s", e); return {}
    async def rpc_call(self, method, params):
        urls=[self.s.rpc_url]+([self.s.rpc_url_2] if getattr(self.s,"rpc_url_2",None) else [])
        for url in urls:
            try:
                j=await asyncio.to_thread(_post_json_sync, url, {"jsonrpc":"2.0","id":1,"method":method,"params":params})
                if "result" in j: return j["result"]
            except Exception: continue
        return None
    async def dexscreener_pair(self, mint):
        try:
            j=await self._get_json(f"{self.s.dexscreener_url}/{mint}")
            pairs=(j or {}).get("pairs") or []
            if not pairs: return {}
            pairs.sort(key=lambda p:(p.get("liquidity") or {}).get("usd") or 0, reverse=True); p=pairs[0]
            return {"pair":p.get("pairAddress"),"dex":p.get("dexId"),"price_usd":float(p.get("priceUsd") or 0),
                    "mcap":float(p.get("marketCap") or p.get("fdv") or 0),"liq":float((p.get("liquidity") or {}).get("usd") or 0)}
        except Exception: return {}
