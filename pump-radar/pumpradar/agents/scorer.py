from __future__ import annotations
import math, pickle
from .base import Agent
from ..settings import ROOT
from ..utils import clamp

def _c01(x, hi, lo=0.0):
    try: x=float(x or 0.0)
    except Exception: x=0.0
    return clamp((x-lo)/(hi-lo) if hi!=lo else 0.0)

PRIOR={
 "unique_buyers_life_c":1.55,"sol_per_s_30s_c":1.25,"buy_sell_ratio_life_c":0.85,
 "repeat_buyer_share_c":0.80,"retail_share_c":0.65,"nar_social_score_c":0.80,
 "nar_buzz_hits_c":0.45,"smart_share_buyers_c":1.10,"cohort_cosine_max_c":0.70,
 "creator_bonded_rate_c":0.60,"creator_known_c":0.25,"buyer_growth_c":0.55,
 "risk_engineered_c":-2.60,"burst_300ms_share_c":-1.40,"single_token_wallet_share_c":-1.15,
 "risk_clone_image_c":-1.30,"risk_junk_name_c":-1.30,"nar_symbol_random_pen_c":-0.90,
 "sell_pressure_excess_c":-1.20,"dev_sold_flag_c":-0.70,"ctx_congestion_c":-0.55,
 "top1_excess_c":-1.30,"late_curve_c":-1.20,"max_slot_sol_share_c":-0.85,
}
BIAS=-1.35

