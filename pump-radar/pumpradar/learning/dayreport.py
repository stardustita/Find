"""REPORT 24H: analisi completa dei lanci recenti, tutto cio' che il DB sa.

Universo: token creati nella finestra (default 24h) con le loro barre 5s da
launch_bars — prezzi, picchi, tempi di picco, volumi, forme. Wallet: dalla
tabella trades (solo token tracciati: bias dichiarato, e' il limite noto) e
dalla tabella wallets (nuovi vs gia' visti). Creator: concentrazione e quota
serial-rugger. NON include 'visualizzatori'/engagement del sito pump.fun:
non sono dati on-chain e nessun feed gratuito li fornisce.

Copertura dichiarata in testa: se `run` e' stato spento, la finestra e'
parziale e il report lo dice (primo/ultimo lancio osservato).
"""
from __future__ import annotations
import statistics
import time
from collections import Counter, defaultdict

from ..guardian import serial_ruggers
from .census import _shape, launch_summaries


def _pct(xs, q):
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def _top(rows, key, n=10, reverse=True):
    return sorted(rows, key=key, reverse=reverse)[:n]


def dayreport(store, hours=24.0, now=None) -> dict:
    now = now or time.time()
    t0 = now - hours * 3600
    rows = [r for r in launch_summaries(store) if r["created_at"] >= t0]
    out = {"window_h": hours, "t0": t0, "now": now, "n_launches": len(rows)}
    if not rows:
        return out
    out["coverage"] = (min(r["created_at"] for r in rows), max(r["created_at"] for r in rows))
    out["by_lane"] = Counter(r["lane"] for r in rows)
    out["by_hour"] = Counter(r["hour_utc"] for r in rows)
    out["graduated"] = sum(1 for r in rows if r["graduated"])
    peaks = [r["peak_mult"] for r in rows]
    out["peak"] = {"med": round(statistics.median(peaks), 2), "p90": round(_pct(peaks, .9), 2),
                   "p99": round(_pct(peaks, .99), 2), "max": round(max(peaks), 1),
                   "ge2": sum(1 for p in peaks if p >= 2), "ge5": sum(1 for p in peaks if p >= 5),
                   "ge10": sum(1 for p in peaks if p >= 10), "ge50": sum(1 for p in peaks if p >= 50)}
    life = [r["lifespan_s"] for r in rows]
    out["life"] = {"med": round(statistics.median(life)), "p90": round(_pct(life, .9)),
                   "dead60": round(sum(1 for x in life if x < 60) / len(life), 3),
                   "dead300": round(sum(1 for x in life if x < 300) / len(life), 3),
                   "surv900": round(sum(1 for x in life if x >= 900) / len(life), 3)}
    out["vol"] = {"total_buy_sol": round(sum(r["buy60"] for r in rows), 1),
                  "med_buy60": round(statistics.median(r["buy60"] for r in rows), 2),
                  "p90_buy60": round(_pct([r["buy60"] for r in rows], .9), 1)}
    ttp = []
    for r in rows:
        if r["path"]:
            ttp.append(max(r["path"], key=lambda x: x[1])[0] - r["created_at"])
    out["time_to_peak"] = {"med": round(statistics.median(ttp)) if ttp else 0,
                           "within60": round(sum(1 for x in ttp if x <= 60) / len(ttp), 3) if ttp else 0}
    out["shapes"] = Counter(_shape(r) for r in rows)
    out["top_peak"] = [{"mint": r["mint"], "creator": r["creator"], "peak_mult": round(r["peak_mult"], 1),
                        "peak_mcap": round(r["peak_mcap"]), "life_s": round(r["lifespan_s"]),
                        "graduated": r["graduated"]} for r in _top(rows, lambda r: r["peak_mult"])]
    out["top_vol"] = [{"mint": r["mint"], "buy60": round(r["buy60"], 1), "peak_mult": round(r["peak_mult"], 1)}
                      for r in _top(rows, lambda r: r["buy60"])]
    creators = Counter(r["creator"] for r in rows if r["creator"])
    out["creators"] = {"unique": len(creators),
                        "top10_share": round(sum(c for _, c in creators.most_common(10)) / max(1, len(rows)), 3),
                        "top": creators.most_common(8)}
    out["ruggers"] = len(serial_ruggers(rows) & {r["creator"] for r in rows})
    # ---- wallet dai trade registrati (token tracciati: bias dichiarato) ----
    trades = store.q("SELECT trader,mint,ts,is_buy,sol FROM trades WHERE ts>=? AND trader IS NOT NULL AND trader<>''", (t0,))
    byw = defaultdict(lambda: {"n": 0, "buy": 0.0, "sell": 0.0, "tokens": set()})
    early = defaultdict(int)
    created = {r["mint"]: r["created_at"] for r in rows}
    for tr in trades:
        w = byw[tr["trader"]]
        w["n"] += 1; w["tokens"].add(tr["mint"])
        w["buy" if tr["is_buy"] else "sell"] += float(tr["sol"] or 0)
        if tr["is_buy"] and tr["mint"] in created and float(tr["ts"]) - created[tr["mint"]] <= 60:
            early[tr["trader"]] += 1
    out["wallets"] = {
        "unique_traders": len(byw),
        "new_wallets": store.q("SELECT COUNT(*) c FROM wallets WHERE first_seen>=?", (t0,))[0]["c"],
        "sprayers": sum(1 for w in byw.values() if len(w["tokens"]) >= 5),
        "top_active": sorted(((w, v["n"], len(v["tokens"])) for w, v in byw.items()), key=lambda x: -x[1])[:8],
        "top_early": sorted(early.items(), key=lambda x: -x[1])[:8],
        "n_trades_tracked": len(trades)}
    return out


