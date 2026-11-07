"""VERIFICA: il banco di prova offline, senza look-ahead, per le regole
intra-minuto (SLANCIO e varianti). Nato da un'autocritica: SLANCIO e' stato
presentato come soluzione prima di essere misurato. Qui viene misurato.

Metodo (ogni scelta e' anti-ottimismo):
- features calcolate SOLO sulle barre fino all'istante t (conoscibili dal vivo);
- ingresso alla barra SUCCESSIVA (la latenza reale non compra al prezzo che
  ha fatto scattare la condizione), piu' variante stressata: prezzo +10%
  (slippage/latenza peggiore) e ingresso ritardato di 2 barre;
- split temporale 60/40: soglie fissate a priori (costanti di gem.py), la
  meta' recente e' conferma fuori campione, mai usata per tarare;
- controlli di onesta': la regola esplosivo60 (gia' morta a +60s) e un
  ingresso quasi-casuale devono risultare NON verificati, altrimenti il
  banco stesso e' rotto;
- mancano i flag di rischio live (engineered/distribution): la verifica e'
  quindi un limite superiore, dichiarato.

Verdetto: PROMETTENTE solo se nella meta' di conferma EV>0, positivi>=35%,
n>=30 anche sotto stress moderato. Altrimenti NON VERIFICATA.
"""
from __future__ import annotations
import statistics

from ..gem import (MAX_AGE_S, MAX_PEAK_RETRACE, MIN_AGE_S, MIN_BUYERS_15S,
                   MIN_RET_15S, MIN_RET_FROM_MIN)
from .analyze import CURVE_COST, simulate_plan
from .census import launch_summaries

LADDER = [(1.8, .25), (3.0, .25), (6.0, .25)]


def _features_at(bars, i):
    """Features conoscibili alla barra i (usa solo barre <= i)."""
    t = bars[i][0]
    mcaps = [b[4] for b in bars[:i + 1] if b[4] > 0]
    if not mcaps:
        return None
    ref15 = mcaps[0]
    for b in bars[:i + 1]:
        if b[0] <= t - 15 and b[4] > 0:
            ref15 = b[4]
    b15 = sum(b[3] for b in bars[:i + 1] if b[0] > t - 15)
    buy30 = sum(b[1] for b in bars[:i + 1] if b[0] > t - 30)
    sell30 = sum(b[2] for b in bars[:i + 1] if b[0] > t - 30)
    return {"age": t, "mcap": mcaps[-1], "min_mcap": min(mcaps), "peak_mcap": max(mcaps),
            "ret15": (mcaps[-1] / ref15 - 1) if ref15 > 0 else 0.0,
            "buyers15": b15, "bs30": buy30 / (sell30 + 0.05)}


def _is_slancio(f, strict=False):
    if f is None or not (MIN_AGE_S <= f["age"] <= MAX_AGE_S):
        return False
    ret_min = f["mcap"] / f["min_mcap"] - 1 if f["min_mcap"] > 0 else 0.0
    return (ret_min >= (0.40 if strict else MIN_RET_FROM_MIN)
            and f["mcap"] >= MAX_PEAK_RETRACE * f["peak_mcap"]
            and f["buyers15"] >= (8 if strict else MIN_BUYERS_15S)
            and f["bs30"] >= 1.3 and f["ret15"] >= MIN_RET_15S)


def _first_entry(bars, created, rule):
    """Primo istante in cui la regola e' conoscibile; ingresso alla barra dopo."""
    for i in range(len(bars) - 1):
        f = _features_at(bars, i)
        if f is None:
            continue
        f["age"] = bars[i][0] - created
        if rule(f, bars, i, created):
            return i + 1
    return None


