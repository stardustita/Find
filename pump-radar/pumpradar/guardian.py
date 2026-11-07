"""Fase 5 — GUARDIANI: agenti di VETO sopra l'emissione dei segnali.

Diagnosi (dati reali): i tier storici emettono con una selezione falsificata
(curva n=801 tutta negativa, RUN a pareggio) -> l'utente riceve scam e token
in caduta. La risposta non e' generare piu' segnali, ma vietare meglio:

- CENSORE: ultimo controllo prima dell'emissione operativa (ENTRY/STRONG, RUN).
  Veti duri, ognuno validato sul censimento: <4 compratori unici/60s (coorte
  con p(2x) 1-8%), gia' -30% dal picco, creator serial-rugger, regime toxic.
- SENTINELLA: pattern strutturali scam — concentrazione degli acquisti del
  primo minuto in 1 wallet, creator con >=10 lanci e >=90% morti in <5 minuti.
- REVISORE: EV eseguibile degli ultimi 100 segnali per tier; se negativo con
  n>=50 il tier viene RETROCESSO a osservazione (registrato e misurato, mai
  notificato ne' operato). Reversibile: torna attivo solo con finestra positiva.

Un segnale censurato non sparisce: viene registrato come WATCH. Il sistema
continua a imparare, ma smette di presentare come opportunita' cio' che non
ha dimostrato di esserlo.
"""
from __future__ import annotations
import statistics
from collections import defaultdict

MIN_BUYERS_60S = 4
MAX_DRAWDOWN_AT_SIGNAL = 0.30
CONCENTRATION_TOP1 = 0.60
RUGGER_MIN_LAUNCHES = 10
RUGGER_FAST_DEAD = 0.90
HEALTH_WINDOW = 100
HEALTH_MIN_N = 50


def serial_ruggers(summaries, min_launches=RUGGER_MIN_LAUNCHES, fast_dead_share=RUGGER_FAST_DEAD):
    """Creator seriali quasi sempre letali in <5 min: blacklist della Sentinella."""
    by = defaultdict(list)
    for r in summaries:
        if r.get("creator"):
            by[r["creator"]].append(r)
    return {c for c, v in by.items()
            if len(v) >= min_launches
            and sum(1 for r in v if r["lifespan_s"] < 300) / len(v) >= fast_dead_share}


def censor_check(st, F: dict, now: float, blacklist=frozenset(), regime_label="unknown") -> list[str]:
    """Ritorna i motivi di veto (lista vuota = il segnale puo' uscire)."""
    reasons = []
    mcap = float(F.get("mcap_sol", 0) or 0)
    peak = float(getattr(st, "peak_mcap", 0) or 0)
    buyers = {t.get("trader") for t in st.window(60, now) if t.get("is_buy") and t.get("trader")}
    if len(buyers) < MIN_BUYERS_60S:
        reasons.append("pochi_compratori_60s")
    if peak > 0 and mcap and mcap < peak * (1 - MAX_DRAWDOWN_AT_SIGNAL):
        reasons.append("gia_in_caduta")
    if getattr(st, "creator", "") and st.creator in blacklist:
        reasons.append("creator_serial_rugger")
    if regime_label == "toxic":
        reasons.append("regime_toxic")
    # Sentinella: il primo minuto dominato da un solo wallet e' la firma dello scam
    created = float(getattr(st, "created_at", 0) or 0)
    per = {}
    for t in getattr(st, "trades", []):
        if t.get("is_buy") and created and float(t.get("ts") or 0) <= created + 60:
            per[t.get("trader")] = per.get(t.get("trader"), 0.0) + float(t.get("sol") or 0)
    tot = sum(per.values())
    if tot > 0 and max(per.values()) / tot > CONCENTRATION_TOP1 and len(buyers) < 8:
        reasons.append("concentrazione_sospetta")
    if float(F.get("risk_engineered", 0) or 0) >= 0.5 or float(F.get("risk_distribution", 0) or 0) >= 0.5:
        reasons.append("rischio_strutturale")
    return reasons


def tier_health(store, window=HEALTH_WINDOW) -> dict:
    """Revisore: EV eseguibile degli ultimi `window` segnali risolti per tier."""
    from .learning.analyze import curve_signal_facts, pg_signal_facts
    out = {}
    for kind, facts in (("curve", curve_signal_facts(store)), ("pg", pg_signal_facts(store))):
        by = defaultdict(list)
        for f in facts:
            by[f["tier"]].append(f)
        for t, v in by.items():
            nets = [x["net_mult"] for x in v[-window:] if x.get("net_mult") is not None]
            if not nets:
                continue
            ev = (statistics.mean(nets) - 1) * 100
            out[f"{kind}:{t}"] = {
                "n": len(nets), "ev_pct": round(ev, 1),
                "med_pct": round((statistics.median(nets) - 1) * 100, 1),
                "pos_share": round(sum(1 for x in nets if x > 1) / len(nets), 3),
                "demote": len(nets) >= HEALTH_MIN_N and ev < 0,
            }
    return out


def format_guardian(blacklist, regime_label, health) -> str:
    L = ["=== GUARDIANI: veti attivi sull'emissione ===",
         f"  creator serial-rugger in blacklist: {len(blacklist)}",
         f"  regime attuale: {regime_label} (toxic = segnali curva solo osservazione)",
         "--- Revisore qualita': EV ultimi 100 segnali per tier ---"]
    if not health:
        L.append("  nessun tier con segnali risolti")
    for k, v in sorted(health.items()):
        flag = "⛔ RETROCESSO a osservazione" if v["demote"] else "attivo"
        L.append(f"  {k:<14} n={v['n']:<4} EV={v['ev_pct']:+.1f}% mediana={v['med_pct']:+.1f}% pos={v['pos_share']:.0%} → {flag}")
    L.append("  ! Retrocessione automatica e reversibile: il tier torna attivo solo se la finestra torna positiva.")
    return "\n".join(L)
