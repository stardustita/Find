"""Fase 0: simulazione piano sui percorsi e dissezione dei segnali storici."""
import time
import pytest
from pumpradar.learning.analyze import analyze, simulate_plan
from pumpradar.store import Store

def test_simulate_plan_ladder_trailing_stop():
    entry = 100.0
    # sale a 2x (vende 25% a 1.8), poi 3.2x (25% a 3.0), poi crolla: trailing sul residuo
    path = [(0, 100.0), (10, 200.0), (20, 320.0), (30, 320.0 * 0.6)]
    sim = simulate_plan(path, entry, [(1.8, .25), (3.0, .25), (6.0, .25)], 1.8, 0.35, 0.65, 0.17, 780, 0)
    assert sim["reason"] == "trailing" and sim["peak_mult"] == pytest.approx(3.2)
    expected = 1 + .25 * (1.8 - 1 - .17) + .25 * (3.0 - 1 - .17) + .50 * (1.92 - 1 - .17)
    assert sim["net_mult"] == pytest.approx(expected, abs=1e-6)
    # stop immediato
    sim = simulate_plan([(0, 100.0), (10, 60.0)], entry, [(1.8, .25)], 1.8, 0.35, 0.65, 0.17, 780, 0)
    assert sim["reason"] == "stop" and sim["net_mult"] == pytest.approx(1 + (0.6 - 1 - .17), abs=1e-6)
    # percorso vuoto
    assert simulate_plan([], entry, [(1.8, .25)], 1.8, 0.35, 0.65, 0.17)["net_mult"] is None

def _seed(store):
    t0 = time.time() - 100000
    mint = "W" * 32
    store.upsert_token({"mint": mint, "name": "W", "symbol": "W", "uri": "", "creator": "d",
                        "created_at": t0, "first_seen": t0, "init_sol": 0, "init_mcap_sol": 40,
                        "mayhem": 0, "pool": "pump", "state": "dead", "last_ts": t0, "creator_sig": None,
                        "quote_mint": "SOL", "lane": "sol"})
    # WATCH quasi-graduation (progress 0.8) che poi raddoppia; ENTRY precoce che muore
    store.add_signal({"mint": mint, "ts": t0 + 100, "tier": "WATCH", "score": 0.40, "price_sol": 1,
                      "mcap_sol": 100.0, "age_s": 100, "sol_price": 150,
                      "gates": {"curve_window": False, "entry_window": False},
                      "plan": {}, "features": {"curve_progress": 0.8}})
    store.add_signal({"mint": mint, "ts": t0 + 100, "tier": "ENTRY", "score": 0.52, "price_sol": 1,
                      "mcap_sol": 100.0, "age_s": 90, "sol_price": 150,
                      "gates": {}, "plan": {}, "features": {"curve_progress": 0.2}})
    for j, m in enumerate([110.0, 150.0, 205.0, 190.0, 60.0]):
        store.add_trade({"mint": mint, "ts": t0 + 200 + j * 60, "trader": "w", "is_buy": True,
                         "sol": 1, "tokens": 1, "mcap_sol": m, "lane": "sol"})

def test_analyze_dissection(tmp_path):
    store = Store(str(tmp_path / "a.db")); _seed(store)
    d = analyze(store)
    assert d["n_curve_signals"] == 2
    watch = d["curve"]["by_tier"]["WATCH"]
    # picco teorico 2.05x, ma il piano (vendita a 1.8x + stop sul crollo) rende 0.73x netto:
    # e' esattamente la differenza tra backtest a picco ed EV eseguibile che Fase 0 misura
    assert watch["hit1.8_15m"] == 1.0 and watch["avg_net_mult"] == pytest.approx(0.73, abs=0.01)
    dis = d["curve"]["watch_dissection"]
    assert "curve_window" in dis["by_failed_gate"]
    assert "0.72-0.90" in dis["by_progress"]
    from pumpradar.learning.analyze import format_report
    assert "FASE 0" in format_report(d)

def test_agg_median_unmasks_tail_mirage():
    # 9 trade tipici in perdita e UN moonshot: la media esplode, la mediana no.
    from pumpradar.learning.analyze import _agg
    facts = [{"peak15": 1.0, "peak24": 1.0, "net_mult": 0.6} for _ in range(9)]
    facts.append({"peak15": 200.0, "peak24": 200.0, "net_mult": 160.0})
    a = _agg(facts)
    assert a["ev_pct"] > 1000            # media: miraggio da coda destra
    assert a["med_net_mult"] == pytest.approx(0.6)   # trade tipico: -40%
    assert a["pos_share"] == pytest.approx(0.1)
