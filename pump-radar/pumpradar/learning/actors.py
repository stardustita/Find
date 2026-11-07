"""Fase 4 — CARTOGRAFO: reputazione persistente degli attori.

Il feed registra il wallet di ogni trade e il creator di ogni lancio: qui
diventano una mappa. Due viste, calcolate dal censimento completo (nessun
filtro) e persistite in creator_stats / wallet_flags:

- CREATOR: quanti lanci, quanti graduati, picco mediano, quota di morti
  rapide (<5 min). Il serial-rugger e il serial-builder si vedono qui.
- WALLET (cartografia dei bundle, proxy onesto): wallet che comprano entro
  120s dal lancio in >=3 lanci dello STESSO creator = "leali al creator":
  e' la firma tipica delle crew organizzate, senza bisogno di dati esterni.

Nota di onesta': i trade dettagliati esistono solo per i token tracciati,
quindi la vista wallet eredita quel bias; quella creator no (usa i lanci).
"""
from __future__ import annotations
import statistics
from collections import defaultdict

from .census import launch_summaries

EARLY_S = 120
REPEAT_MIN = 3


def build_actor_stats(store, summaries=None, persist=True) -> dict:
    rows = summaries if summaries is not None else launch_summaries(store)
    byc = defaultdict(list)
    for r in rows:
        if r["creator"]:
            byc[r["creator"]].append(r)
    creators = []
    for c, v in byc.items():
        creators.append({
            "creator": c, "n_launches": len(v),
            "n_grad": sum(1 for r in v if r["graduated"]),
            "grad_rate": round(sum(1 for r in v if r["graduated"]) / len(v), 4),
            "med_peak": round(statistics.median(r["peak_mult"] for r in v), 2),
            "fast_dead_share": round(sum(1 for r in v if r["lifespan_s"] < 300) / len(v), 3),
            "last_ts": max(r["created_at"] for r in v),
        })
    creators.sort(key=lambda x: -x["n_launches"])

    # cartografia wallet: acquisti precoci ripetuti sullo stesso creator
    pair, wtokens, wb = defaultdict(int), defaultdict(set), {}
    tokmap = {r["mint"]: r for r in store.q("SELECT mint,creator,created_at,bonded_at FROM tokens")}
    for tr in store.q("SELECT trader,mint,ts FROM trades WHERE is_buy=1 AND trader IS NOT NULL AND trader<>''"):
        t = tokmap.get(tr["mint"])
        if not t or not t["creator"] or (tr["ts"] or 0) - (t["created_at"] or 0) > EARLY_S:
            continue
        pair[(tr["trader"], t["creator"])] += 1
        wtokens[tr["trader"]].add(tr["mint"])
        wb.setdefault(tr["trader"], []).append(1 if t["bonded_at"] else 0)
    bywallet = defaultdict(list)
    for (w, c), n in pair.items():
        bywallet[w].append(n)
    wallets = []
    for w, counts in bywallet.items():
        rep = sum(1 for n in counts if n >= REPEAT_MIN)
        grads = wb.get(w, [])
        wallets.append({"wallet": w, "n_tokens": len(wtokens[w]),
                        "n_repeat_creators": rep, "max_creator_launches": max(counts),
                        "bonded_share": round(sum(grads) / len(grads), 3) if grads else 0.0})
    wallets.sort(key=lambda x: (-x["n_repeat_creators"], -x["n_tokens"]))
    if persist:
        store.replace_actor_stats(creators, wallets)
    return {"creators": creators, "wallets": wallets}


def format_actors(a: dict, top=15) -> str:
    L = ["=== CARTOGRAFO: reputazione attori (dal censimento completo) ===",
         f"--- creator seriali (top {top} per lanci) ---"]
    for c in a["creators"][:top]:
        tag = "🧨 serial-rugger?" if c["fast_dead_share"] >= 0.9 and c["n_launches"] >= 10 else \
              "🏗️ builder?" if c["grad_rate"] >= 0.05 and c["n_launches"] >= 10 else ""
        L.append(f"  {c['creator'][:16]:<16} lanci={c['n_launches']:<4} grad={c['grad_rate']:.1%} "
                 f"picco_med={c['med_peak']:.2f}x morti<5m={c['fast_dead_share']:.0%} {tag}")
    loy = [w for w in a["wallets"] if w["n_repeat_creators"] > 0]
    L.append(f"--- wallet 'leali a un creator' (>=3 lanci precoci stesso creator): {len(loy)} ---")
    for w in loy[:top]:
        L.append(f"  {w['wallet'][:16]:<16} token={w['n_tokens']:<4} creator_ripetuti={w['n_repeat_creators']} "
                 f"max_stesso_creator={w['max_creator_launches']}  quota_graduati={w['bonded_share']:.0%}")
    L.append("  ! Vista wallet basata sui trade dei token tracciati (bias noto); vista creator sul censimento intero.")
    return "\n".join(L)
