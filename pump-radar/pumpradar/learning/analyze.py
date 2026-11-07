"""Fase 0 — archeologia sui segnali storici.

Domande a cui risponde, sui dati REALI registrati nel DB:
1. Per tier, i segnali hanno EV eseguibile positivo? (simulazione del piano di
   uscita sul percorso reale dei trade, NON il picco teorico del backtest)
2. Dentro i WATCH, quale sottogruppo contiene i vincitori? (gate fallito,
   progresso curva al segnale, fascia di score, eta', market cap)
3. Lo score e' monotono rispetto agli esiti o e' invertito? (quintili di score)
4. Stesse misure per i segnali post-graduation (trade AMM).

Convenzioni: entry = market cap registrato al momento del segnale; il percorso
e' la serie dei market cap dei trade successivi (persistiti solo per i token
tracciati: e' il limite noto del dataset, dichiarato nel report).
Costi: curva 17% round-trip, AMM 15.6% (stesse ipotesi di exit/runner).
"""
from __future__ import annotations
import json
import statistics
from collections import defaultdict

CURVE_COST = 0.17
AMM_COST = 0.156
HORIZON_S = 86400.0


def _path(store, table, key_col, key_val, ts0, mcap_col="mcap_sol"):
    rows = store.q(
        f"SELECT ts,{mcap_col} m FROM {table} WHERE {key_col}=? AND ts>=? AND ts<=? AND {mcap_col}>0 ORDER BY ts",
        (key_val, ts0, ts0 + HORIZON_S))
    return [(float(r["ts"]), float(r["m"])) for r in rows if r["m"]]


def simulate_plan(path, entry_mcap, ladder, trail_from, trail_drop, stop_mult,
                  cost, time_stop_s=None, entry_ts=None):
    """Simula il piano di uscita sul percorso. Ritorna multiplo netto del capitale
    (1.0 = pareggio) e motivo di chiusura. Riempimenti ai prezzi dei trade
    registrati: approssimazione dichiarata, niente fill 'al picco'."""
    if not path or not entry_mcap:
        return {"net_mult": None, "reason": "no_path", "peak_mult": 0.0}
    sold = 0.0
    pnl = 0.0            # in unita' di multiplo sul capitale investito
    peak = 1.0
    last_mult = 1.0
    li = 0
    reason = "horizon"
    t0 = entry_ts if entry_ts is not None else path[0][0]
    for ts, mcap in path:
        mult = mcap / entry_mcap
        last_mult = mult
        peak = max(peak, mult)
        if mult <= stop_mult:
            pnl += (1 - sold) * (mult - 1 - cost); sold = 1.0; reason = "stop"; break
        while li < len(ladder) and mult >= ladder[li][0]:
            pnl += ladder[li][1] * (ladder[li][0] - 1 - cost); sold += ladder[li][1]; li += 1
        if peak >= trail_from and mult <= peak * (1 - trail_drop):
            pnl += (1 - sold) * (mult - 1 - cost); sold = 1.0; reason = "trailing"; break
        if time_stop_s and ts - t0 > time_stop_s and mult < 1.2:
            pnl += (1 - sold) * (mult - 1 - cost); sold = 1.0; reason = "time_stop"; break
    if sold < 1.0:
        pnl += (1 - sold) * (last_mult - 1 - cost)
    return {"net_mult": 1.0 + pnl, "reason": reason, "peak_mult": peak}


def curve_signal_facts(store):
    """Un fatto per segnale curva: esiti grezzi + EV eseguibile del piano."""
    facts = []
    for r in store.q("SELECT * FROM signals WHERE mcap_sol>0 ORDER BY ts"):
        path = _path(store, "trades", "mint", r["mint"], float(r["ts"]))
        if not path:
            continue
        entry = float(r["mcap_sol"])
        p15 = max((m for ts, m in path if ts - float(r["ts"]) <= 900), default=0.0) / entry
        sim = simulate_plan(path, entry, [(1.8, .25), (3.0, .25), (6.0, .25)],
                            trail_from=1.8, trail_drop=0.35, stop_mult=0.65,
                            cost=CURVE_COST, time_stop_s=780, entry_ts=float(r["ts"]))
        try: gates = json.loads(r["gates"] or "{}")
        except Exception: gates = {}
        try: feats = json.loads(r["features"] or "{}")
        except Exception: feats = {}
        facts.append({
            "tier": r["tier"], "score": float(r["score"] or 0), "ts": float(r["ts"]),
            "mcap": entry, "age_s": float(r["age_s"] or 0),
            "progress": float(feats.get("curve_progress", 0) or 0),
            "failed_gates": sorted(k for k, v in gates.items() if not v),
            "peak15": p15, "peak24": sim["peak_mult"],
            "net_mult": sim["net_mult"], "exit_reason": sim["reason"],
        })
    return facts


