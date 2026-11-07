"""Fase 4 — METEOROLOGO: il regime di mercato, ora per ora.

Gli esiti dei segnali dipendevano dal periodo (train -25% vs test +1492% nello
stesso optimize): il mercato ha un meteo. Qui lo misuriamo dal censimento:
lanci/ora, tasso di graduation dei lanci di quell'ora, vita mediana.
Regimi: risk_on (graduation >= 1.4x la baseline storica), toxic (<= 0.6x),
neutral in mezzo. Ogni verdetto puo' cosi' essere letto PER REGIME: una
strategia vera in un regime e falsa in un altro non e' una strategia.
"""
from __future__ import annotations
import statistics
import time

MIN_N = 20          # lanci minimi per fidarsi del tasso di un'ora
RISK_ON, TOXIC = 1.4, 0.6


def regime_series(store, now=None) -> list[dict]:
    now = now or time.time()
    launches = {}
    for r in store.q("SELECT created_at, bonded_at FROM tokens WHERE created_at IS NOT NULL"):
        h = int((r["created_at"] or 0) // 3600)
        if not h:
            continue
        launches.setdefault(h, []).append(1 if r["bonded_at"] else 0)
    life = {}
    for r in store.q("""SELECT CAST(MIN(bucket) AS INT) f, CAST(MAX(bucket) AS INT) l, mint FROM launch_bars GROUP BY mint"""):
        h = int((r["f"] or 0) // 3600)
        if h:
            life.setdefault(h, []).append((r["l"] or 0) - (r["f"] or 0))
    out, rates = [], []
    for h in sorted(launches):
        v = launches[h]
        rate = sum(v) / len(v) if v else 0.0
        base = statistics.median(rates) if len(rates) >= 6 else (statistics.median(rates) if rates else rate)
        label = "neutral"
        if len(v) >= MIN_N and base > 0:
            label = "risk_on" if rate >= RISK_ON * base else "toxic" if rate <= TOXIC * base else "neutral"
        if len(v) >= MIN_N:
            rates.append(rate)
        lv = life.get(h, [])
        out.append({"hour": h, "ts": h * 3600, "n_launch": len(v), "grad_rate": round(rate, 4),
                    "med_life_s": round(statistics.median(lv)) if lv else None,
                    "baseline": round(base, 4), "regime": label,
                    "mature": (now - h * 3600) > 7200})
    return out


def regime_at(series, ts):
    label = "unknown"
    for row in series:
        if row["ts"] <= ts:
            label = row["regime"]
        else:
            break
    return label


def current_regime(store, now=None) -> dict:
    s = regime_series(store, now)
    mature = [r for r in s if r["mature"] and r["n_launch"] >= MIN_N]
    return mature[-1] if mature else (s[-1] if s else {"regime": "unknown", "n_launch": 0, "grad_rate": 0})


def format_regime(series, last=24) -> str:
    if not series:
        return "=== METEOROLOGO: nessun dato (launch_bars vuoto) ==="
    cur = [r for r in series if r["mature"] and r["n_launch"] >= MIN_N]
    c = cur[-1] if cur else series[-1]
    L = ["=== METEOROLOGO: regime di mercato (tasso graduation per ora di lancio) ===",
         f"  ORA: {c['regime'].upper()}  (grad {c['grad_rate']:.1%} vs baseline {c['baseline']:.1%}, lanci/ora {c['n_launch']}, vita mediana {c['med_life_s']}s)",
         "--- ultime 24 ore mature ---"]
    for r in series[-last:]:
        bar = {"risk_on": "🟢", "toxic": "🔴", "neutral": "⚪"}.get(r["regime"], "·")
        L.append(f"  {time.strftime('%d/%m %H:00', time.gmtime(r['ts']))} UTC {bar} {r['regime']:<8} lanci={r['n_launch']:<4} grad={r['grad_rate']:.1%} vita_med={r['med_life_s']}s")
    return "\n".join(L)
