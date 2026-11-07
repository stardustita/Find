"""Fase 3: ottimizzazione controfattuale ingressi/uscite con split temporale."""
import time
from pumpradar.learning.optimize import optimize, race_stats, _entries
from pumpradar.store import Store

def test_entries_pullback_and_race():
    t0 = 1000.0
    path = [(t0, 100.0), (t0 + 10, 130.0), (t0 + 40, 80.0), (t0 + 80, 160.0), (t0 + 200, 300.0)]
    names = dict((name, (sub, em)) for name, sub, em in _entries(path, t0, 100.0))
    assert "immediato" in names and "ritardo+30s" in names and "pullback-15%" in names
    assert names["pullback-15%"][1] == 80.0          # entra sul ritracciamento, non sul segnale
    assert names["ritardo+30s"][1] == 80.0
    # gara: il prezzo tocca 1.8x (180) prima dello stop (65)? qui si ferma a 300 passando per 160: target
    assert race_stats([(t0, 100.0, path)]) == {"target_prima": 1}
    path2 = [(t0, 100.0), (t0 + 10, 60.0), (t0 + 20, 200.0)]
    assert race_stats([(t0, 100.0, path2)]) == {"stop_prima": 1}

def _seed_paths(store, n=44):
    t0 = time.time() - 200000
    mint = "P" * 32
    store.upsert_token({"mint": mint, "name": "P", "symbol": "P", "uri": "", "creator": "d",
                        "created_at": t0, "first_seen": t0, "init_sol": 0, "init_mcap_sol": 50,
                        "mayhem": 0, "pool": "pump", "state": "dead", "last_ts": t0, "creator_sig": None,
                        "quote_mint": "SOL", "lane": "sol"})
    for i in range(n):
        ts = t0 + i * 1000
        store.add_signal({"mint": mint, "ts": ts, "tier": "WATCH", "score": 0.5, "price_sol": 1,
                          "mcap_sol": 100.0, "age_s": 60, "sol_price": 150, "gates": {}, "plan": {}, "features": {}})
        # pattern: spike, pullback -25%, poi corsa a 3x — il pullback deve battere l'immediato
        for j, m in enumerate([140.0, 75.0, 120.0, 200.0, 300.0, 280.0]):
            store.add_trade({"mint": mint, "ts": ts + 10 + j * 30, "trader": "w", "is_buy": True,
                             "sol": 1, "tokens": 1, "mcap_sol": m, "lane": "sol"})

def test_optimize_finds_pullback_candidate(tmp_path):
    store = Store(str(tmp_path / "o.db")); _seed_paths(store)
    d = optimize(store, "curve")
    assert d["n_signals"] == 44 and d["race"].get("target_prima", 0) >= 1
    joined = " ".join(r["entry"] for r in d["top_by_test"])
    assert "pullback" in joined or "ritardo" in joined
    from pumpradar.learning.optimize import format_optimize
    assert "Ottimizzazione controfattuale" in format_optimize(d)
