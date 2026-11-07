"""Motore GEMME (ricostruzione dello strato segnali): alert in tempo reale
PRIMA dell'esplosione, costruito solo su cio' che i dati non hanno falsificato.

Lezione dei 6.429 lanci censiti: l'esplosione del primo minuto predice il picco
(p(2x) 70,7% vs 13,7%), ma a +60s — primo istante in cui la forma completa e'
conoscibile — il prezzo la incorpora gia' (griglia onesta: 7/7 celle negative).
L'unica geometria mai testata e' entrare DURANTE la formazione del pattern,
con informazione parziale ma disponibile in quell'istante (nessun look-ahead
per costruzione): a 18-90s di vita, +25% dal minimo, compratori in espansione
negli ultimi 15s, momentum ancora in accelerazione, non gia' ritracciato.

Disciplina invariata: il segnale SLANCIO e' paper (posizioni simulate e alert),
passa dal Censore come ogni emissione operativa, viene registrato nella
tabella signals (quindi analyze lo giudica con EV eseguibile e il Revisore lo
retrocede da solo se gli ultimi 100 risolti hanno EV<0, n>=50). Ogni alert
porta con se' i tassi base del pattern: nessuna falsa precisione.
"""
from __future__ import annotations

# Tassi base del pattern madre (censimento reale, forma esplosiva 60s):
PATTERN_BASE = {"p2x": 0.707, "p5x": 0.22, "grad": 0.015, "note": "forma esplosiva 60s, universo p2x=13.7%"}

MIN_AGE_S, MAX_AGE_S = 18, 90
MIN_RET_FROM_MIN = 0.25        # +25% dal minimo di nascita
MIN_BUYERS_15S = 5             # ondata fresca, non un wallet solo
MIN_RET_15S = 0.03             # ancora in accelerazione
MAX_PEAK_RETRACE = 0.85        # se ha gia' perso >15% dal picco, e' tardi


def _ret_window(st, now, seconds):
    """Rendimento del prezzo negli ultimi `seconds` dai trade registrati."""
    pts = [(float(t.get("ts") or 0), float(t.get("mcap_sol") or 0)) for t in st.trades
           if t.get("mcap_sol")]
    if len(pts) < 2:
        return 0.0
    last_ts, last_m = pts[-1]
    ref = pts[0][1]
    for ts, m in pts:
        if ts <= now - seconds:
            ref = m
        else:
            break
    return (last_m / ref - 1) if ref > 0 else 0.0


def slancio_signal(st, F: dict, now: float) -> dict | None:
    """Momentum intra-minuto conoscibile all'ingresso. None = niente segnale."""
    if getattr(st, "lane", "") != "sol":
        return None
    age = float(F.get("age_s", 0) or 0)
    mcap = float(F.get("mcap_sol", 0) or 0)
    if not (MIN_AGE_S <= age <= MAX_AGE_S and mcap > 0):
        return None
    base = float(getattr(st, "min_mcap", 0) or 0)
    peak = float(getattr(st, "peak_mcap", 0) or 0)
    if base <= 0 or peak <= 0:
        return None
    ret_min = mcap / base - 1
    if ret_min < MIN_RET_FROM_MIN:
        return None                       # non sta ancora esplodendo
    if mcap < MAX_PEAK_RETRACE * peak:
        return None                       # esplosione gia' in ritirata
    buyers15 = {t.get("trader") for t in st.window(15, now) if t.get("is_buy") and t.get("trader")}
    if len(buyers15) < MIN_BUYERS_15S:
        return None                       # ondata non confermata da wallet distinti
    if float(F.get("buy_sell_ratio_30s", 0) or 0) < 1.3:
        return None                       # pressione in acquisto non dominante
    ret15 = _ret_window(st, now, 15)
    if ret15 < MIN_RET_15S:
        return None                       # momentum gia' piatto: sarebbe inseguire
    if float(F.get("risk_engineered", 0) or 0) >= 0.5 or float(F.get("risk_distribution", 0) or 0) >= 0.5:
        return None
    return {"ret_from_min": round(ret_min, 3), "ret_15s": round(ret15, 3),
            "buyers_15s": len(buyers15), "age_s": round(age),
            "pattern_base_p2x": PATTERN_BASE["p2x"]}
