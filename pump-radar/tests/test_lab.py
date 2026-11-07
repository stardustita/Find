"""Fase 4 — Laboratorio: censimento, meteorologo, fabbrica, cartografo, oracolo, autopsy."""
import time
import pytest
from pumpradar.store import Store
from pumpradar.learning.census import census
from pumpradar.learning.regime import current_regime, regime_series
from pumpradar.learning.factory import run_factory
from pumpradar.learning.actors import build_actor_stats
from pumpradar.learning.knn import find_twins
from pumpradar.learning.autopsy import build_autopsy, sol_benchmark

NOW = time.time()
RISER = [(o, 30 + o * 0.3) for o in range(0, 901, 30)]     # 30 -> 300 SOL in 15 min
DEAD = [(0, 30.0), (30, 28.0), (60, 20.0)]                  # muore in un minuto

def _launch(store, mint, creator, created, path, bonded=False):
    store.upsert_token({"mint": mint, "name": "T", "symbol": "T", "uri": "", "creator": creator,
                        "created_at": created, "first_seen": created, "init_sol": 0,
                        "init_mcap_sol": path[0][1], "mayhem": 0, "pool": "pump", "state": "x",
                        "last_ts": created, "creator_sig": None, "quote_mint": "SOL", "lane": "sol"})
    if bonded:
        store.execute("UPDATE tokens SET bonded_at=? WHERE mint=?", (created + 600, mint))
    store.add_bars([(mint, int(created + off), "sol", 3, 2.0, 0.5, 4, m) for off, m in path])

def _seed_universe(store):
    for i in range(160):
        _launch(store, f"G{i:032d}", "GOODCREATOR", NOW - 86400 * 3 - i * 60, RISER, bonded=True)
    for i in range(160):
        _launch(store, f"B{i:032d}", "BADCREATOR", NOW - 86400 * 3 - i * 60, DEAD)

def test_census_and_factory(tmp_path):
    store = Store(str(tmp_path / "l.db")); _seed_universe(store)
    c = census(store)
    assert c["n_launches"] == 320 and c["baseline"]["grad_rate"] == pytest.approx(0.5)
    assert any(a["dimension"] == "creator_seriali" and a["key"] == "GOODCREATOR" for a in c["anomalies"])
    f = run_factory(store)
    good = [r for r in f["rows"] if r["cohort"] == "GOODCREATOR"]
    assert good and good[0]["verdict"] == "CANDIDATE" and good[0]["ev_pct"] > 0
    assert len(store.list_hypotheses()) >= 1
    n0 = len(store.list_hypotheses())
    run_factory(store)                                   # registro immutabile: niente doppioni
    assert len(store.list_hypotheses()) == n0

def test_actors(tmp_path):
    store = Store(str(tmp_path / "a.db")); _seed_universe(store)
    for i in range(3):                                   # wallet leale: compra presto 3 lanci GOOD
        store.add_trade({"mint": f"G{i:032d}", "ts": NOW - 86400 * 3 - i * 60 + 30, "trader": "LOYALWALLET",
                         "is_buy": True, "sol": 1, "tokens": 1, "mcap_sol": 40, "lane": "sol"})
    a = build_actor_stats(store)
    good = [c for c in a["creators"] if c["creator"] == "GOODCREATOR"][0]
    assert good["n_launches"] == 160 and good["grad_rate"] == 1.0
    assert store.q("SELECT COUNT(*) c FROM creator_stats")[0]["c"] >= 2
    loyal = [w for w in a["wallets"] if w["wallet"] == "LOYALWALLET"]
    assert loyal and loyal[0]["n_repeat_creators"] >= 1

def test_knn_twins(tmp_path):
    store = Store(str(tmp_path / "k.db"))
    for i in range(30):
        _launch(store, f"R{i:032d}", "C1", NOW - 86400 * 5 - i * 3600, RISER, bonded=True)
        _launch(store, f"D{i:032d}", "C2", NOW - 86400 * 5 - i * 3600, DEAD)
    _launch(store, f"Q{0:032d}", "C9", NOW - 1800, RISER, bonded=True)
    t = find_twins(store, f"Q{0:032d}", k=25)
    assert "error" not in t and t["med_peak"] > 2.5 and t["p2x"] > 0.8

def test_regime_and_autopsy(tmp_path):
    store = Store(str(tmp_path / "r.db"))
    for h in range(30, 2, -1):                           # 28 ore di lanci, meta' recenti graduano
        for i in range(25):
            created = NOW - h * 3600 - i * 60
            _launch(store, f"H{h}_{i:028d}", "C", created, RISER if h <= 10 else DEAD, bonded=(h <= 10))
    series = regime_series(store)
    assert series and current_regime(store)["regime"] in ("risk_on", "neutral", "toxic")
    for j, sp in enumerate([100.0, 150.0]):
        store.add_signal({"mint": f"G{j:032d}", "ts": NOW - 1000 + j * 500, "tier": "WATCH", "score": 0.5,
                          "price_sol": 1, "mcap_sol": 50, "age_s": 60, "sol_price": sp,
                          "gates": {}, "plan": {}, "features": {}})
    assert sol_benchmark(store) == pytest.approx(50.0)
    md = build_autopsy(store)
    assert "Autopsy" in md and "Benchmark" in md and "criteri di promozione" in md

def test_factory_antileakage_and_dedupe(tmp_path):
    store = Store(str(tmp_path / "f.db")); _seed_universe(store)
    f = run_factory(store)
    keys = [r["rule_key"] for r in f["rows"]]
    assert len(keys) == len(set(keys))                       # niente righe doppie
    cand = [r for r in f["rows"] if r["verdict"] == "CANDIDATE"]
    assert cand and all("ev60_pct" in r and "n60" in r for r in cand)

def test_autopsy_cli_writes_utf8(tmp_path, monkeypatch):
    monkeypatch.setenv("PR_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.chdir(tmp_path)
    from pumpradar.cli import _autopsy
    class A: send = False
    _autopsy(A())
    files = list((tmp_path / "reports").glob("autopsy-*.md"))
    assert files and "Autopsy" in files[0].read_text(encoding="utf-8")
