from __future__ import annotations
import time
from collections import deque
from .base import Agent
from ..utils import safe_div
class ContextAgent(Agent):
    name="context"
    def __init__(self, enricher=None): self.enr=enricher; self.launches=deque(maxlen=10000); self.sol_hist=deque(maxlen=240)
    def observe_create(self, ts=None): self.launches.append(ts or time.time())
    def observe(self, st, event):
        if event and event.get("kind")=="create": self.launches.append(event.get("ts") or time.time())
    def tick(self):
        p=getattr(self.enr,"sol_price",0.0) if self.enr else 0.0
        if p: self.sol_hist.append((time.time(),p))
    def features(self, st):
        now=st.last_ts or time.time(); n60=sum(1 for t in self.launches if now-t<=60); n300=sum(1 for t in self.launches if now-t<=300)
        sol_ret=0.0; price=getattr(self.enr,"sol_price",150.0) if self.enr else 150.0
        if len(self.sol_hist)>=2 and self.sol_hist[0][1]: sol_ret=safe_div(price-self.sol_hist[0][1], self.sol_hist[0][1])
        tm=time.localtime(now)
        return {"ctx_launches_60s":n60,"ctx_launches_300s":n300,"ctx_congestion":min(1.0,n60/60.0),
                "ctx_sol_price":price or 150.0,"ctx_sol_ret":sol_ret,"ctx_hour":tm.tm_hour,"ctx_dow":tm.tm_wday}
