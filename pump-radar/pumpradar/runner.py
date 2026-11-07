from __future__ import annotations
import math, time
from collections import Counter, deque
from dataclasses import dataclass, field
from .ingest.pumpevent import SOL_QUOTE, amm_price
from .utils import clamp, hhi, safe_div

@dataclass
class GradState:
    pool: str
    base_mint: str
    quote_mint: str = SOL_QUOTE
    bdec: int = 6
    qdec: int = 9
    supply: float = 1_000_000_000.0
    creator: str = ""
    created_at: float = 0.0
    mayhem: bool = False
    trades: deque = field(default_factory=lambda: deque(maxlen=5000))
    buyers: dict = field(default_factory=dict)
    sellers: dict = field(default_factory=dict)
    prices: deque = field(default_factory=lambda: deque(maxlen=4000))
    price: float = 0.0
    liq_sol: float = 0.0
    init_liq_sol: float = 0.0
    init_mcap_sol: float = 0.0
    mcap_sol: float = 0.0
    peak_mcap: float = 0.0
    last_ts: float = 0.0
    n_buys: int = 0
    n_sells: int = 0
    buy_sol_total: float = 0.0
    sell_sol_total: float = 0.0
    creator_sold_sol: float = 0.0
    n_bad: int = 0
    state: str = "new"
    track: bool = False
    confirm_count: int = 0
    last_signal_id: int = 0
    opened_episode: bool = False
    last_score: float = 0.0
    last_tier: str = ""

    def age(self, now=None): return max(0.0,(now or time.time())-(self.created_at or (now or time.time())))
    def observe(self, t: dict):
        ts=float(t.get("ts") or t.get("_ts") or t.get("ts_chain") or time.time())
        user=t.get("user") or t.get("trader") or t.get("traderPublicKey") or ""
        is_buy=bool(t.get("is_buy"))
        pool_base=t.get("pool_base", t.get("pool_base_amount")); pool_quote=t.get("pool_quote", t.get("pool_quote_amount"))
        if pool_base is None or pool_quote is None: self.n_bad+=1; return
        price=amm_price(pool_quote, pool_base, self.bdec, self.qdec)
        liq=float(pool_quote)/(10**self.qdec); mcap=price*self.supply
        if not (price>0 and mcap>0 and liq>=0): self.n_bad+=1; return
        sol=float(t.get("quote_amount") or 0)/(10**self.qdec); tok=float(t.get("base_amount") or 0)/(10**self.bdec)
        rec={"ts":ts,"user":user,"is_buy":is_buy,"sol":sol,"tokens":tok,"price":price,"mcap":mcap,"liq":liq}
        self.trades.append(rec); self.prices.append((ts,price,mcap))
        self.price,self.liq_sol,self.mcap_sol,self.last_ts=price,liq,mcap,ts
        if not self.init_liq_sol: self.init_liq_sol=liq
        if not self.init_mcap_sol: self.init_mcap_sol=mcap
        self.peak_mcap=max(self.peak_mcap,mcap)
        if is_buy:
            self.n_buys+=1; self.buy_sol_total+=sol; d=self.buyers.setdefault(user,{"sol":0.0,"n":0,"first_ts":ts}); d["sol"]+=sol; d["n"]+=1
        else:
            self.n_sells+=1; self.sell_sol_total+=sol; d=self.sellers.setdefault(user,{"sol":0.0,"n":0,"first_ts":ts}); d["sol"]+=sol; d["n"]+=1
            if user and user==self.creator: self.creator_sold_sol+=sol
    def window(self, seconds, now=None):
        now=now or self.last_ts or time.time(); cut=now-seconds; out=[]
        for r in reversed(self.trades):
            if r["ts"]<cut: break
            out.append(r)
        out.reverse(); return out
    def price_at(self, seconds_ago, now=None):
        now=now or time.time(); cut=now-seconds_ago
        for ts,px,_ in reversed(self.prices):
            if ts<=cut: return px
        return self.prices[0][1] if self.prices else 0.0

