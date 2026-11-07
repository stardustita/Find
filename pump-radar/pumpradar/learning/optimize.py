"""Fase 3 — ottimizzazione controfattuale di ingressi e uscite.

Sugli stessi percorsi reali registrati (vedi analyze.py) prova, per ogni segnale
storico, varianti di:
- INGRESSO: immediato | ritardato +30/60/120s | sul pullback -15%/-30% dal segnale
- USCITA: stop, scaletta, trailing (griglia dichiarata, non infinita)

Disciplina anti-overfitting: split temporale 60/40 sui segnali; una variante e'
candidata solo se EV positivo su ENTRAMBE le meta' con n sufficiente.
Include la "gara" stop-contro-target: chi arriva prima dopo l'ingresso immediato.
"""
from __future__ import annotations
from collections import defaultdict
from .analyze import CURVE_COST, AMM_COST, _path, simulate_plan

CURVE_LADDERS = {
    "standard(1.8/3/6)": [(1.8, .25), (3.0, .25), (6.0, .25)],
    "precoce(1.5/2.5/4)": [(1.5, .30), (2.5, .25), (4.0, .20)],
    "moon(2/5/10)": [(2.0, .20), (5.0, .20), (10.0, .20)],
}
PG_LADDERS = {
    "runner(2/5/15/50)": [(2.0, .20), (5.0, .20), (15.0, .20), (50.0, .15)],
    "precoce(1.6/3/6)": [(1.6, .30), (3.0, .25), (6.0, .20)],
    "moon(3/8/25)": [(3.0, .20), (8.0, .20), (25.0, .20)],
}
STOPS = [0.70, 0.58, 0.45, 0.30]                    # multiplo di stop (1 = ingresso)
TRAILS = [(1.5, 0.30), (1.8, 0.35), (2.5, 0.45)]    # (attivazione, drop dal picco)


def _entries(path, sig_ts, sig_mcap):
    yield "immediato", path, sig_mcap
    for d in (30, 60, 120):
        sub = [p for p in path if p[0] >= sig_ts + d]
        if len(sub) >= 2: yield f"ritardo+{d}s", sub, sub[0][1]
    for pb in (0.15, 0.30):
        idx = next((i for i, p in enumerate(path) if p[0] <= sig_ts + 300 and p[1] <= sig_mcap * (1 - pb)), None)
        if idx is not None and len(path) - idx >= 2:
            yield f"pullback-{int(pb*100)}%", path[idx:], path[idx][1]


def _load(store, kind):
    if kind == "curve":
        rows = store.q("SELECT mint x, ts, mcap_sol FROM signals WHERE mcap_sol>0 ORDER BY ts")
        table, key = "trades", "mint"
    else:
        rows = store.q("SELECT pool x, ts, mcap_sol FROM pg_signals WHERE mcap_sol>0 ORDER BY ts")
        table, key = "amm_trades", "pool"
    out = []
    for r in rows:
        path = _path(store, table, key, r["x"], float(r["ts"]))
        if len(path) >= 2:
            out.append((float(r["ts"]), float(r["mcap_sol"]), path))
    return out


def race_stats(signals):
    """Ingresso immediato: chi arriva prima, stop (-35%) o target (1.8x)?"""
    res = defaultdict(int)
    for sig_ts, sig_mcap, path in signals:
        outcome = "nessuno"
        for ts, m in path:
            mult = m / sig_mcap
            if mult >= 1.8: outcome = "target_prima"; break
            if mult <= 0.65: outcome = "stop_prima"; break
        res[outcome] += 1
    return dict(res)


def optimize(store, kind="curve", top_n=12):
    signals = _load(store, kind)
    ladders = CURVE_LADDERS if kind == "curve" else PG_LADDERS
    cost = CURVE_COST if kind == "curve" else AMM_COST
    cut = int(len(signals) * 0.6)
    results = []
    entry_names = ["immediato", "ritardo+30s", "ritardo+60s", "ritardo+120s", "pullback-15%", "pullback-30%"]
    for ename in entry_names:
        for lname, ladder in ladders.items():
            for stop in STOPS:
                for tfrom, tdrop in TRAILS:
                    nets_tr, nets_te = [], []
                    for i, (sig_ts, sig_mcap, path) in enumerate(signals):
                        for name, sub, emcap in _entries(path, sig_ts, sig_mcap):
                            if name != ename: continue
                            sim = simulate_plan(sub, emcap, ladder, tfrom, tdrop, stop, cost, 780 if kind == "curve" else None, sub[0][0])
                            if sim["net_mult"] is not None:
                                (nets_tr if i < cut else nets_te).append(sim["net_mult"])
                    if len(nets_tr) >= 15 and len(nets_te) >= 10:
                        ev_tr = (sum(nets_tr) / len(nets_tr) - 1) * 100
                        ev_te = (sum(nets_te) / len(nets_te) - 1) * 100
                        results.append({"entry": ename, "ladder": lname, "stop": stop,
                                        "trail": f"{tfrom}x/-{int(tdrop*100)}%",
                                        "n_train": len(nets_tr), "n_test": len(nets_te),
                                        "ev_train": round(ev_tr, 1), "ev_test": round(ev_te, 1),
                                        "pos_test": round(sum(1 for x in nets_te if x > 1) / len(nets_te), 2)})
    results.sort(key=lambda r: (min(r["ev_train"], r["ev_test"]), r["ev_test"]), reverse=True)
    return {"kind": kind, "n_signals": len(signals), "race": race_stats(signals) if kind == "curve" else {},
            "candidates": [r for r in results if r["ev_train"] > 0 and r["ev_test"] > 0][:top_n],
            "top_by_test": results[:top_n]}


def format_optimize(d: dict) -> str:
    L = [f"=== Ottimizzazione controfattuale ({d['kind']}) — segnali con percorso: {d['n_signals']} ==="]
    if d.get("race"):
        r = d["race"]; tot = max(1, sum(r.values()))
        L.append("Gara dopo ingresso immediato (stop -35% vs target 1.8x): " +
                 " · ".join(f"{k}={v} ({v/tot:.0%})" for k, v in sorted(r.items())))
    L.append("--- Varianti con EV positivo su train E test (candidate, da confermare in ombra) ---")
    if d["candidates"]:
        for r in d["candidates"]:
            L.append(f"  {r['entry']:<13} {r['ladder']:<18} stop={r['stop']:.2f} trail={r['trail']:<9} EV train {r['ev_train']:+.1f}% · test {r['ev_test']:+.1f}% (n={r['n_test']}, positivi {r['pos_test']:.0%})")
    else:
        L.append("  nessuna: ogni variante perde su almeno una meta'. Il piano attuale non si salva con la taratura.")
    L.append("--- Migliori per EV test (anche se train negativo: NON candidate) ---")
    for r in d["top_by_test"][:6]:
        L.append(f"  {r['entry']:<13} {r['ladder']:<18} stop={r['stop']:.2f} trail={r['trail']:<9} EV train {r['ev_train']:+.1f}% · test {r['ev_test']:+.1f}% (n={r['n_test']})")
    L.append("  ! Griglia su dati storici: anche le 'candidate' richiedono conferma in ombra su dati nuovi.")
    return "\n".join(L)