class ScorerAgent(Agent):
    name="scorer"
    def __init__(self, settings, store=None):
        self.s=settings; self.store=store; self.model=None; self.model_meta={}; self.calibrated=False
        self.model_path=ROOT/"models"/"model.pkl"; self.load_model()
    def load_model(self):
        try:
            if self.model_path.exists():
                with open(self.model_path,"rb") as f: bundle=pickle.load(f)
                self.model=bundle.get("model"); self.model_meta=bundle.get("meta",{}); self.calibrated=self.model is not None
        except Exception: self.model=None; self.calibrated=False
    @staticmethod
    def transform(F):
        return {
         "unique_buyers_life_c":_c01(F.get("unique_buyers_life",0),30),
         "sol_per_s_30s_c":_c01(F.get("sol_per_s_30s",0),0.30),
         "buy_sell_ratio_life_c":_c01(F.get("buy_sell_ratio_life",0),6.0),
         "repeat_buyer_share_c":_c01(F.get("repeat_buyer_share",0),0.30),
         "retail_share_c":_c01(F.get("retail_share",0),0.75),
         "nar_social_score_c":_c01(F.get("nar_social_score",0),1.0),
         "nar_buzz_hits_c":_c01(F.get("nar_buzz_hits",0),3),
         "smart_share_buyers_c":_c01(F.get("smart_share_buyers",0),0.25),
         "cohort_cosine_max_c":_c01(F.get("cohort_cosine_max",0),0.12),
         "creator_bonded_rate_c":_c01(F.get("creator_bonded_rate",0),0.5),
         "creator_known_c":_c01(F.get("creator_known",0),1),
         "buyer_growth_c":_c01(F.get("buyer_growth",0),2.0),
         "risk_engineered_c":_c01(F.get("risk_engineered",0),1),
         "burst_300ms_share_c":_c01(F.get("burst_300ms_share",0),0.45),
         "single_token_wallet_share_c":_c01(F.get("single_token_wallet_share",0),0.7),
         "risk_clone_image_c":_c01(F.get("risk_clone_image",0),1),
         "risk_junk_name_c":_c01(F.get("risk_junk_name",0),1),
         "nar_symbol_random_pen_c":_c01(F.get("nar_symbol_random_pen",0),1),
         "sell_pressure_excess_c":_c01(max(0.0,float(F.get("risk_sell_pressure_30s",0) or 0)-1.2),3.0),
         "dev_sold_flag_c":_c01(F.get("dev_sold_flag",0),1),
         "ctx_congestion_c":_c01(F.get("ctx_congestion",0),1),
         "top1_excess_c":_c01(max(0.0,float(F.get("top1_buy_share",0) or 0)-0.45),0.55),
         "late_curve_c":_c01(max(0.0,float(F.get("curve_progress",0) or 0)-0.70),0.30),
         "max_slot_sol_share_c":_c01(F.get("max_slot_sol_share",0),0.8),
        }
    def prior_score(self,c): return 1/(1+math.exp(-(BIAS+sum(w*c.get(k,0.0) for k,w in PRIOR.items()))))
    def model_score(self,c):
        try:
            import numpy as np
            cols=list(self.model_meta.get("features") or c.keys())
            x=np.array([[c.get(k,0.0) for k in cols]], dtype=float)
            return float(self.model.predict_proba(x)[0][1])
        except Exception: return self.prior_score(c)
    def gates(self,F,c=None):
        s=self.s
        return {
         "age":float(F.get("age_s",0) or 0)<=s.prefilter_max_age_s,
         "not_engineered":float(F.get("risk_engineered",0) or 0)<0.5,
         "curve_window":0.01<=float(F.get("curve_progress",0) or 0)<=0.72,
         "min_buyers":float(F.get("unique_buyers_life",0) or 0)>=8,
         "not_bundle":float(F.get("burst_300ms_share",0) or 0)<0.50 and float(F.get("single_token_wallet_share",0) or 0)<0.75,
         "not_selloff":float(F.get("risk_sell_pressure_30s",0) or 0)<1.8,
         "dev_holding":float(F.get("dev_hold_pct",0) or 0)<0.20,
         "not_clone":float(F.get("risk_clone_image",0) or 0)<0.5,
         "liquidity_floor":float(F.get("buy_sol_30s",0) or 0)>=0.4,
         "no_distribution":float(F.get("risk_distribution",0) or 0)<0.5,
         "tradeable_lane":float(F.get("lane_sol",0) or 0)>=0.5,
        }
    def plan(self,F,entry_mcap):
        return {"kind":"curve","entry_mcap_sol":round(float(entry_mcap or 0),2),"size_sol":self.s.position_sol,
                "ladder":[{"mult":1.8,"sell_pct":0.25},{"mult":3.0,"sell_pct":0.25},{"mult":6.0,"sell_pct":0.25}],
                "trail":{"from_peak_drop_pct":0.35,"applies_to_pct":0.25},"stop_loss_pct":self.s.curve_stop_pct,
                "time_stop_s":780,"exit_on":["dev_sell","sell_pressure>3x","no_new_buyers_120s"]}
    def entry_gates(self,F):
        """Gate SOLO per l'ingresso operativo (ENTRY/STRONG). I dati reali mostrano
        che inseguire spike verticali e ingressi a curva avanzata ha EV negativo:
        chi fallisce questi gate resta WATCH (osservazione), mai posizione."""
        s=self.s; progress=float(F.get("curve_progress",0) or 0)
        return {
         "entry_window":float(getattr(s,"entry_min_progress",0.03))<=progress<=float(getattr(s,"entry_max_progress",0.45)),
         "entry_mcap_cap":float(F.get("mcap_sol",0) or 0)<=float(getattr(s,"max_entry_mcap_sol",150.0)),
         "not_chasing":float(F.get("mcap_ret_30s",0) or 0)<=float(getattr(s,"entry_max_ret_30s",0.85)),
         "flow_not_exhausted":not (float(F.get("flow_decel",0) or 0)>0.55 and float(F.get("risk_sell_pressure_30s",0) or 0)>1.2),
        }
    def decide(self, st, F, sol_price=0.0):
        c=self.transform(F); score=self.model_score(c) if self.model is not None else self.prior_score(c)
        g=self.gates(F,c); eg=self.entry_gates(F); passed=all(g.values()); entry_ok=all(eg.values()); tier="NONE"
        if passed and entry_ok:
            if score>=self.s.min_strong_score: tier="STRONG"
            elif score>=self.s.min_alert_score: tier="ENTRY"
            elif score>=self.s.watch_score: tier="WATCH"
        elif passed and score>=self.s.watch_score:
            tier="WATCH"  # qualita' ok ma ingresso vietato (tardi/spike/flusso esaurito)
        elif score>=self.s.min_strong_score and F.get("risk_engineered",0)<0.5 and F.get("risk_clone_image",0)<0.5:
            tier="WATCH"  # osservazione, mai operativita' con gate rossi
        g={**g, **eg}
        progress=float(F.get("curve_progress",0) or 0)
        return {"score":round(float(score),4),"tier":tier,"gates":g,"gates_passed":passed,
                "source":"model" if self.model is not None else "prior","features":F,
                "plan":self.plan(F,F.get("mcap_sol",0)) if tier in ("ENTRY","STRONG") else {},
                "p_bond":round(clamp(progress*0.75+score*0.25),4),"p_2x":round(clamp(score*0.8),4),
                "p_5x":round(clamp(score*score*0.55),4),"attribution":{}}
