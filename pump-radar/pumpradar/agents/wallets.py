from __future__ import annotations
import time
from collections import Counter, defaultdict
from .base import Agent
from ..utils import cosine_similarity, safe_div

class WalletGraphAgent(Agent):
    name="walletgraph"
    def __init__(self, store=None, refresh_s: float = 45.0, min_mult_for_cohort: float = 5.0):
        self.store=store; self.refresh_s=refresh_s; self.min_mult=min_mult_for_cohort
        self._t=0.0; self.smart=set(); self.botty=set(); self.winner_sets=[]
    def refresh(self, force=False):
        now=time.time()
        if not force and now-self._t<self.refresh_s: return
        self._t=now
        if self.store is None: return
        try:
            win=self.store.q("""SELECT wt.wallet, wt.mint FROM wallet_tokens wt JOIN outcomes o ON o.mint=wt.mint
                                WHERE o.entry_mcap>0 AND o.peak_mcap/o.entry_mcap>=?""", (self.min_mult,))
            self.smart={r["wallet"] for r in win}
            per=defaultdict(set)
            for r in win: per[r["mint"]].add(r["wallet"])
            self.winner_sets=list(per.values())[-400:]
            bots=self.store.q("""SELECT addr FROM wallets WHERE n_trades>=40 AND (sol_bought+sol_sold)/NULLIF(n_trades,0)<0.35""")
            self.botty={r["addr"] for r in bots}
        except Exception:
            pass
    def observe(self, st, event):
        if len(st.buyers)%25==0: self.refresh()
    def features(self, st):
        self.refresh()
        buyers=st.buyers; n=max(1,len(buyers)); total_buy=sum(d.get("sol",0.0) for d in buyers.values()) or 1e-9
        bset=set(buyers); smart_hits=bset & self.smart; bot_hits=bset & self.botty
        best_cos=0.0
        for ws in self.winner_sets[-120:]: best_cos=max(best_cos, cosine_similarity(bset, ws))
        slot_counts=[len(v) for v in st.slots_buyers.values() if v]
        bt=sorted(float(t.get("ts") or 0) for t in st.trades if t.get("is_buy"))
        close=sum(1 for i in range(1,len(bt)) if bt[i]-bt[i-1]<=0.3)
        amts=[round(float(t.get("sol") or 0),4) for t in st.trades if t.get("is_buy") and t.get("sol")]
        counts=Counter(amts); ident=sum(c for a,c in counts.items() if c>=3 and a>0)
        single=0; checked=0
        if self.store is not None:
            for w in list(buyers.keys())[:120]:
                checked+=1
                r=self.store.one("SELECT COUNT(*) c FROM wallet_tokens WHERE wallet=?", (w,))
                if r and r["c"]<=1: single+=1
        cluster_sol=defaultdict(float)
        for t in st.trades:
            if t.get("is_buy") and t.get("slot") is not None: cluster_sol[t["slot"]]+=float(t.get("sol") or 0)
        return {"smart_hits":len(smart_hits),"smart_share_buyers":safe_div(len(smart_hits),n),
                "smart_share_sol":safe_div(sum(buyers[w].get("sol",0.0) for w in smart_hits), total_buy),
                "cohort_cosine_max":best_cos,"bot_share":safe_div(len(bot_hits),n),
                "same_slot_max_buyers":max(slot_counts) if slot_counts else 0,
                "burst_300ms_share":safe_div(close,max(1,len(bt))),
                "identical_amount_share":safe_div(ident,max(1,len(amts))),
                "single_token_wallet_share":safe_div(single,max(1,checked)) if checked else 0.0,
                "max_slot_sol_share":safe_div(max(cluster_sol.values()) if cluster_sol else 0.0,total_buy),
                "n_wallets_tracked":len(bset)}
