"""Strategie ombra (Fase 2): registrate e giudicate con EV eseguibile,
mai posizioni finché non promosse con criteri pre-registrati.

Ipotesi, nate dai dati reali (Fase 0/3): l'ingresso sul momentum in curva perde
(gara stop-vs-target 56% vs 18%); le geometrie candidate sono post-selezione:

1. second_leg (curva): il token ha gia' pompato >=2x dal minimo, e' crollato del
   45-75% dal picco SENZA morire, e una nuova ondata di compratori unici sta
   tornando con prezzo in recupero. Gli sniper sono usciti: resta chi ci crede.
2. pg_pullback (post-graduation): pool salito >=1.8x dal prezzo iniziale, ritraccia
   del 25-55% dal picco con liquidita' intatta e compratori di ritorno (+ret 1m).

3. esplosivo60 (curva): prima CANDIDATE della Fabbrica di Ipotesi (censimento
   reale, 6.351 lanci): +50% nei primi 60s dal minimo di nascita -> p(2x) 70,7%
   contro 13,7% dell'universo. La valutazione storica entrava a +15s conoscendo
   la forma a +60s (look-ahead): dal vivo il segnale scatta A +60s e l'ingresso
   registrato e' il prezzo di quel momento. L'ombra dira' quanto EV sopravvive.

I rilevatori sono funzioni pure su state/feature: l'orchestratore le invoca,
registra il segnale in shadow_signals e NON apre posizioni.
"""
from __future__ import annotations


def second_leg_signal(st, F: dict, now: float) -> dict | None:
    if getattr(st, "lane", "") != "sol":
        return None
    age = float(F.get("age_s", 0) or 0)
    mcap = float(F.get("mcap_sol", 0) or 0)
    if not (240 <= age <= 3600 and mcap > 0):
        return None
    peak = float(getattr(st, "peak_mcap", 0) or 0)
    base = float(getattr(st, "min_mcap", 0) or 0)
    if peak <= 0 or base <= 0 or peak < 2.0 * base:
        return None                       # deve aver gia' avuto la sua prima gamba
    drawdown = 1 - mcap / peak
    if not (0.45 <= drawdown <= 0.78):
        return None                       # crollato abbastanza ma non morto
    buyers60 = {t.get("trader") for t in st.window(60, now) if t.get("is_buy") and t.get("trader")}
    if len(buyers60) < 8:
        return None                       # seconda ondata: compratori unici, non uno solo
    if float(F.get("buy_sell_ratio_30s", 0) or 0) < 1.4:
        return None
    if float(F.get("mcap_ret_60s", 0) or 0) < 0.04:
        return None                       # prezzo in recupero, non ancora in caduta
    if float(F.get("risk_engineered", 0) or 0) >= 0.5 or float(F.get("risk_distribution", 0) or 0) >= 0.5:
        return None
    return {"peak_mcap": round(peak, 1), "drawdown": round(drawdown, 3),
            "buyers_60s": len(buyers60), "age_s": round(age)}


def pg_pullback_signal(gs, F: dict, now: float) -> dict | None:
    age = float(F.get("pg_age_s", 0) or 0)
    if not (240 <= age <= 10800):
        return None
    ath = float(F.get("pg_ath_mult", 0) or 0)
    dd = float(F.get("pg_drawdown_ath", 0) or 0)
    if ath < 1.8 or not (0.25 <= dd <= 0.55):
        return None                       # salito e ritracciato, non in caduta libera
    if float(F.get("pg_liq_sol", 0) or 0) < 8.0:
        return None                       # liquidita' deve essere sopravvissuta
    if int(F.get("pg_unique_buyers_5m", 0) or 0) < 10:
        return None
    if float(F.get("pg_ret_1m", 0) or 0) < 0.0:
        return None                       # i compratori stanno tornando ora
    if float(F.get("pg_turnover_5m", 0) or 0) < 0.05:
        return None
    if float(F.get("pg_creator_sold", 0) or 0) >= 0.5:
        return None
    return {"ath_mult": round(ath, 2), "drawdown": round(dd, 3),
            "liq_sol": round(float(F.get("pg_liq_sol", 0) or 0), 1),
            "buyers_5m": int(F.get("pg_unique_buyers_5m", 0) or 0)}


def esplosivo60_signal(st, F: dict, now: float) -> dict | None:
    if getattr(st, "lane", "") != "sol":
        return None
    age = float(F.get("age_s", 0) or 0)
    mcap = float(F.get("mcap_sol", 0) or 0)
    if not (55 <= age <= 300 and mcap > 0):
        return None
    base = float(getattr(st, "min_mcap", 0) or 0)
    peak = float(getattr(st, "peak_mcap", 0) or 0)
    if base <= 0 or peak <= 0:
        return None
    if mcap / base - 1 < 0.50:
        return None                       # non e' esploso dal minimo di nascita
    if mcap < 0.75 * peak:
        return None                       # gia' ritracciato: esplosione finita
    buyers60 = {t.get("trader") for t in st.window(60, now) if t.get("is_buy") and t.get("trader")}
    if len(buyers60) < 5:
        return None                       # niente pump di un singolo wallet
    if float(F.get("risk_engineered", 0) or 0) >= 0.5 or float(F.get("risk_distribution", 0) or 0) >= 0.5:
        return None
    return {"ret_from_min": round(mcap / base - 1, 3), "buyers_60s": len(buyers60), "age_s": round(age)}