class PostGradAgent:
    name="postgrad"
    def features(self, st: GradState):
        now=st.last_ts or time.time(); f={}
        w1,w5,w15=st.window(60,now),st.window(300,now),st.window(900,now)
        def agg(ws):
            b=sum(r["sol"] for r in ws if r["is_buy"]); s=sum(r["sol"] for r in ws if not r["is_buy"])
            return b,s,len(ws),{r["user"] for r in ws if r["is_buy"]}
        b1,s1,n1,ub1=agg(w1); b5,s5,n5,ub5=agg(w5); b15,s15,n15,ub15=agg(w15)
        prev_ub={r["user"] for r in st.trades if r["is_buy"] and r["user"] and now-900<=r["ts"]<now-300}
        liq=max(1e-9,st.liq_sol); px=st.price or 0.0
        p1,p5,p15=st.price_at(60,now),st.price_at(300,now),st.price_at(900,now)
        init_price=(st.init_mcap_sol/st.supply) if st.supply else 0.0
        f.update({"pg_age_s":st.age(now),"pg_mcap_sol":st.mcap_sol,"pg_log_mcap":math.log1p(max(0.0,st.mcap_sol)),
                  "pg_liq_sol":st.liq_sol,"pg_liq_ratio":safe_div(st.liq_sol,st.mcap_sol),
                  "pg_liq_growth":safe_div(st.liq_sol-st.init_liq_sol,max(1e-9,st.init_liq_sol)),
                  "pg_turnover_1m":safe_div(b1+s1,liq),"pg_turnover_5m":safe_div(b5+s5,liq),"pg_vol_5m":b5+s5,
                  "pg_buy_sell_ratio_5m":safe_div(b5,s5+0.02),"pg_n_trades_5m":n5,
                  "pg_buys_1m":len([r for r in w1 if r["is_buy"]]),"pg_unique_buyers_1m":len(ub1),
                  "pg_unique_buyers_5m":len(ub5),"pg_unique_buyers_15m":len(ub15),
                  "pg_buyer_growth":safe_div(len(ub5),max(1,len(prev_ub))),"pg_new_buyers_5m":len(ub5-prev_ub),
                  "pg_avg_buy_5m":safe_div(b5,max(1,len([r for r in w5 if r["is_buy"]]))),
                  "pg_max_buy_5m":max([r["sol"] for r in w5 if r["is_buy"]] or [0.0]),
                  "pg_buy_hhi_5m":hhi([r["sol"] for r in w5 if r["is_buy"]]) if w5 else 1.0,
                  "pg_ret_1m":safe_div(px-p1,p1),"pg_ret_5m":safe_div(px-p5,p5),"pg_ret_15m":safe_div(px-p15,p15),
                  "pg_ret_since_birth":safe_div(px-init_price,init_price),
                  "pg_ath_mult":safe_div(st.peak_mcap,max(1e-9,st.init_mcap_sol)),
                  "pg_drawdown_ath":safe_div(st.peak_mcap-st.mcap_sol,max(1e-9,st.peak_mcap)),
                  "pg_creator_sold":1.0 if st.creator_sold_sol>0.05 else 0.0,"pg_mayhem":1.0 if st.mayhem else 0.0})
        amts=[round(r["sol"],4) for r in w5 if r["sol"]>0]
        if amts:
            c=Counter(amts); f["pg_dup_amount_share"]=safe_div(sum(n for a,n in c.items() if n>=3),len(amts))
            f["pg_dust_share"]=sum(1 for a in amts if a<0.02)/len(amts)
        else: f["pg_dup_amount_share"]=1.0; f["pg_dust_share"]=1.0
        rt=sum(1 for u,d in list(st.buyers.items())[:300] if (s:=st.sellers.get(u)) and abs(s["first_ts"]-d["first_ts"])<15)
        f["pg_roundtrip_share"]=safe_div(rt,max(1,len(st.buyers)))
        return f

