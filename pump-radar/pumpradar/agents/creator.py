from __future__ import annotations
import time
from .base import Agent
from ..utils import safe_div
class CreatorAgent(Agent):
    name="creator"
    def __init__(self, store=None): self.store=store; self._cache={}
    def profile(self, creator):
        if not creator or self.store is None: return {"n_launches":0,"bonded_rate":0.0,"best_mcap":0.0,"med_mcap":0.0,"known":0}
        now=time.time(); cached=self._cache.get(creator)
        if cached and now-cached.get("_t",0)<30: return cached
        rows=self.store.q("""SELECT t.state, COALESCE(o.peak_mcap,0) peak FROM tokens t LEFT JOIN outcomes o ON o.mint=t.mint WHERE t.creator=? ORDER BY t.created_at DESC LIMIT 100""", (creator,))
        peaks=sorted(float(r["peak"] or 0) for r in rows); n=len(rows)
        prof={"n_launches":n,"bonded_rate":safe_div(sum(1 for r in rows if r["state"]=="bonded"),n),
              "best_mcap":peaks[-1] if peaks else 0.0,"med_mcap":peaks[len(peaks)//2] if peaks else 0.0,
              "known":1 if n>=2 else 0,"_t":now}
        self._cache[creator]=prof; return prof
    def features(self, st):
        prof=self.profile(st.creator)
        dev_buy=st.buyers.get(st.creator,{}); dev_sell=st.sellers.get(st.creator,{})
        net=max(0.0,float(dev_buy.get("tokens",0.0))-float(dev_sell.get("tokens",0.0)))
        return {"creator_launches":prof["n_launches"],"creator_bonded_rate":prof["bonded_rate"],
                "creator_best_mcap":prof["best_mcap"],"creator_med_mcap":prof["med_mcap"],"creator_known":prof["known"],
                "dev_hold_pct":min(1.0,safe_div(net,1_000_000_000.0)),
                "dev_sold_flag":1.0 if st.creator in st.sellers else 0.0,
                "dev_buy_sol":float(dev_buy.get("sol",0.0))}
