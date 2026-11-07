"""Database storico: cattura profonda, schede lancio, barre pool, persistenza serie."""
import time
from pumpradar.orchestrator import Orchestrator
from pumpradar.runner import GradState
from pumpradar.settings import Settings
from pumpradar.state import TokenState
from pumpradar.store import Store

def _seed_launch(store, mint="F" * 32, creator="DEVWALLET", now=None):
    now = now or time.time()
    store.upsert_token({"mint": mint, "name": "T", "symbol": "T", "uri": "", "creator": creator,
                        "created_at": now - 3600, "first_seen": now - 3600, "init_sol": 3.0,
                        "init_mcap_sol": 30.0, "mayhem": 0, "pool": "pump", "state": "dead",
                        "last_ts": now, "creator_sig": None, "quote_mint": "SOL", "lane": "sol"})
    store.execute("UPDATE tokens SET bonded_at=? WHERE mint=?", (now - 3000, mint))
    store.add_bars([(mint, int(now - 3600 + o), "sol", 3, 2.0, 0.5, 4, m)
                    for o, m in [(0, 30.0), (300, 90.0), (900, 150.0), (1800, 60.0)]])
    # dev compra 2 SOL nei primi 60s; una balena il 70% del resto
    store.add_trade({"mint": mint, "ts": now - 3590, "trader": creator, "is_buy": True, "sol": 2.0, "tokens": 1, "mcap_sol": 31, "lane": "sol"})
    store.add_trade({"mint": mint, "ts": now - 3580, "trader": "WHALE", "is_buy": True, "sol": 7.0, "tokens": 1, "mcap_sol": 35, "lane": "sol"})
    store.add_trade({"mint": mint, "ts": now - 3500, "trader": "W2", "is_buy": True, "sol": 1.0, "tokens": 1, "mcap_sol": 50, "lane": "sol"})
    store.add_trade({"mint": mint, "ts": now - 3400, "trader": "W2", "is_buy": False, "sol": 1.2, "tokens": 1, "mcap_sol": 45, "lane": "sol"})
    return now

def test_launch_facts_complete(tmp_path):
    store = Store(str(tmp_path / "f.db")); _seed_launch(store)
    assert store.compute_launch_facts("F" * 32)
    f = store.q("SELECT * FROM launch_facts WHERE mint=?", ("F" * 32,))[0]
    assert f["graduated"] == 1 and f["peak_mult"] == 5.0 and f["uniq_buyers"] == 3
    assert f["dev_buy_60s"] == 2.0 and f["top1_share"] > 0.6 and f["creator_prior"] == 0
    assert store.backfill_launch_facts() == 0        # gia' schedata: idempotente

def test_backfill_counts(tmp_path):
    store = Store(str(tmp_path / "b.db")); _seed_launch(store)
    store.execute("DELETE FROM launch_facts")
    assert store.backfill_launch_facts() == 1

def test_persist_trade_window(tmp_path):
    s = Settings(); s.db_path = str(tmp_path / "p.db")
    orch = Orchestrator(s); now = time.time()
    st = TokenState(mint="P" * 32, created_at=now - 600, lane="sol"); st.state = "dead"
    assert orch._persist_trade(st, st.mint, {"ts": now}) is True          # morto ma entro 30 min
    st.created_at = now - 3600
    assert orch._persist_trade(st, st.mint, {"ts": now}) is False         # oltre la finestra
    st.state = "watch"
    assert orch._persist_trade(st, st.mint, {"ts": now}) is True          # watch: sempre

def test_pool_bars_and_series(tmp_path):
    s = Settings(); s.db_path = str(tmp_path / "pb.db")
    orch = Orchestrator(s); now = time.time()
    gs = GradState(pool="POOL" + "0" * 28, base_mint="B" * 32, created_at=now - 3600)
    orch._update_pool_bar(gs, {"ts": now - 120, "trader": "W", "is_buy": True, "sol": 2.0, "mcap_sol": 500, "liq_sol": 40})
    orch._flush_pool_bars()
    rows = orch.store.q("SELECT * FROM pool_bars")
    assert len(rows) == 1 and rows[0]["n_trades"] == 1 and rows[0]["n_buyers"] == 1
    orch.store.add_sol_price(now, 150.0); orch.store.add_sol_price(now, 151.0)
    assert orch.store.q("SELECT COUNT(*) c FROM sol_prices")[0]["c"] == 1
    orch.store.add_regime({"hour": int(now // 3600), "regime": "toxic", "grad_rate": 0.01, "baseline": 0.02, "n_launch": 100, "med_life_s": 60})
    assert orch.store.q("SELECT regime FROM regime_log")[0]["regime"] == "toxic"
    assert "pool_bars_deleted" in orch.store.prune()
