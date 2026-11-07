"""Fase 4 — AUTOPSY: il report che si scrive da solo (+ benchmark SOL).

Chiude il loop che prima era manuale (l'utente incollava gli output): un
documento markdown con meteo di mercato, anomalie del censimento, stato dei
verdetti ombra rispetto ai criteri pre-registrati, registro della Fabbrica e
il confronto col benchmark "tenere SOL" — la domanda a cui ogni numero deve
rispondere. Con --send viaggia su Telegram (se configurato).
"""
from __future__ import annotations
import time

from .analyze import analyze
from .census import census
from .regime import current_regime


def sol_benchmark(store, days=30):
    """Variazione del prezzo SOL nella finestra dei segnali: il 'non fare nulla'."""
    t0 = time.time() - days * 86400
    rows = store.q("SELECT ts,sol_price FROM signals WHERE ts>=? AND sol_price>0 ORDER BY ts", (t0,))
    if len(rows) < 2:
        return None
    a, b = float(rows[0]["sol_price"]), float(rows[-1]["sol_price"])
    return round((b / a - 1) * 100, 1) if a > 0 else None


def _med(a):
    m = a.get("med_net_mult")
    return f"{(m - 1) * 100:+.1f}%" if m is not None else "n/d"


def _criteria(a):
    if not a or not a.get("n"):
        return "nessun segnale"
    checks = [("n>=30", a["n"] >= 30), ("EV>0", (a.get("ev_pct") or -1) > 0),
              ("positivi>40%", (a.get("pos_share") or 0) > 0.40)]
    passed = " · ".join(f"{'✅' if ok else '❌'} {k}" for k, ok in checks)
    return f"n={a['n']}/30 · EV={a.get('ev_pct')}% · mediana={_med(a)} · positivi={a.get('pos_share')} — {passed}"


def build_autopsy(store) -> str:
    now = time.time()
    d = analyze(store)
    c = census(store)
    reg = current_regime(store)
    bench = sol_benchmark(store)
    L = [f"# PumpRadar — Autopsy {time.strftime('%Y-%m-%d %H:%M', time.localtime(now))}",
         "",
         f"**Meteo di mercato:** {str(reg.get('regime', '?')).upper()} "
         f"(graduation {reg.get('grad_rate', 0):.1%} vs baseline {reg.get('baseline', 0):.1%}, {reg.get('n_launch', 0)} lanci/ora)",
         f"**Benchmark 'tenere SOL' (30g):** {bench if bench is not None else 'n/d'}%",
         f"**Universo censito:** {c['n_launches']} lanci · graduation {c['baseline'].get('grad_rate', 0):.2%} · p(2x) {c['baseline'].get('p2x', 0):.1%}",
         "",
         "## Strategie ombra — stato verso i criteri di promozione"]
    if d.get("shadow"):
        for k, a in sorted(d["shadow"].items()):
            L.append(f"- **{k}**: {_criteria(a)}")
    else:
        L.append("- nessun segnale ombra ancora registrato")
    L += ["", "## Anomalie del censimento (candidate Fabbrica)"]
    if c["anomalies"]:
        for a in c["anomalies"][:8]:
            L.append(f"- {a['dimension']}/{a['key']}: {a['metric']} {a['value']:.1%} vs base {a['baseline']:.1%} (n={a['n']}, z={a['z']})")
    else:
        L.append("- nessuna sopra z=3")
    L += ["", "## Registro Fabbrica (ultimi verdetti)"]
    hyps = store.list_hypotheses(10)
    if hyps:
        for h in hyps:
            L.append(f"- {h['verdict']} · {h['rule_key']} · EV {h['ev_pct']}% (base {h['baseline_ev_pct']}%) · n={h['n']} · {h['detail'] or ''}")
    else:
        L.append("- registro vuoto: eseguire `python -m pumpradar factory`")
    L += ["", "## Tier storici (EV eseguibile, per memoria)"]
    for t, a in sorted(d.get("pg", {}).get("by_tier", {}).items()):
        L.append(f"- PG {t}: n={a.get('n')} EV={a.get('ev_pct')}% mediana={_med(a)}")
    for t, a in sorted(d.get("curve", {}).get("by_tier", {}).items()):
        L.append(f"- curva {t}: n={a.get('n')} EV={a.get('ev_pct')}% mediana={_med(a)}")
    L += ["", "_Verdetti secondo criteri pre-registrati (Fase 2). Nessuna promozione senza conferma in ombra su dati nuovi._"]
    return "\n".join(L)


def send_telegram(settings, text):
    from ..notify import _post
    if not settings.telegram_token or not settings.telegram_chat:
        return False
    _post(f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
          {"chat_id": settings.telegram_chat, "text": text[:3900], "disable_web_page_preview": True})
    return True