def _ts(x):
    return time.strftime("%d/%m %H:%M", time.localtime(x))


def format_dayreport(d: dict) -> str:
    L = [f"=== REPORT ULTIME {d['window_h']:.0f}H: analisi completa dei lanci ==="]
    if not d["n_launches"]:
        L.append("  nessun lancio nella finestra (run spento? launch_bars vuoto?)")
        return "\n".join(L)
    f, l = d["coverage"]
    L.append(f"  copertura osservata: {_ts(f)} → {_ts(l)} · lanci: {d['n_launches']} · per corsia: {dict(d['by_lane'])}")
    L.append(f"  graduati: {d['graduated']} ({d['graduated'] / d['n_launches']:.1%})")
    p, lf = d["peak"], d["life"]
    L.append(f"  PICCHI dal prezzo di lancio: mediano {p['med']}x · p90 {p['p90']}x · p99 {p['p99']}x · max {p['max']}x")
    L.append(f"  hanno toccato: 2x {p['ge2']} · 5x {p['ge5']} · 10x {p['ge10']} · 50x {p['ge50']}  (su {d['n_launches']})")
    L.append(f"  VITA: mediana {lf['med']}s · morti <60s {lf['dead60']:.0%} · <5min {lf['dead300']:.0%} · vivi a 15min {lf['surv900']:.0%}")
    L.append(f"  TEMPO AL PICCO: mediano {d['time_to_peak']['med']}s · entro 60s: {d['time_to_peak']['within60']:.0%} dei casi")
    L.append(f"  VOLUMI primo minuto: totale comprato {d['vol']['total_buy_sol']} SOL · mediano/lancio {d['vol']['med_buy60']} · p90 {d['vol']['p90_buy60']}")
    L.append(f"  FORME primi 60s: {dict(d['shapes'])}")
    L.append("--- top 10 per picco ---")
    for t in d["top_peak"]:
        L.append(f"  {t['mint'][:10]}… picco {t['peak_mult']}x ({t['peak_mcap']} SOL) vita {t['life_s']}s {'GRADUATO' if t['graduated'] else ''} creator {t['creator'][:8]}…")
    L.append("--- top 10 per SOL comprati nel primo minuto ---")
    for t in d["top_vol"]:
        L.append(f"  {t['mint'][:10]}… buy60 {t['buy60']} SOL · picco {t['peak_mult']}x")
    c = d["creators"]
    L.append(f"--- creator: {c['unique']} unici · top10 = {c['top10_share']:.0%} dei lanci · serial-rugger attivi nella finestra: {d['ruggers']}")
    for w, n in c["top"]:
        L.append(f"  {w[:12]}… {n} lanci")
    w = d["wallets"]
    L.append(f"--- wallet (solo token tracciati, {w['n_trades_tracked']} trade): {w['unique_traders']} trader unici · "
             f"nuovi {w['new_wallets']} · su >=5 token: {w['sprayers']}")
    L.append("  piu' attivi: " + ", ".join(f"{a[:8]}…({n} trade/{t} token)" for a, n, t in w["top_active"]))
    L.append("  compratori precoci (primi 60s) piu' frequenti: " + ", ".join(f"{a[:8]}…({n})" for a, n in w["top_early"]))
    L.append("  ! Prezzi/trade/volumi/wallet: dati on-chain completi per i lanci (barre 5s); dettaglio trade solo per token tracciati.")
    L.append("  ! 'Visualizzatori'/engagement del sito pump.fun: NON disponibili on-chain ne' via feed gratuiti.")
    return "\n".join(L)
