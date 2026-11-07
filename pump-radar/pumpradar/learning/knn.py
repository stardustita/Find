"""Fase 4 — ORACOLO PER ANALOGIA: gemelli storici del percorso.

I primi 6 minuti di un lancio, a barre da 30s, sono un'impronta: andamento del
prezzo, flusso di acquisto cumulato, compratori cumulati (forme normalizzate,
36 numeri). Per un token vivo troviamo i k lanci storici piu' simili — solo
lanci INIZIATI almeno un'ora prima (niente leakage dal futuro) — e restituiamo
la DISTRIBUZIONE dei loro esiti: tasso di graduation, picco mediano, p(2x),
p(5x). Non un punteggio profetico: un "di 25 gemelli, ecco com'e' andata".

Uso onesto: strumento di lettura e sorgente di ipotesi per la Fabbrica.
Mai un segnale operativo senza passaggio in ombra.
"""
from __future__ import annotations
import math
import statistics

from .census import launch_summaries

SLICES, SLICE_S = 12, 30          # 12 x 30s = primi 6 minuti
MIN_AGE_GAP_S = 3600              # i gemelli devono essere risolti e precedenti


def _fingerprint(summary):
    bars, t0, first = summary["bars"], summary["created_at"], summary["first_mcap"]
    if not bars or not first:
        return None
    total_buy = sum(b[1] for b in bars) or 1e-9
    total_buyers = sum(b[3] for b in bars) or 1e-9
    vec, cum_buy, cum_b, last_mult = [], 0.0, 0, 1.0
    for i in range(SLICES):
        lo, hi = t0 + i * SLICE_S, t0 + (i + 1) * SLICE_S
        for b in bars:
            if lo <= b[0] < hi:
                cum_buy += b[1]; cum_b += b[3]
                if b[4] > 0:
                    last_mult = b[4] / first
            elif b[0] < lo:
                cum_buy += 0.0
        vec += [last_mult, cum_buy / total_buy, cum_b / total_buyers]
    if summary["lifespan_s"] < SLICES * SLICE_S * 0.8:
        return None               # impronta incompleta: percorso troppo breve
    return vec


def _index(summaries):
    fps = {}
    for s in summaries:
        fp = _fingerprint(s)
        if fp:
            fps[s["mint"]] = (s, fp)
    if not fps:
        return fps, [], []
    dims = len(next(iter(fps.values()))[1])
    means = [statistics.mean(v[1][d] for v in fps.values()) for d in range(dims)]
    stds = [statistics.pstdev([v[1][d] for v in fps.values()]) or 1.0 for d in range(dims)]
    return fps, means, stds


def twins_from_index(fps, means, stds, mint, k=25):
    """Gemelli da un indice gia' costruito (l'Orchestrator lo tiene in cache)."""
    if mint not in fps:
        return {"error": "impronta non disponibile (servono ~6 min di barre e un token noto)"}
    tgt, tfp = fps[mint]
    scored = []
    for m, (s, fp) in fps.items():
        if m == mint or s["created_at"] > tgt["created_at"] - MIN_AGE_GAP_S:
            continue
        d = math.sqrt(sum(((a - b) / sd) ** 2 for a, b, sd in zip(fp, tfp, stds)))
        scored.append((d, s))
    scored.sort(key=lambda x: x[0])
    twins = scored[:k]
    if not twins:
        return {"error": "nessun gemello storico abbastanza vecchio"}
    ts = [s for _, s in twins]
    return {
        "mint": mint, "k": len(twins),
        "grad_rate": round(sum(1 for s in ts if s["graduated"]) / len(ts), 3),
        "p2x": round(sum(1 for s in ts if s["peak_mult"] >= 2) / len(ts), 3),
        "p5x": round(sum(1 for s in ts if s["peak_mult"] >= 5) / len(ts), 3),
        "med_peak": round(statistics.median(s["peak_mult"] for s in ts), 2),
        "med_last": round(statistics.median(s["last_mult"] for s in ts), 2),
        "twins": [{"mint": s["mint"], "dist": round(d, 2), "peak_mult": round(s["peak_mult"], 2),
                   "graduated": s["graduated"]} for d, s in twins],
    }


def find_twins(store, mint, k=25, summaries=None):
    rows = summaries if summaries is not None else launch_summaries(store)
    fps, means, stds = _index(rows)
    return twins_from_index(fps, means, stds, mint, k)


def format_twins(t: dict) -> str:
    if "error" in t:
        return f"ORACOLO: {t['error']}"
    L = [f"=== ORACOLO PER ANALOGIA: {t['k']} gemelli storici di {t['mint'][:12]}… ===",
         f"  esiti dei gemelli: graduation={t['grad_rate']:.0%}  p(2x)={t['p2x']:.0%}  p(5x)={t['p5x']:.0%}  "
         f"picco mediano={t['med_peak']:.2f}x  esito finale mediano={t['med_last']:.2f}x",
         "--- gemelli piu' vicini ---"]
    for w in t["twins"][:10]:
        L.append(f"  {w['mint'][:12]}… dist={w['dist']:.2f} picco={w['peak_mult']:.2f}x {'GRADUATO' if w['graduated'] else ''}")
    L.append("  ! Distribuzione storica, non previsione: i gemelli dicono il meteo di quel sentiero, non il destino.")
    return "\n".join(L)
