"""Fase 4 — CENSIMENTO: tassi base per coorte su TUTTI i lanci.

launch_bars registra ogni lancio (anche morto in 8 secondi): qui lo trasformiamo
in conoscenza. Per ogni coorte misuriamo graduation rate, sopravvivenza,
probabilita' di 2x/5x dal primo prezzo, picco mediano. Nessun filtro di mezzo:
e' il primo sguardo al mercato senza survivorship bias.

Le coorti anomale (z >= 3 dopo il confronto col resto dell'universo) sono le
candidate che la Fabbrica di Ipotesi (factory.py) deve giudicare con EV sui
percorsi: il censimento PROPONE, la fabbrica DISPONE.
"""
from __future__ import annotations
import math
import statistics
from collections import defaultdict


def launch_summaries(store) -> list[dict]:
    """Un riassunto per lancio: percorso a barre, esiti, contesto."""
    bars = defaultdict(list)
    for r in store.q("SELECT mint,bucket,n_trades,buy_sol,sell_sol,n_buyers,mcap_sol FROM launch_bars ORDER BY mint,bucket"):
        bars[r["mint"]].append(r)
    toks = {r["mint"]: dict(r) for r in store.q("SELECT mint,creator,created_at,lane,bonded_at FROM tokens")}
    # lanci precedenti per creator (esperienza al momento del lancio)
    prior, seen = {}, defaultdict(int)
    for r in sorted(toks.values(), key=lambda x: x["created_at"] or 0):
        prior[r["mint"]] = seen[r["creator"]] if r["creator"] else 0
        if r["creator"]:
            seen[r["creator"]] += 1
    out = []
    for mint, bs in bars.items():
        t = toks.get(mint) or {}
        created = float(t.get("created_at") or bs[0]["bucket"])
        mcaps = [float(b["mcap_sol"] or 0) for b in bs]
        first = next((m for m in mcaps if m > 0), 0.0)
        if not first:
            continue
        peak = max(mcaps)
        b60 = [b for b in bs if float(b["bucket"]) <= created + 60]
        m60 = [float(b["mcap_sol"] or 0) for b in b60 if float(b["mcap_sol"] or 0) > 0]
        ret60 = (m60[-1] / first - 1) if m60 else 0.0
        creator = t.get("creator") or ""
        pr = prior.get(mint, 0)
        out.append({
            "mint": mint, "creator": creator, "created_at": created,
            "lane": t.get("lane") or bs[0]["lane"] or "?",
            "graduated": bool(t.get("bonded_at")),
            "lifespan_s": float(bs[-1]["bucket"] - bs[0]["bucket"]),
            "first_mcap": first, "peak_mcap": peak, "last_mcap": mcaps[-1],
            "peak_mult": peak / first, "last_mult": mcaps[-1] / first,
            "vol60": sum(float(b["buy_sol"] or 0) + float(b["sell_sol"] or 0) for b in b60),
            "buy60": sum(float(b["buy_sol"] or 0) for b in b60),
            "buyers60": sum(int(b["n_buyers"] or 0) for b in b60),
            "ret60": ret60,
            "creator_prior": pr,
            "hour_utc": int((created // 3600) % 24),
            "path": [(float(b["bucket"]), float(b["mcap_sol"] or 0)) for b in bs if float(b["mcap_sol"] or 0) > 0],
            "bars": [(float(b["bucket"]), float(b["buy_sol"] or 0), float(b["sell_sol"] or 0),
                      int(b["n_buyers"] or 0), float(b["mcap_sol"] or 0)) for b in bs],
        })
    return out


def _metrics(rows):
    n = len(rows)
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "grad_rate": round(sum(1 for r in rows if r["graduated"]) / n, 4),
        "surv15": round(sum(1 for r in rows if r["lifespan_s"] >= 900) / n, 3),
        "p2x": round(sum(1 for r in rows if r["peak_mult"] >= 2) / n, 3),
        "p5x": round(sum(1 for r in rows if r["peak_mult"] >= 5) / n, 3),
        "med_peak": round(statistics.median(r["peak_mult"] for r in rows), 2),
        "med_life_s": round(statistics.median(r["lifespan_s"] for r in rows)),
    }


def _z(p1, n1, p0, n0):
    if not n1 or not n0:
        return 0.0
    p = (p1 * n1 + p0 * n0) / (n1 + n0)
    se = math.sqrt(max(p * (1 - p), 1e-9) * (1 / n1 + 1 / n0))
    return (p1 - p0) / se if se > 0 else 0.0


def _shape(r):
    x = r["ret60"]
    return ("esplosivo" if x >= 0.5 else "rialzo" if x >= 0.10 else
            "piatto" if x > -0.10 else "cedimento" if x > -0.30 else "crollo")


def _buyers_b(r):
    b = r["buyers60"]
    return "0" if b == 0 else "1-3" if b <= 3 else "4-9" if b <= 9 else "10+"


def _size_b(r):
    v = r["buy60"]
    return "<1 SOL" if v < 1 else "1-5" if v < 5 else "5-20" if v < 20 else "20+"


def _exp_b(r):
    p = r["creator_prior"]
    return "primo lancio" if p == 0 else "1 lancio" if p == 1 else "2-4" if p <= 4 else "5+"


DIMENSIONS = {
    "lane": lambda r: r["lane"],
    "ora_utc": lambda r: f"{r['hour_utc']:02d}",
    "esperienza_creator": _exp_b,
    "forma_primi_60s": _shape,
    "compratori_60s": _buyers_b,
    "dimensione_buy_60s": _size_b,
}


def census(store, summaries=None) -> dict:
    rows = summaries if summaries is not None else launch_summaries(store)
    base = _metrics(rows)
    dims = {}
    for name, fn in DIMENSIONS.items():
        groups = defaultdict(list)
        for r in rows:
            groups[fn(r)].append(r)
        dims[name] = {k: _metrics(v) for k, v in groups.items()}
        # creator singoli solo se seriali (>=30 lanci): altrimenti e' rumore nominale
        if name == "esperienza_creator":
            byc = defaultdict(list)
            for r in rows:
                if r["creator"]:
                    byc[r["creator"]].append(r)
            big = {c: _metrics(v) for c, v in byc.items() if len(v) >= 30}
            if big:
                dims["creator_seriali"] = dict(sorted(big.items(), key=lambda kv: -kv[1]["n"])[:15])
    anomalies = []
    for name, groups in dims.items():
        for key, m in groups.items():
            if m["n"] < 150:
                continue
            rest = [r for r in rows if (DIMENSIONS.get(name) or (lambda r: r["creator"]))(r) != key] \
                if name != "creator_seriali" else [r for r in rows if r["creator"] != key]
            rm = _metrics(rest)
            if not rm.get("n"):
                continue
            for metric in ("grad_rate", "p2x"):
                z = _z(m[metric], m["n"], rm[metric], rm["n"])
                if z >= 3.0 and m[metric] > base[metric]:
                    anomalies.append({"dimension": name, "key": key, "metric": metric,
                                      "value": m[metric], "baseline": base[metric], "n": m["n"], "z": round(z, 1)})
    anomalies.sort(key=lambda a: -a["z"])
    return {"n_launches": len(rows), "baseline": base, "dimensions": dims, "anomalies": anomalies}


def _fmt_m(m):
    if not m or not m.get("n"):
        return "n=0"
    return (f"n={m['n']:<6} grad={m['grad_rate']:.1%}  surv15={m['surv15']:.0%}  "
            f"p2x={m['p2x']:.0%}  p5x={m['p5x']:.0%}  picco_med={m['med_peak']:.2f}x  vita_med={m['med_life_s']:.0f}s")


def format_census(c: dict) -> str:
    L = ["=== CENSIMENTO: tassi base su TUTTI i lanci (nessun filtro) ==="]
    L.append(f"  universo: {_fmt_m(c['baseline'])}")
    for name, groups in c["dimensions"].items():
        L.append(f"--- per {name} ---")
        for k, m in sorted(groups.items(), key=lambda kv: -kv[1]["n"])[:14]:
            L.append(f"  {str(k)[:44]:<44} {_fmt_m(m)}")
    if c["anomalies"]:
        L.append("=== ANOMALIE (z>=3 vs resto dell'universo): candidate per la Fabbrica ===")
        for a in c["anomalies"][:15]:
            L.append(f"  {a['dimension']}/{a['key']}: {a['metric']}={a['value']:.1%} (base {a['baseline']:.1%}) n={a['n']} z={a['z']}")
    else:
        L.append("=== ANOMALIE: nessuna coorte sopra z=3 (servono piu' lanci o l'effetto non c'e') ===")
    return "\n".join(L)