def pg_signal_facts(store):
    facts = []
    for r in store.q("SELECT * FROM pg_signals WHERE mcap_sol>0 ORDER BY ts"):
        path = _path(store, "amm_trades", "pool", r["pool"], float(r["ts"]))
        if not path:
            continue
        entry = float(r["mcap_sol"])
        sim = simulate_plan(path, entry, [(2.0, .20), (5.0, .20), (15.0, .20), (50.0, .15)],
                            trail_from=2.0, trail_drop=0.35, stop_mult=0.55,
                            cost=AMM_COST, entry_ts=float(r["ts"]))
        facts.append({"tier": r["tier"], "score": float(r["score"] or 0),
                      "mcap": entry, "peak24": sim["peak_mult"],
                      "net_mult": sim["net_mult"], "exit_reason": sim["reason"]})
    return facts


def shadow_facts(store):
    """EV eseguibile dei segnali OMBRA (Fase 2): stessa metrica dei segnali veri,
    cosi' il confronto e' onesto. Le strategie ombra non aprono mai posizioni."""
    by = {}
    for r in store.q("SELECT * FROM shadow_signals ORDER BY ts"):
        entry = float(r["entry_mcap"] or 0)
        if not entry: continue
        if r["kind"] == "curve":
            path = _path(store, "trades", "mint", r["mint"], float(r["ts"]))
            sim = simulate_plan(path, entry, [(1.8, .25), (3.0, .25), (6.0, .25)], 1.8, 0.35, 0.65, CURVE_COST, 780, float(r["ts"]))
        else:
            path = _path(store, "amm_trades", "pool", r["pool"], float(r["ts"]))
            sim = simulate_plan(path, entry, [(2.0, .20), (5.0, .20), (15.0, .20), (50.0, .15)], 2.0, 0.35, 0.55, AMM_COST, None, float(r["ts"]))
        if sim["net_mult"] is None: continue
        p15 = max((m for ts, m in path if ts - float(r["ts"]) <= 900), default=0.0) / entry
        by.setdefault(r["strategy"], []).append({"peak15": p15, "peak24": sim["peak_mult"], "net_mult": sim["net_mult"]})
    return {k: _agg(v) for k, v in sorted(by.items())}


def _agg(facts):
    n = len(facts)
    if not n:
        return {"n": 0}
    nets = [f["net_mult"] for f in facts if f["net_mult"] is not None]
    return {
        "n": n,
        "hit1.8_15m": round(sum(1 for f in facts if f["peak15"] >= 1.8) / n, 3) if "peak15" in facts[0] else None,
        "hit2x_24h": round(sum(1 for f in facts if f["peak24"] >= 2.0) / n, 3),
        "hit10x_24h": round(sum(1 for f in facts if f["peak24"] >= 10.0) / n, 3),
        "avg_peak15": round(sum(f.get("peak15", 0) for f in facts) / n, 2) if "peak15" in facts[0] else None,
        "avg_net_mult": round(sum(nets) / len(nets), 3) if nets else None,
        "ev_pct": round((sum(nets) / len(nets) - 1) * 100, 1) if nets else None,
        # Mediana del netto: la media su code pesanti e' dominata da 1-2 moonshot
        # (es. un tier a EV +1187% con 56% di trade in perdita). La mediana dice
        # com'e' andato il trade TIPICO, ed e' il primo smascheratore di miraggi.
        "med_net_mult": round(statistics.median(nets), 3) if nets else None,
        "pos_share": round(sum(1 for x in nets if x > 1) / len(nets), 3) if nets else None,
    }


def _bucket(value, edges):
    for i, e in enumerate(edges):
        if value < e:
            return i
    return len(edges)


