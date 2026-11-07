from __future__ import annotations
import json, logging, pickle, time
from pathlib import Path
from ..settings import ROOT
log=logging.getLogger("learning.trainer")
LABEL_MULT=1.8; HORIZON_S=900

def build_dataset(store, min_age_s=15.0, max_age_s=240.0):
    import numpy as np
    rows=store.q(f"""SELECT s.mint,s.ts,s.age_s,s.mcap_sol,s.features,
      (SELECT MAX(t.mcap_sol) FROM trades t WHERE t.mint=s.mint AND t.ts BETWEEN s.ts AND s.ts+{HORIZON_S}) fut_peak,
      (SELECT MIN(t.mcap_sol) FROM trades t WHERE t.mint=s.mint AND t.ts BETWEEN s.ts AND s.ts+{HORIZON_S}) fut_min,
      (SELECT COUNT(*) FROM trades t WHERE t.mint=s.mint AND t.ts BETWEEN s.ts AND s.ts+{HORIZON_S}) fut_trades,
      COALESCE(o.engineered,0) eng FROM snapshots s LEFT JOIN outcomes o ON o.mint=s.mint
      WHERE s.age_s BETWEEN {min_age_s} AND {max_age_s} AND s.mcap_sol>0 ORDER BY s.ts ASC""")
    X,y,ts,meta=[],[],[],[]
    for r in rows:
        if not r["fut_peak"] or not r["mcap_sol"] or (r["fut_trades"] or 0)<3 or r["eng"]: continue
        try: F=json.loads(r["features"])
        except Exception: continue
        mult=float(r["fut_peak"])/float(r["mcap_sol"]); X.append(F); y.append(1 if mult>=LABEL_MULT else 0); ts.append(float(r["ts"])); meta.append({"mint":r["mint"],"mult":mult,"mcap":float(r["mcap_sol"])})
    return X,np.array(y),np.array(ts),meta

def _ev(mults, size=0.1, cost_pct=0.14):
    if len(mults)==0: return 0.0
    tot=0.0
    for m in mults:
        r=0.25*max(0.0,min(m,1.8)-1)+0.25*max(0.0,min(m,3.0)-1)+0.25*max(0.0,min(m,6.0)-1)
        r += 0.25*max(0.0,m*0.7-1) if m>=1.8 else 0.25*(m-1)
        tot += (r-cost_pct)*size
    return tot/len(mults)

def train(store, out_path=None, min_rows=500, force=False):
    out_path=Path(out_path) if out_path else (ROOT/"models"/"model.pkl")
    sim_rows=store.one("SELECT COUNT(*) c FROM snapshots WHERE mint LIKE 'SIM%'")
    if sim_rows and sim_rows["c"] and not force:
        return {"error":"Il DB contiene dati sintetici (SIM): il modello non va usato live. Rilancia con --force solo per test."}
    try:
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.metrics import average_precision_score, roc_auc_score
        import numpy as np
    except Exception as e:
        return {"error":f"scikit-learn non disponibile: {e}. Installa requirements.txt"}
    from ..agents.scorer import ScorerAgent
    X,y,ts,meta=build_dataset(store); report={"n_rows":len(X),"positives":int(y.sum()) if len(y) else 0}
    if len(X)<min_rows: report["error"]=f"dati insufficienti: {len(X)} righe (servono {min_rows})"; return report
    if y.sum()<30 or (len(y)-y.sum())<30: report["error"]="sbilanciamento estremo: servono più positivi e negativi"; return report
    cols=list(ScorerAgent.transform({}).keys())
    Xm=np.array([[ScorerAgent.transform(F).get(k,0.0) for k in cols] for F in X], dtype=float)
    # split temporale PER TOKEN: gli snapshot dello stesso mint non devono stare in entrambi i lati (leakage)
    first_ts={}
    for i,m in enumerate(meta): first_ts.setdefault(m["mint"], ts[i])
    ordered_mints=sorted(first_ts, key=lambda mm: first_ts[mm])
    if len(ordered_mints)>=10:
        train_mints=set(ordered_mints[:int(len(ordered_mints)*0.7)])
        tr_idx=[i for i,m in enumerate(meta) if m["mint"] in train_mints]; te_idx=[i for i,m in enumerate(meta) if m["mint"] not in train_mints]
    else:
        cut=int(len(Xm)*0.7); tr_idx=list(range(cut)); te_idx=list(range(cut,len(Xm)))
    Xtr,ytr,Xte,yte=Xm[tr_idx],y[tr_idx],Xm[te_idx],y[te_idx]
    report["split"]="temporale per token (train/test disgiunti per mint)"
    if ytr.sum()<15 or yte.sum()<5: report["error"]="split temporale troppo sbilanciato"; return report
    base=HistGradientBoostingClassifier(max_iter=400,learning_rate=0.05,max_leaf_nodes=15,min_samples_leaf=25,l2_regularization=1.0,random_state=7)
    model=CalibratedClassifierCV(base,method="isotonic",cv=3); model.fit(Xtr,ytr)
    p=model.predict_proba(Xte)[:,1]; auc=float(roc_auc_score(yte,p)); ap=float(average_precision_score(yte,p))
    order=np.argsort(-p); top={}
    for frac in (0.01,0.02,0.05,0.10):
        k=max(1,int(len(order)*frac)); sel=order[:k]; mults=np.array([meta[te_idx[i]]["mult"] for i in sel])
        hit=float(yte[sel].mean()); top[f"top_{int(frac*100)}pct"]={"n":int(k),"hit_rate":round(hit,4),"base_rate":round(float(yte.mean()),4),"lift":round(hit/max(1e-9,float(yte.mean())),2),"avg_mult":round(float(mults.mean()),3),"ev_sol_per_0.1sol":round(float(_ev(mults)),5)}
    imp={}
    try:
        rng=np.random.default_rng(0)
        for j,name in enumerate(cols):
            Xp=Xte.copy(); rng.shuffle(Xp[:,j]); imp[name]=round(auc-float(roc_auc_score(yte,model.predict_proba(Xp)[:,1])),5)
        imp=dict(sorted(imp.items(), key=lambda kv:-kv[1])[:20])
    except Exception: pass
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bundle={"model":model,"meta":{"features":cols,"trained_at":time.time(),"n_train":int(len(Xtr)),"n_test":int(len(Xte)),"label_mult":LABEL_MULT,"horizon_s":HORIZON_S,"auc":round(auc,4),"ap":round(ap,4),"top":top}}
    with open(out_path,"wb") as f: pickle.dump(bundle,f)
    report.update({"auc":round(auc,4),"average_precision":round(ap,4),"base_rate_test":round(float(yte.mean()),4),"selection":top,"importance":imp,"saved":str(out_path),"features":cols})
    (out_path.parent/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report
