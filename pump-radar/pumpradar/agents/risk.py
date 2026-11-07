from __future__ import annotations
from .base import Agent
from ..utils import safe_div
class RiskAgent(Agent):
    name="risk"
    def __init__(self, settings=None): self.s=settings
    def features(self, st):
        now=st.last_ts or st.created_at; age=st.age(now)
        def vol(sec, buy):
            return sum(float(t.get("sol") or 0) for t in st.window(sec,now) if bool(t.get("is_buy"))==buy)
        b30,s30,b10,s10=vol(30,True),vol(30,False),vol(10,True),vol(10,False)
        tot_buy=sum(float(t.get("sol") or 0) for t in st.trades if t.get("is_buy")) or 1e-9
        tot_sell=sum(float(t.get("sol") or 0) for t in st.trades if not t.get("is_buy"))
        top=sorted((d.get("sol",0.0) for d in st.buyers.values()), reverse=True); top1=top[0]/tot_buy if top else 0.0
        engineered=0.0
        if age<65 and st.vsol>90: engineered=1.0
        if top1>0.80 and len(st.buyers)<=4: engineered=1.0
        if len(st.buyers)<=2 and st.vsol>60: engineered=1.0
        name_txt=f"{st.name} {st.symbol}".lower().strip()
        junk=1.0 if any(k in name_txt for k in ("test","asdf","junk","rug","scam","xxx")) or len(name_txt)<=2 else 0.0
        img_reuse=(st.meta or {}).get("image_reuse",0) or 0
        new_buyers=len({t.get("trader") for t in st.window(30,now) if t.get("is_buy")})
        distribution=1.0 if (s30>2.2*b30 and b30>0.05 and new_buyers<=2) else 0.0
        return {"risk_engineered":engineered,"risk_junk_name":junk,"risk_clone_image":1.0 if img_reuse>1 else 0.0,
                "risk_no_social":0.0 if ((st.meta or {}).get("twitter") or (st.meta or {}).get("telegram")) else 1.0,
                "risk_desc_len":min(len((st.meta or {}).get("description") or ""),400),
                "risk_top1_share":top1,"risk_sell_pressure_30s":safe_div(s30,b30+0.05),
                "risk_sell_pressure_10s":safe_div(s10,b10+0.05),"risk_distribution":distribution,
                "risk_cashout_ratio":safe_div(tot_sell,tot_buy),"risk_mayhem":1.0 if st.mayhem else 0.0}