def analyze(store) -> dict:
    out = {"curve": {}, "pg": {}, "notes": [
        "EV eseguibile: piano simulato sui trade registrati, costi inclusi; i fill reali possono essere peggiori.",
        "Percorsi solo per token tracciati (watch/posizioni): survivorship noto del dataset.",
    ]}
    facts = curve_signal_facts(store)
    by_tier = defaultdict(list)
    for f in facts: by_tier[f["tier"]].append(f)
    out["curve"]["by_tier"] = {t: _agg(v) for t, v in sorted(by_tier.items())}

    # quintili di score: lo score ordina davvero gli esiti?
    sf = sorted(facts, key=lambda f: f["score"])
    quintiles = []
    if len(sf) >= 10:
        step = len(sf) / 5
        for i in range(5):
            part = sf[int(i * step):int((i + 1) * step)] or sf[-1:]
            a = _agg(part)
            a["score_range"] = [round(part[0]["score"], 3), round(part[-1]["score"], 3)]
            quintiles.append(a)
    out["curve"]["score_quintiles"] = quintiles

    # dissezione WATCH: gate fallito / progresso / score / eta' / mcap
    watch = by_tier.get("WATCH", [])
    dis = {}
    by_gate = defaultdict(list)
    for f in watch:
        for g in f["failed_gates"]: by_gate[g].append(f)
        if not f["failed_gates"]: by_gate["(nessuno: score)"].append(f)
    dis["by_failed_gate"] = {g: _agg(v) for g, v in sorted(by_gate.items(), key=lambda kv: -len(kv[1]))}
    prog_edges = [0.30, 0.50, 0.72, 0.90]
    prog_labels = ["<0.30", "0.30-0.50", "0.50-0.72", "0.72-0.90", ">0.90"]
    bp = defaultdict(list)
    for f in watch: bp[prog_labels[_bucket(f["progress"], prog_edges)]].append(f)
    dis["by_progress"] = {k: _agg(bp[k]) for k in prog_labels if bp[k]}
    bs = defaultdict(list)
    for f in watch:
        band = "<0.34" if f["score"] < 0.34 else "0.34-0.44" if f["score"] < 0.44 else "0.44-0.54" if f["score"] < 0.54 else ">=0.54"
        bs[band].append(f)
    dis["by_score_band"] = {k: _agg(v) for k, v in bs.items()}
    bm = defaultdict(list)
    for f in watch:
        band = "<50" if f["mcap"] < 50 else "50-150" if f["mcap"] < 150 else "150-300" if f["mcap"] < 300 else ">=300"
        bm[band].append(f)
    dis["by_entry_mcap"] = {k: _agg(v) for k, v in bm.items()}
    out["curve"]["watch_dissection"] = dis

    pg = pg_signal_facts(store)
    by_tier_pg = defaultdict(list)
    for f in pg: by_tier_pg[f["tier"]].append(f)
    out["pg"]["by_tier"] = {t: _agg(v) for t, v in sorted(by_tier_pg.items())}
    reasons = defaultdict(lambda: [0, 0.0])
    for f in facts:
        if f["net_mult"] is not None:
            reasons[f["exit_reason"]][0] += 1; reasons[f["exit_reason"]][1] += f["net_mult"] - 1
    out["curve"]["exit_reasons"] = {k: {"n": v[0], "avg_net_pct": round(v[1] / v[0] * 100, 1)} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1][0])}
    try: out["shadow"] = shadow_facts(store)
    except Exception: out["shadow"] = {}
    out["n_curve_signals"] = len(facts); out["n_pg_signals"] = len(pg)
    return out


def _fmt_agg(a):
    if not a or not a.get("n"): return "n=0"
    parts = [f"n={a['n']}"]
    if a.get("hit1.8_15m") is not None: parts.append(f"hit1.8={a['hit1.8_15m']:.0%}")
    parts.append(f"hit2x={a['hit2x_24h']:.0%} hit10x={a['hit10x_24h']:.0%}")
    if a.get("avg_peak15") is not None: parts.append(f"picco15={a['avg_peak15']:.2f}x")
    parts.append(f"EVnetto={a['ev_pct']:+.1f}% positivi={a['pos_share']:.0%}")
    if a.get("med_net_mult") is not None: parts.append(f"mediana={(a['med_net_mult'] - 1) * 100:+.1f}%")
    return "  ".join(parts)


def format_report(d: dict) -> str:
    L = ["=== FASE 0: EV eseguibile per tier (curva) ==="]
    for t, a in d["curve"].get("by_tier", {}).items(): L.append(f"  {t:<8} {_fmt_agg(a)}")
    L.append("=== Quintili di score (curva): Q1 score basso -> Q5 score alto ===")
    for i, a in enumerate(d["curve"].get("score_quintiles", []), 1):
        L.append(f"  Q{i} {a.get('score_range')}  {_fmt_agg(a)}")
    dis = d["curve"].get("watch_dissection", {})
    for sec, title in (("by_failed_gate", "WATCH per gate fallito"), ("by_progress", "WATCH per progresso curva"),
                       ("by_score_band", "WATCH per fascia di score"), ("by_entry_mcap", "WATCH per mcap ingresso (SOL)")):
        L.append(f"=== {title} ===")
        for k, a in dis.get(sec, {}).items(): L.append(f"  {k:<28} {_fmt_agg(a)}")
    L.append("=== Motivi di uscita simulati (curva) ===")
    for k, v in d["curve"].get("exit_reasons", {}).items(): L.append(f"  {k:<12} n={v['n']:<4} netto medio {v['avg_net_pct']:+.1f}%")
    if d.get("shadow"):
        L.append("=== Strategie OMBRA (mai operative finche' non promosse) ===")
        for k, a in d["shadow"].items(): L.append(f"  {k:<14} {_fmt_agg(a)}")
    L.append("=== Post-graduation: EV eseguibile per tier ===")
    for t, a in d["pg"].get("by_tier", {}).items(): L.append(f"  {t:<8} {_fmt_agg(a)}")
    L.append(f"(segnali analizzati: curva={d.get('n_curve_signals',0)} post-grad={d.get('n_pg_signals',0)})")
    for n in d.get("notes", []): L.append(f"  ! {n}")
    return "\n".join(L)
