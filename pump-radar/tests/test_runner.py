import random, time
from pumpradar.runner import GradState, PostGradAgent, RunnerBook, RunnerScorer
from pumpradar.settings import Settings
from pumpradar.store import Store
POOL="POOLtest1111111111111111111111111111111111"; MINT="MINTtest111111111111111111111111111111pump"

def settings(tmp_path):
    s=Settings(); s.db_path=str(tmp_path/"t.db"); s.runner_min_liq_sol=8; s.runner_min_buyers=12; s.runner_min_turnover=0.10; return s

def build_pool(healthy=True, age_s=600):
    now=time.time(); rng=random.Random(7)
    st=GradState(pool=POOL,base_mint=MINT,bdec=6,qdec=9,supply=1e9,created_at=now-age_s,creator="CREATOR")
    pbase=int(206.9e6*1e6); pquote=int(85*1e9); k=pbase*pquote
    def buy(ts,user,sol):
        nonlocal pbase,pquote
        dq=int(sol*1e9); nq=pquote+dq; nb=k//nq; amt=pbase-nb; pquote,pbase=nq,nb
        st.observe({"ts":ts,"user":user,"is_buy":True,"quote_amount":dq,"base_amount":amt,"pool_base":pbase,"pool_quote":pquote})
    def sell(ts,user,tokens):
        nonlocal pbase,pquote
        amt=int(tokens*1e6); nb=pbase+amt; nq=k//nb; dq=pquote-nq; pquote,pbase=nq,nb
        st.observe({"ts":ts,"user":user,"is_buy":False,"quote_amount":dq,"base_amount":amt,"pool_base":pbase,"pool_quote":pquote})
    if healthy:
        for i in range(100):
            buy(now-560+i*5, f"buyer{i%18}", rng.uniform(0.06,0.22))
            if i%10==0: sell(now-560+i*5+1, f"buyer{(i+3)%18}", rng.uniform(20000,90000))
        for i in range(80): buy(now-280+i*3, f"buyer{(i*2)%18}", rng.uniform(0.07,0.25))
    else:
        for i in range(160): buy(now-560+i*3, f"bot{i%2}", 0.05) if i%2==0 else sell(now-560+i*3, f"bot{i%2}", 120000)
    return st

def test_healthy_beats_wash(tmp_path):
    agent=PostGradAgent(); scorer=RunnerScorer(settings(tmp_path)); good=agent.features(build_pool(True)); bad=agent.features(build_pool(False))
    assert scorer.score(good)>scorer.score(bad)+0.15
    assert good["pg_unique_buyers_5m"]>bad["pg_unique_buyers_5m"]
    assert bad["pg_dup_amount_share"]>=good["pg_dup_amount_share"]

def test_healthy_runner_gates_and_plan(tmp_path):
    d=RunnerScorer(settings(tmp_path)).decide(PostGradAgent().features(build_pool(True)))
    assert d["gates_passed"], [k for k,v in d["gates"].items() if not v]
    assert d["tier"] in ("WATCH","SETUP","RUN")
    if d["plan"]: assert d["plan"]["time_stop_s"] is None and d["plan"]["ladder"][-1]["mult"]>=15

def test_wash_and_creator_block(tmp_path):
    s=settings(tmp_path); d=RunnerScorer(s).decide(PostGradAgent().features(build_pool(False)))
    assert not d["gates_passed"] and d["tier"] in ("NONE","WATCH")
    st=build_pool(True); st.creator="buyer0"; st.creator_sold_sol=1.5; F=PostGradAgent().features(st)
    assert F["pg_creator_sold"]==1.0 and not RunnerScorer(s).decide(F)["gates"]["creator_holding"]

def test_exit_ladder_trailing_stop(tmp_path):
    s=settings(tmp_path); store=Store(s.db_path); book=RunnerBook(s,store); st=build_pool(True)
    pid=book.open_position(st,1,st.mcap_sol,st.liq_sol); pos=store.one("SELECT * FROM positions WHERE id=?", (pid,)); entry=pos["entry_mcap"]
    st.mcap_sol=entry*2.2; res=book.evaluate(pos,st,{}); assert res and res[0]=="SELL" and "2.0x" in res[1]; book.apply(pos,res[0],res[1],res[2],st)
    pos=store.one("SELECT * FROM positions WHERE id=?", (pid,)); st.mcap_sol=entry*5.4; res=book.evaluate(pos,st,{}); assert res and res[0]=="SELL" and "5.0x" in res[1]; book.apply(pos,res[0],res[1],res[2],st)
    pos=store.one("SELECT * FROM positions WHERE id=?", (pid,)); st.mcap_sol=entry*2.3; res=book.evaluate(pos,st,{}); assert res and res[0]=="CLOSE" and "trailing" in res[1]
    st2=build_pool(True); pid2=book.open_position(st2,2,st2.mcap_sol,st2.liq_sol); pos2=store.one("SELECT * FROM positions WHERE id=?", (pid2,)); st2.mcap_sol=pos2["entry_mcap"]*0.4
    res=book.evaluate(pos2,st2,{}); assert res and res[0]=="CLOSE" and "stop" in res[1]

def test_creator_sell_exit(tmp_path):
    s=settings(tmp_path); store=Store(s.db_path); book=RunnerBook(s,store); st=build_pool(True); pid=book.open_position(st,1,st.mcap_sol,st.liq_sol); pos=store.one("SELECT * FROM positions WHERE id=?", (pid,)); st.mcap_sol=pos["entry_mcap"]*1.1
    res=book.evaluate(pos,st,{"pg_creator_sold":1.0}); assert res and res[0]=="CLOSE" and "creator" in res[1]
