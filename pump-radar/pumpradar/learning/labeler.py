from __future__ import annotations
import logging, time
from collections import defaultdict
log=logging.getLogger("learning.labeler")

class Labeler:
    def __init__(self, store, settings): self.store=store; self.s=settings
    def label_outcomes(self, horizon_s: float = 900.0) -> int:
        now=time.time(); rows=self.store.q("SELECT mint,state,bonded_at,created_at FROM tokens WHERE created_at<=? ORDER BY created_at DESC LIMIT 20000", (now-horizon_s,))
        n=0
        for r in rows:
            mint=r["mint"]; first=self.store.one("SELECT MIN(ts) ts, MAX(ts) last FROM trades WHERE mint=?", (mint,))
            if not first or not first["ts"]: continue
            entry_ts=float(first["ts"]); e=self.store.one("SELECT mcap_sol FROM trades WHERE mint=? AND mcap_sol IS NOT NULL AND mcap_sol>0 ORDER BY ts LIMIT 1", (mint,))
            entry_mcap=float(e["mcap_sol"]) if e and e["mcap_sol"] else 0.0
            if entry_mcap<=0: continue
            def peak(sec):
                q=self.store.one("SELECT MAX(mcap_sol) p FROM trades WHERE mint=? AND ts BETWEEN ? AND ?", (mint,entry_ts,entry_ts+sec)); return float(q["p"] or 0) if q else 0.0
            def trough(sec):
                q=self.store.one("SELECT MIN(mcap_sol) p FROM trades WHERE mint=? AND ts BETWEEN ? AND ?", (mint,entry_ts,entry_ts+sec)); return float(q["p"] or entry_mcap) if q else entry_mcap
            p5,p15,p60=peak(300),peak(900),peak(3600); p6=peak(21600) if now-entry_ts>21600 else p60; p24=peak(86400) if now-entry_ts>86400 else p6
            nb=self.store.one("SELECT COUNT(DISTINCT trader) c FROM trades WHERE mint=?", (mint,))
            engineered=0
            if r["state"]=="bonded" and r["bonded_at"] and float(r["bonded_at"])-entry_ts<60: engineered=1
            if nb and (nb["c"] or 0)<=2: engineered=1
            self.store.execute("""INSERT INTO outcomes(mint,entry_ts,entry_mcap,max_mult_5m,max_mult_15m,max_mult_60m,max_mult_6h,max_mult_24h,min_mult,bonded,engineered,peak_mcap,labeled_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(mint) DO UPDATE SET entry_ts=excluded.entry_ts,entry_mcap=excluded.entry_mcap,
                max_mult_5m=excluded.max_mult_5m,max_mult_15m=excluded.max_mult_15m,max_mult_60m=excluded.max_mult_60m,
                max_mult_6h=excluded.max_mult_6h,max_mult_24h=excluded.max_mult_24h,min_mult=excluded.min_mult,
                bonded=excluded.bonded,engineered=excluded.engineered,peak_mcap=excluded.peak_mcap,labeled_at=excluded.labeled_at""",
                (mint,entry_ts,entry_mcap,p5/entry_mcap,p15/entry_mcap,p60/entry_mcap,p6/entry_mcap,p24/entry_mcap,trough(horizon_s)/entry_mcap,1 if r["state"]=="bonded" else 0,engineered,p24,now))
            n+=1
        log.info("etichettati %d token", n); return n
    def update_wallet_skill(self, min_mult: float = 5.0, early_window_s: float = 90.0):
        outcomes=self.store.q("SELECT mint,entry_ts,entry_mcap,peak_mcap FROM outcomes WHERE entry_mcap>0 ORDER BY labeled_at DESC LIMIT 5000")
        if not outcomes: return
        wins=defaultdict(int); early=defaultdict(int)
        for o in outcomes:
            entry_ts=float(o["entry_ts"] or 0); mult=float(o["peak_mcap"] or 0)/float(o["entry_mcap"] or 1)
            buyers=self.store.q("SELECT DISTINCT trader FROM trades WHERE mint=? AND is_buy=1 AND ts<=?", (o["mint"], entry_ts+early_window_s))
            for b in buyers:
                if not b["trader"]: continue
                early[b["trader"]]+=1
                if mult>=min_mult: wins[b["trader"]]+=1
        for wallet,n_early in early.items():
            score=(wins.get(wallet,0)+1)/(n_early+2)
            self.store.execute("UPDATE wallets SET wins=?, score=? WHERE addr=?", (wins.get(wallet,0),score,wallet))
        self.store.execute("UPDATE wallets SET is_bot=1 WHERE n_trades>=40 AND (sol_bought+sol_sold)/NULLIF(n_trades,0)<0.25")
    async def post_grad_tracking(self, enricher, limit: int = 40):
        rows=self.store.q("SELECT mint FROM tokens WHERE state='bonded' LIMIT ?", (limit,))
        for r in rows:
            d=await enricher.dexscreener_pair(r["mint"])
            if d and d.get("mcap") and enricher.sol_price:
                self.store.execute("UPDATE outcomes SET peak_mcap=MAX(COALESCE(peak_mcap,0),?) WHERE mint=?", (d["mcap"]/enricher.sol_price, r["mint"]))