class RunnerScorer:
    name="runner"
    PRIOR={"turnover":1.6,"buyers":1.5,"growth":1.1,"liq_ratio":0.9,"momentum":1.0,"buy_pressure":0.8,"retail":0.6,
           "wash":-1.8,"creator_sold":-2.2,"chase":-1.4,"illiquid":-2.0,"drawdown":-1.0,"hhi":-0.8}
    def __init__(self, settings): self.s=settings
    def score(self,F):
        c={"turnover":clamp(F.get("pg_turnover_5m",0)/1.2),"buyers":clamp(F.get("pg_unique_buyers_5m",0)/40),
           "growth":clamp(F.get("pg_buyer_growth",0)/1.5),"liq_ratio":clamp(F.get("pg_liq_ratio",0)/0.25),
           "momentum":clamp((F.get("pg_ret_5m",0)+0.2)/0.9),"buy_pressure":clamp(F.get("pg_buy_sell_ratio_5m",0)/3),
           "retail":clamp(1-F.get("pg_avg_buy_5m",0)/2.0),
           "wash":clamp(max(F.get("pg_dup_amount_share",0),F.get("pg_roundtrip_share",0))/0.5),
           "creator_sold":1.0 if F.get("pg_creator_sold") else 0.0,
           "chase":clamp(max(0.0,F.get("pg_ath_mult",1)-8)/20),"illiquid":clamp(1-F.get("pg_liq_sol",0)/10),
           "drawdown":clamp(F.get("pg_drawdown_ath",0)/0.6),"hhi":clamp(max(0.0,F.get("pg_buy_hhi_5m",0)-0.35)/0.5)}
        z=-1.9+sum(w*c[k] for k,w in self.PRIOR.items()); return 1/(1+math.exp(-z))
    def gates(self,F):
        s=self.s
        return {"liquidity":F.get("pg_liq_sol",0)>=s.runner_min_liq_sol,"fresh":F.get("pg_age_s",0)<=s.runner_max_age_s,
                "turnover":F.get("pg_turnover_5m",0)>=s.runner_min_turnover,"buyers":F.get("pg_unique_buyers_5m",0)>=s.runner_min_buyers,
                "not_wash":max(F.get("pg_dup_amount_share",0),F.get("pg_roundtrip_share",0))<0.5,
                "creator_holding":F.get("pg_creator_sold",0)<0.5,"not_chasing":F.get("pg_ath_mult",1)<=s.runner_max_ath_mult,
                "drawdown_ok":F.get("pg_drawdown_ath",0)<=0.6,"not_mayhem":F.get("pg_mayhem",0)<0.5}
    def plan(self,F):
        return {"kind":"runner","entry_mcap_sol":round(F.get("pg_mcap_sol",0),1),"entry_liq_sol":round(F.get("pg_liq_sol",0),2),
                "size_sol":self.s.runner_size_sol,"ladder":[{"mult":2.0,"sell_pct":0.20},{"mult":5.0,"sell_pct":0.20},{"mult":15.0,"sell_pct":0.20},{"mult":50.0,"sell_pct":0.15}],
                "trail":{"from_peak_drop_pct":0.35,"applies_to_pct":0.25},"stop_loss_pct":self.s.runner_stop_pct,
                "exit_on":["creator_sell","liq_drop_60pct","turnover_decay","drawdown_ath>60pct"],"time_stop_s":None}
    def decide(self,F):
        score=self.score(F); g=self.gates(F); passed=all(g.values()); tier="NONE"
        if passed:
            if score>=self.s.runner_strong_score: tier="RUN"
            elif score>=self.s.runner_entry_score: tier="SETUP"
            elif score>=self.s.runner_watch_score: tier="WATCH"
        elif score>=self.s.runner_strong_score: tier="WATCH"
        return {"score":round(score,4),"tier":tier,"gates":g,"gates_passed":passed,"features":F,"plan":self.plan(F) if tier in ("SETUP","RUN") else {}}

