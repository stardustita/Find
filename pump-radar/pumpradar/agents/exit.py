from __future__ import annotations
import time

class ExitAgent:
    name="exit"
    def __init__(self, settings, store): self.s=settings; self.store=store
    def open_position(self, mint, signal_id, mcap, price_sol):
        cur=self.store.execute("""INSERT INTO positions(mint,signal_id,opened_ts,entry_mcap,entry_price,size_sol,status,peak_mcap,kind)
            VALUES(?,?,?,?,?,?, 'open', ?, 'curve')""", (mint,signal_id,time.time(),mcap,price_sol,self.s.position_sol,mcap))
        return int(cur.lastrowid)
    def open_count(self):
        r=self.store.one("SELECT COUNT(*) c FROM positions WHERE status='open' AND kind='curve'"); return int(r["c"]) if r else 0
    def realized_today(self):
        lt=time.localtime(); start=time.mktime((lt.tm_year,lt.tm_mon,lt.tm_mday,0,0,0,0,0,-1))
        r=self.store.one("SELECT COALESCE(SUM(pnl_sol),0) s FROM positions WHERE status='closed' AND closed_ts>=?", (start,))
        return float(r["s"]) if r else 0.0
    def evaluate(self, pos, st, F):
        entry=float(pos["entry_mcap"] or 0) or 1e-9; cur=float(st.mcap_sol or entry)
        peak=max(float(pos["peak_mcap"] or entry),cur); mult=cur/entry; peak_mult=peak/entry
        age=time.time()-float(pos["opened_ts"] or time.time())
        if mult <= 1-float(getattr(self.s,"curve_stop_pct",0.35)): return ("CLOSE",f"stop_loss {mult:.2f}x",1.0)
        if peak_mult>=1.30 and mult<=1.03: return ("CLOSE",f"pareggio dopo picco {peak_mult:.2f}x",1.0)
        if F.get("dev_sold_flag",0)>=1 and mult<1.6: return ("CLOSE","dev ha venduto",1.0)
        if F.get("risk_sell_pressure_30s",0)>3.0 and mult<1.4: return ("CLOSE","pressione di vendita dominante",1.0)
        idle=time.time()-float(getattr(st,"last_ts",0) or 0)
        if idle>45 and mult<1.05: return ("CLOSE","token inattivo",1.0)
        if age>240 and mult<1.05: return ("CLOSE","momentum esaurito 4min",1.0)
        if age>780 and mult<1.2: return ("CLOSE","time_stop 13min",1.0)
        sold=float(self.store.kv_get(f"sold_{pos['id']}",0.0) or 0.0); cum=0.0
        for m,pct in ((1.8,0.25),(3.0,0.25),(6.0,0.25)):
            if mult>=m and sold<=cum+1e-9: return ("SELL",f"target {m}x",pct)
            cum+=pct
        if peak_mult>=1.8 and 1-(cur/peak)>=0.35: return ("CLOSE",f"trailing da picco {peak_mult:.2f}x",1.0)
        return None
    def apply(self, pos, action, reason, pct, st):
        entry=float(pos["entry_mcap"] or 0) or 1e-9; cur=float(st.mcap_sol or entry); mult=cur/entry
        cost_pct=(self.s.pump_fee_bps*2+self.s.slippage_bps)/10000.0
        if action=="CLOSE":  # chiude solo il residuo non ancora venduto a scaletta
            pct=pct*max(0.0,1.0-float(self.store.kv_get(f"sold_{pos['id']}",0.0) or 0.0))
        pnl=float(pos["size_sol"] or 0)*pct*((mult-1.0)-cost_pct)
        prev=float(pos["pnl_sol"] or 0.0); total_size=float(pos["size_sol"] or 0) or 1e-9
        peak=max(float(pos["peak_mcap"] or 0),cur)
        if action=="CLOSE":
            total=prev+pnl
            self.store.execute("""UPDATE positions SET status='closed',closed_ts=?,exit_mcap=?,pnl_sol=?,pnl_pct=?,reason=?,peak_mcap=? WHERE id=?""",
                               (time.time(),cur,total,total/total_size,reason,peak,pos["id"]))
        else:
            sold=float(self.store.kv_get(f"sold_{pos['id']}",0.0) or 0.0)+pct; self.store.kv_set(f"sold_{pos['id']}",sold)
            self.store.execute("UPDATE positions SET pnl_sol=COALESCE(pnl_sol,0)+?,reason=?,peak_mcap=? WHERE id=?", (pnl,reason,peak,pos["id"]))
            if sold>=0.999: self.store.execute("UPDATE positions SET status='closed',closed_ts=? WHERE id=?", (time.time(),pos["id"]))
        return {"mint":st.mint,"kind":"curve","action":action,"reason":reason,"pct":pct,"mult":round(mult,3),"pnl_sol":round(pnl,5),"mcap_sol":round(cur,2)}
    def tick(self, states, feats):
        out=[]; rows=self.store.q("SELECT * FROM positions WHERE status='open' AND kind='curve'")
        for pos in rows:
            st=states.get(pos["mint"])
            if st is None: continue
            cur=float(st.mcap_sol or pos["entry_mcap"] or 0)
            if cur>float(pos["peak_mcap"] or 0): self.store.execute("UPDATE positions SET peak_mcap=? WHERE id=?", (cur,pos["id"])); pos=dict(pos); pos["peak_mcap"]=cur
            res=self.evaluate(pos,st,feats.get(pos["mint"],{}))
            if res: out.append(self.apply(pos,res[0],res[1],res[2],st))
        return out
