"""Fase 4 — FABBRICA DI IPOTESI: il censimento propone, i percorsi giudicano.

Flusso: (1) census trova coorti anomale (z>=3, correzione implicita per
confronti multipli: con ~100 celle testate, z>=3 lascia ~0.1 falsi positivi
attesi); (2) ogni anomalia diventa una REGOLA pre-registrata; (3) la regola
viene valutata con EV eseguibile simulato sui percorsi a barre di TUTTI i
lanci della coorte (ingresso a +60s, ladder curva standard, costi inclusi) e
confrontata con la baseline dell'intero universo; (4) verdetto scritto nel
registro immutabile `hypotheses`: CANDIDATE (merita un detector ombra) o DEAD.

Nessuna regola diventa operativa qui: CANDIDATE e' un invito a costruire il
detector e a confermare in ombra su dati nuovi, come da disciplina Fase 2.
"""
from __future__ import annotations
import statistics

from .analyze import CURVE_COST, simulate_plan
from .census import DIMENSIONS, census, launch_summaries

LADDER = [(1.8, .25), (3.0, .25), (6.0, .25)]
# Ingresso stilizzato a +15s: abbastanza presto da includere anche i lanci morti
# in un minuto. A +60s i morti istantanei sparirebbero dalla valutazione e la
# fabbrica erediterebbe survivorship bias al suo interno (baseline gonfiata).
ENTRY_DELAY_S = 15


def _members(summaries, dimension, key):
    if dimension == "creator_seriali":
        return [r for r in summaries if r["creator"] == key]
    fn = DIMENSIONS[dimension]
    return [r for r in summaries if fn(r) == key]


def _ev_of(rows):
    nets = []
    for r in rows:
        path = [(ts, m) for ts, m in r["path"] if ts >= r["created_at"] + ENTRY_DELAY_S]
        if len(path) < 2:
            continue
        sim = simulate_plan(path, path[0][1], LADDER, 1.8, 0.35, 0.65, CURVE_COST, None, path[0][0])
        if sim["net_mult"] is not None:
            nets.append(sim["net_mult"])
    if not nets:
        return {"n": 0, "ev_pct": None, "med_pct": None, "pos_share": None}
    return {"n": len(nets),
            "ev_pct": round((statistics.mean(nets) - 1) * 100, 1),
            "med_pct": round((statistics.median(nets) - 1) * 100, 1),
            "pos_share": round(sum(1 for x in nets if x > 1) / len(nets), 3)}


def run_factory(store, min_n=150, zmin=3.0, persist=True) -> dict:
    summaries = launch_summaries(store)
    c = census(store, summaries)
    base = _ev_of(summaries)
    registered = {r["rule_key"] for r in store.list_hypotheses(500)}
    rows = []
    for a in c["anomalies"]:
        if a["n"] < min_n or a["z"] < zmin:
            continue
        ev = _ev_of(_members(summaries, a["dimension"], a["key"]))
        verdict = "DEAD"
        if (ev["n"] >= 100 and ev["ev_pct"] is not None and ev["ev_pct"] > 0
                and ev["pos_share"] >= 0.35 and base["ev_pct"] is not None
                and ev["ev_pct"] >= base["ev_pct"] + 5):
            verdict = "CANDIDATE"
        key = f"{a['dimension']}:{a['key']}"
        row = {"rule_key": key, "dimension": a["dimension"], "cohort": a["key"],
               "metric": a["metric"], "z": a["z"], **ev, "baseline_ev_pct": base["ev_pct"],
               "verdict": verdict, "already": key in registered}
        if persist and not row["already"] and ev["n"]:
            store.add_hypothesis(key, a["dimension"], a["key"], ev["n"], ev["ev_pct"], ev["med_pct"],
                                 ev["pos_share"], base["ev_pct"], a["z"], verdict,
                                 f"anomalia {a['metric']}={a['value']:.3f} vs base {a['baseline']:.3f}")
        rows.append(row)
    rows.sort(key=lambda r: -(r["ev_pct"] or -999))
    return {"baseline": base, "rows": rows, "n_launches": len(summaries)}


def format_factory(f: dict) -> str:
    b = f["baseline"]
    L = ["=== FABBRICA DI IPOTESI: anomalie del censimento giudicate sui percorsi ===",
         f"  baseline universo (ingresso +15s, ladder curva): n={b['n']} EV={b['ev_pct']}% mediana={b['med_pct']}% positivi={b['pos_share']}",
         f"  lanci nel censimento: {f['n_launches']}"]
    if not f["rows"]:
        L.append("  nessuna anomalia sopra soglia: la fabbrica non ha materia prima (ancora).")
    for r in f["rows"]:
        flag = "🟢 CANDIDATE" if r["verdict"] == "CANDIDATE" else "⚫ DEAD"
        reg = " (gia' nel registro)" if r["already"] else ""
        L.append(f"  {flag}  {r['rule_key']:<42} n={r['n']:<5} EV={r['ev_pct']}%  mediana={r['med_pct']}%  pos={r['pos_share']}  z={r['z']}{reg}")
    L.append("  ! CANDIDATE = merita un detector ombra e conferma su dati nuovi. Mai operativa direttamente.")
    return "\n".join(L)