RULES = {
    "slancio (live)": lambda f, b, i, c: _is_slancio(f),
    "slancio_strict": lambda f, b, i, c: _is_slancio(f, strict=True),
    "controllo_esplosivo60": lambda f, b, i, c: f["age"] >= 60 and f["min_mcap"] > 0
        and f["mcap"] / (b[0][4] or f["mcap"]) - 1 >= 0.50,
    "controllo_big60": lambda f, b, i, c: f["age"] >= 60
        and sum(x[1] for x in b[:i + 1] if x[0] <= c + 60) >= 20
        and sum(x[3] for x in b[:i + 1] if x[0] <= c + 60) >= 10,
    "controllo_base30": lambda f, b, i, c: f["age"] >= 30,
}


def _eval(rows, rule, delay_bars=1, haircut=1.0):
    nets = []
    for r in rows:
        bars = [(b[0], b[1], b[2], b[3], b[4]) for b in r["bars"] if b[4] > 0]
        if len(bars) < 4:
            continue
        ei = _first_entry(bars, r["created_at"], rule)
        if ei is None or ei + delay_bars - 1 >= len(bars):
            continue
        ei += delay_bars - 1
        entry = bars[ei][4] * haircut
        path = [(b[0], b[4]) for b in bars[ei:]]
        sim = simulate_plan(path, entry, LADDER, 1.8, 0.35, 0.65, CURVE_COST, None, path[0][0])
        if sim["net_mult"] is not None:
            nets.append(sim["net_mult"])
    if not nets:
        return {"n": 0, "ev_pct": None, "med_pct": None, "pos_share": None}
    return {"n": len(nets), "ev_pct": round((statistics.mean(nets) - 1) * 100, 1),
            "med_pct": round((statistics.median(nets) - 1) * 100, 1),
            "pos_share": round(sum(1 for x in nets if x > 1) / len(nets), 3)}


def verify(store, summaries=None) -> dict:
    rows = summaries if summaries is not None else launch_summaries(store)
    rows = sorted(rows, key=lambda r: r["created_at"])
    cut = int(len(rows) * 0.6)
    halves = {"train(60% vecchi)": rows[:cut], "test(40% recenti)": rows[cut:]}
    out = {"n_launches": len(rows), "rules": {}}
    for name, rule in RULES.items():
        cell = {}
        for hname, hrows in halves.items():
            cell[hname] = _eval(hrows, rule)
            cell[hname + "|stress"] = _eval(hrows, rule, delay_bars=2, haircut=1.10)
        test = cell["test(40% recenti)"]
        stress = cell["test(40% recenti)|stress"]
        ok = (test["ev_pct"] is not None and test["ev_pct"] > 0 and test["pos_share"] >= 0.35
              and test["n"] >= 30 and stress["ev_pct"] is not None and stress["ev_pct"] > 0)
        cell["verdict"] = "PROMETTENTE" if ok else "NON VERIFICATA"
        out["rules"][name] = cell
    return out


def _fmt(c):
    if not c or c.get("ev_pct") is None:
        return "n=0"
    return f"n={c['n']:<4} EV={c['ev_pct']:+.1f}% mediana={c['med_pct']:+.1f}% pos={c['pos_share']:.0%}"


def format_verify(v: dict) -> str:
    L = ["=== VERIFICA offline senza look-ahead (ingresso alla barra successiva) ===",
         f"  universo: {v['n_launches']} lanci · split temporale 60/40 · stress = +1 barra e prezzo +10%"]
    for name, cell in v["rules"].items():
        flag = "🟢 PROMETTENTE" if cell["verdict"] == "PROMETTENTE" else "⚫ NON VERIFICATA"
        L.append(f"{flag}  {name}")
        L.append(f"    train : {_fmt(cell['train(60% vecchi)'])}   | stress: {_fmt(cell['train(60% vecchi)|stress'])}")
        L.append(f"    test  : {_fmt(cell['test(40% recenti)'])}   | stress: {_fmt(cell['test(40% recenti)|stress'])}")
    L.append("  ! I controlli devono risultare NON VERIFICATI: se un controllo 'passa', il banco e' rotto.")
    L.append("  ! Mancano i flag di rischio live: questi numeri sono un limite superiore, non una promessa.")
    return "\n".join(L)