class RunnerBook:
    def __init__(self, settings, store):
        self.s=settings; self.store=store; self.peak: dict[int,float]={}
    def open_position(self, st, signal_id, mcap, liq):
        cur=self.store.execute("""INSERT INTO positions(mint,signal_id,opened_ts,entry_mcap,entry_price,size_sol,status,peak_mcap,kind,pool)
            VALUES(?,?,?,?,?,?, 'open', ?, 'runner', ?)""", (st.base_mint,signal_id,time.time(),mcap,st.price,self.s.runner_size_sol,mcap,st.pool))
        pid=int(cur.lastrowid); self.store.kv_set(f"liq_{pid}", float(liq or st.liq_sol or 0.0)); self.peak[pid]=float(mcap or 0.0); return pid
    def open_count(self):
        r=self.store.one("SELECT COUNT(*) c FROM positions WHERE status='open' AND kind='runner'"); return int(r["c"]) if r else 0
    def evaluate(self, pos, st, F):
        pid=int(pos["id"]); entry=float(pos["entry_mcap"] or 0) or 1e-9; cur=float(st.mcap_sol or entry)
        peak=max(float(pos["peak_mcap"] or entry), self.peak.get(pid, entry), cur); self.peak[pid]=peak
        mult=cur/entry; peak_mult=peak/entry; age=time.time()-float(pos["opened_ts"] or time.time())
        if mult<=1-float(self.s.runner_stop_pct): return ("CLOSE",f"stop {mult:.2f}x",1.0)
        if peak_mult>=1.60 and mult<=1.03: return ("CLOSE",f"pareggio dopo picco {peak_mult:.2f}x",1.0)
        if F.get("pg_creator_sold"): return ("CLOSE","creator sta vendendo",1.0)
        liq0=float(self.store.kv_get(f"liq_{pid}", st.liq_sol) or st.liq_sol or 0.0)
        if st.liq_sol and liq0 and st.liq_sol<0.4*liq0: return ("CLOSE","liquidità crollata -60%",1.0)
        if age>1200 and F.get("pg_turnover_5m",0)<0.03 and mult<1.15: return ("CLOSE","turnover esaurito",1.0)
        sold=float(self.store.kv_get(f"sold_{pid}",0.0) or 0.0); cum=0.0
        for m,pct in ((2.0,0.20),(5.0,0.20),(15.0,0.20),(50.0,0.15)):
            if mult>=m and sold<=cum+1e-9: return ("SELL",f"target {m}x",pct)
            cum+=pct
        if peak_mult>=2.0 and 1-(cur/peak)>=0.35: return ("CLOSE",f"trailing da {peak_mult:.1f}x",1.0)
        return None
    def apply(self, pos, action, reason, pct, st):
        pid=int(pos["id"]); entry=float(pos["entry_mcap"] or 0) or 1e-9; cur=float(st.mcap_sol or entry); mult=cur/entry
        cost_pct=(0.30*2+self.s.slippage_bps/100.0)/100.0
        if action=="CLOSE":  # chiude solo il residuo non ancora venduto a scaletta
            pct=pct*max(0.0,1.0-float(self.store.kv_get(f"sold_{pid}",0.0) or 0.0))
        pnl=float(pos["size_sol"] or 0)*pct*((mult-1.0)-cost_pct); prev=float(pos["pnl_sol"] or 0.0); size=float(pos["size_sol"] or 0) or 1e-9
        peak=max(float(pos["peak_mcap"] or 0),cur,self.peak.get(pid,0.0)); self.peak[pid]=peak
        if action=="CLOSE":
            total=prev+pnl
            self.store.execute("""UPDATE positions SET status='closed',closed_ts=?,exit_mcap=?,pnl_sol=?,pnl_pct=?,reason=?,peak_mcap=? WHERE id=?""",
                               (time.time(),cur,total,total/size,reason,peak,pid))
        else:
            sold=float(self.store.kv_get(f"sold_{pid}",0.0) or 0.0)+pct; self.store.kv_set(f"sold_{pid}",sold)
            self.store.execute("UPDATE positions SET pnl_sol=COALESCE(pnl_sol,0)+?,reason=?,peak_mcap=? WHERE id=?", (pnl,reason,peak,pid))
            if sold>=0.999: self.store.execute("UPDATE positions SET status='closed',closed_ts=? WHERE id=?", (time.time(),pid))
        return {"mint":st.base_mint,"pool":st.pool,"kind":"runner","action":action,"reason":reason,"pct":pct,"mult":round(mult,3),"pnl_sol":round(pnl,5),"mcap_sol":round(cur,1)}
    def tick(self, pools, feats):
        out=[]; rows=self.store.q("SELECT * FROM positions WHERE status='open' AND kind='runner'")
        for pos in rows:
            st=pools.get(pos["pool"])
            if st is None: continue
            cur=float(st.mcap_sol or pos["entry_mcap"] or 0)
            if cur>float(pos["peak_mcap"] or 0):
                self.store.execute("UPDATE positions SET peak_mcap=? WHERE id=?", (cur,pos["id"])); pos=dict(pos); pos["peak_mcap"]=cur
            res=self.evaluate(pos,st,feats.get(pos["pool"],{}))
            if res: out.append(self.apply(pos,res[0],res[1],res[2],st))
        return out
