from __future__ import annotations
from .base import Agent
from ..utils import curve_progress, gini, hhi, progress_from_rtok, safe_div, spot_price_sol

class CurveAgent(Agent):
    name="curve"
    def __init__(self, grad_vsol: float = 115.0): self.grad_vsol=grad_vsol
    def features(self, st):
        now=st.last_ts or st.created_at
        f={}
        def agg(ws):
            buy=sum(float(t.get("sol") or 0) for t in ws if t.get("is_buy")); sell=sum(float(t.get("sol") or 0) for t in ws if not t.get("is_buy"))
            nb=sum(1 for t in ws if t.get("is_buy")); ns=sum(1 for t in ws if not t.get("is_buy"))
            ub={t.get("trader") for t in ws if t.get("is_buy") and t.get("trader")}
            return buy,sell,nb,ns,ub
        w10,w30,w60,wall=st.window(10,now),st.window(30,now),st.window(60,now),list(st.trades)
        b10=agg(w10)[0]; b30,s30,nb30,ns30,ub30=agg(w30); b60=agg(w60)[0]
        # compratori attivi nella finestra precedente (30-60s fa): base per "nuovi" e crescita
        prev_buyers={t.get("trader") for t in wall if t.get("is_buy") and t.get("trader") and now-60<=float(t.get("ts") or 0)<now-30}
        age=st.age(now)
        lane=getattr(st,"lane","unknown")
        std=bool(getattr(st,"curve_std", lane=="sol"))
        if lane=="sol" and getattr(st,"rtok",None):
            progress=progress_from_rtok(st.rtok)
        elif lane=="sol":
            progress=curve_progress(st.vsol)
        else:
            progress=0.0
        total_buy=sum(float(t.get("sol") or 0) for t in wall if t.get("is_buy")); total_sell=sum(float(t.get("sol") or 0) for t in wall if not t.get("is_buy"))
        f.update({
            "age_s":age,"curve_progress":progress,"vsol":st.vsol,"vtok":st.vtok,"rtok":st.rtok,
            "mcap_sol":float(st.mcap_sol or 0.0),"has_price":1.0 if st.mcap_sol else 0.0,
            "lane_sol":1.0 if lane=="sol" else 0.0,"lane_alt":1.0 if lane=="alt" else 0.0,
            "lane_cross":1.0 if lane=="cross" else 0.0,"lane_shallow":1.0 if lane=="shallow" else 0.0,
            "curve_std":1.0 if std else 0.0,
            "sol_per_s_10s":b10/10.0,"sol_per_s_30s":b30/30.0,"sol_per_s_60s":b60/60.0,
            "sol_per_s_life":safe_div(total_buy,max(age,1.0)),
            "sol_accel":safe_div(b30/30.0, safe_div(b60-b30,30.0)+1e-6),
            "buy_sol_10s":b10,"buy_sol_30s":b30,"buy_sol_60s":b60,"sell_sol_30s":s30,
            "buy_sell_ratio_30s":safe_div(b30,s30+0.05),"buy_sell_ratio_life":safe_div(total_buy,total_sell+0.05),
            "n_buys_30s":nb30,"n_sells_30s":ns30,"trade_rate_30s":(nb30+ns30)/30.0,
            "unique_buyers_30s":len(ub30),"unique_buyers_life":len(st.buyers),
            "new_buyers_30s":len(ub30-prev_buyers),"buyer_growth":safe_div(len(ub30),max(1,len(prev_buyers))),
            "unique_buyer_per_s":safe_div(len(st.buyers),max(age,1.0)),
            "price_sol":spot_price_sol(st.vsol, st.vtok) if lane=="sol" else safe_div(getattr(st,"vquote",0.0), st.vtok),
        })
        buys=[float(t.get("sol") or 0) for t in wall if t.get("is_buy") and t.get("sol")]
        if buys:
            tot=sum(buys); top=sorted(buys, reverse=True)
            f.update({"avg_buy_sol":tot/len(buys),"max_buy_sol":top[0],"top1_buy_share":top[0]/tot,
                      "top3_buy_share":sum(top[:3])/tot,"buy_hhi":hhi(buys),"buy_gini":gini(buys),
                      "retail_share":sum(1 for b in buys if b<0.15)/len(buys)})
        else:
            f.update({"avg_buy_sol":0.0,"max_buy_sol":0.0,"top1_buy_share":0.0,"top3_buy_share":0.0,"buy_hhi":0.0,"buy_gini":0.0,"retail_share":0.0})
        rep=sum(1 for d in st.buyers.values() if d.get("n",0)>=2)
        f["repeat_buyers"]=rep; f["repeat_buyer_share"]=safe_div(rep,max(1,len(st.buyers)))
        f["early_exit_share"]=safe_div(len([w for w in st.sellers if w in st.buyers]), max(1,len(st.buyers)))
        f["deviation_from_peak"]=safe_div((st.peak_mcap or 0)-(st.mcap_sol or 0), st.peak_mcap or 1)
        return f
