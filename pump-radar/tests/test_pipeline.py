import time
import pytest
from pumpradar.agents.curve import CurveAgent
from pumpradar.agents.risk import RiskAgent
from pumpradar.agents.scorer import ScorerAgent
from pumpradar.learning.labeler import Labeler
from pumpradar.learning.trainer import build_dataset
from pumpradar.settings import Settings
from pumpradar.state import TokenState
from pumpradar.store import Store
from pumpradar.utils import curve_progress, gini, hhi, mcap_sol, progress_check, spot_price_sol

def cfg(tmp_path):
    s=Settings(); s.db_path=str(tmp_path/"p.db"); return s

def build_token(organic=True, age_s=60.0, buyers=14):
    now=time.time(); st=TokenState(mint="TESTmint111111111111111111111111111111pump",name="Test Coin",symbol="TEST",creator="DEV",created_at=now-age_s,lane="sol",quote_mint="SOL",rtok=793.1e6)
    vsol,vtok=30.0,1.073e9; k=vsol*vtok
    for i in range(40):
        ts=now-age_s+i*age_s/40
        trader=f"w{i%buyers}" if organic else f"bot{i%3}"; sol=(0.12+(i%6)*0.06) if organic else 0.5; is_buy=(i%7!=3) if organic else True
        if is_buy: vsol+=sol*0.99; vtok=k/vsol
        st.observe({"ts":ts,"trader":trader,"is_buy":is_buy,"sol":sol,"tokens":sol*1e6,"vsol":vsol,"vtok":vtok,"mcap_sol":vsol*1e9/vtok,"slot":1000+i//3,"rtok":max(0.0,793.1e6-(1.073e9-vtok)),"lane":"sol"})
    st.meta={"twitter":"x.com/t","telegram":"","description":"a"*80,"image_reuse":0}; return st

def test_curve_math():
    assert spot_price_sol(30,1.073e9)==pytest.approx(30/1.073e9)
    assert mcap_sol(30,1.073e9)==pytest.approx(27.96,abs=0.05)
    assert curve_progress(115)==1.0 and curve_progress(30)==0.0
    assert 0.2<progress_check(20)<0.25
    assert hhi([1,1,1,1])==pytest.approx(0.25); assert gini([1]*10)==pytest.approx(0,abs=1e-9)

def test_organic_passes_and_bundle_features_block(tmp_path):
    c=cfg(tmp_path); store=Store(c.db_path); scorer=ScorerAgent(c,store)
    st=build_token(True); F={**CurveAgent().features(st),**RiskAgent(c).features(st)}; d=scorer.decide(st,F,150)
    assert d["gates"]["min_buyers"] and d["gates"]["not_bundle"] and d["score"]>0.45
    F2=dict(F); F2.update({"burst_300ms_share":0.9,"single_token_wallet_share":0.95})
    assert not scorer.gates(F2)["not_bundle"]

def test_engineered_and_cross_lane_blocked(tmp_path):
    c=cfg(tmp_path); store=Store(c.db_path); scorer=ScorerAgent(c,store); st=build_token(True)
    F={**CurveAgent().features(st),**RiskAgent(c).features(st)}; F["risk_engineered"]=1.0
    d=scorer.decide(st,F,150); assert not d["gates_passed"] and not d["plan"]
    st.lane="cross"; F={**CurveAgent().features(st),**RiskAgent(c).features(st)}; d=scorer.decide(st,F,150)
    assert not d["gates"]["tradeable_lane"] and d["tier"]!="ENTRY"

def seed(store,n=40):
    base=time.time()-4000
    for i in range(n):
        mint=f"TOK{i:04d}"+"x"*30; store.upsert_token({"mint":mint,"name":f"T{i}","symbol":f"T{i}","uri":"","creator":f"dev{i%5}","created_at":base+i*60,"first_seen":base+i*60,"init_sol":0.1,"init_mcap_sol":28,"mayhem":0,"pool":"pump","state":"dead","last_ts":base+i*60+600,"creator_sig":None,"quote_mint":"SOL","lane":"sol"})
        explodes=i%4==0; t0=base+i*60
        for j in range(20):
            mult=(1+6*j/20) if explodes else (1-0.4*j/20)
            store.add_trade({"mint":mint,"ts":t0+j*20,"tx":f"tx{i}{j}","trader":f"w{i}_{j%6}","is_buy":True,"sol":0.3,"tokens":1e6,"vsol":30+j*.5,"vtok":1e9,"mcap_sol":28*mult,"slot":100+j,"source":"test","lane":"sol","rtok":700e6-j*1e6})
        for j in range(6):
            store.add_snapshot(mint,t0+30+j*10,30+j*10,28,{"age_s":30+j*10,"mcap_sol":28,"buy_sol_30s":1.0,"unique_buyers_life":8,"curve_progress":0.05},0.5,None,None,None)

def test_labeler_and_dataset(tmp_path):
    c=cfg(tmp_path); store=Store(c.db_path); seed(store)
    Labeler(store,c).label_outcomes(); rows=store.q("SELECT * FROM outcomes"); assert len(rows)>=30
    assert any((r["peak_mcap"] or 0)/r["entry_mcap"]>=1.8 for r in rows)
    X,y,ts,meta=build_dataset(store); assert len(X)>20 and 0<y.sum()<len(y)

def test_trainer_report(tmp_path):
    pytest.importorskip("sklearn")
    from pumpradar.learning.trainer import train
    c=cfg(tmp_path); store=Store(c.db_path); seed(store,60)
    rep=train(store,out_path=tmp_path/"m.pkl",min_rows=20,force=True)
    if "error" in rep: pytest.skip(rep["error"])
    assert 0<=rep["auc"]<=1 and "selection" in rep
