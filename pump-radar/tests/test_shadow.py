"""Fase 1+2: barre per tutti i lanci, rilevatori ombra, valutazione in analyze."""
import time
from pumpradar.orchestrator import Orchestrator
from pumpradar.runner import GradState
from pumpradar.settings import Settings
from pumpradar.shadow import pg_pullback_signal, second_leg_signal
from pumpradar.state import TokenState
from pumpradar.store import Store
from pumpradar.learning.analyze import analyze

def cfg(tmp_path):
    s = Settings(); s.db_path = str(tmp_path / "t.db"); return s

def test_second_leg_detector():
    now = time.time()
    st = TokenState(mint="M" * 32, created_at=now - 600, lane="sol")
    st.peak_mcap, st.min_mcap, st.mcap_sol, st.last_ts = 200.0, 28.0, 90.0, now
    for i in range(10):
        st.trades.append({"ts": now - 10, "trader": f"w{i}", "is_buy": True, "sol": 0.2, "mcap_sol": 90.0})
    F = {"age_s": 600, "mcap_sol": 90.0, "buy_sell_ratio_30s": 2.0, "mcap_ret_60s": 0.10,
         "risk_engineered": 0, "risk_distribution": 0}
    assert second_leg_signal(st, F, now) is not None
    st.mcap_sol = 190.0; F["mcap_sol"] = 190.0   # nessun drawdown: non e' una seconda gamba
    assert second_leg_signal(st, F, now) is None

def test_pg_pullback_detector():
    now = time.time()
    gs = GradState(pool="P" * 32, base_mint="M" * 32, created_at=now - 3600)
    F = {"pg_age_s": 3600, "pg_ath_mult": 3.0, "pg_drawdown_ath": 0.40, "pg_liq_sol": 40.0,
         "pg_unique_buyers_5m": 20, "pg_ret_1m": 0.03, "pg_turnover_5m": 0.4, "pg_creator_sold": 0}
    assert pg_pullback_signal(gs, F, now) is not None
    F["pg_drawdown_ath"] = 0.80                  # caduta libera, non pullback
    assert pg_pullback_signal(gs, F, now) is None

def test_bars_written_for_all_tokens(tmp_path):
    orch = Orchestrator(cfg(tmp_path))
    now = time.time()
    st = TokenState(mint="B" * 32, created_at=now - 100, lane="sol")
    orch.states[st.mint] = st
    for i in range(3):
        orch._update_bar(st, {"ts": now - 20, "trader": f"w{i}", "is_buy": True, "sol": 0.5, "mcap_sol": 40.0})
    orch._flush_bars()
    rows = orch.store.q("SELECT * FROM launch_bars WHERE mint=?", (st.mint,))
    assert len(rows) == 1 and rows[0]["n_trades"] == 3 and rows[0]["n_buyers"] == 3

def test_shadow_evaluation_in_analyze(tmp_path):
    store = Store(str(tmp_path / "s.db")); t0 = time.time() - 50000; mint = "S" * 32
    store.add_shadow("second_leg", "curve", mint, "", t0, 100.0, {"drawdown": 0.5})
    for j, m in enumerate([120.0, 190.0, 150.0]):
        store.add_trade({"mint": mint, "ts": t0 + 60 * (j + 1), "trader": "w", "is_buy": True,
                         "sol": 1, "tokens": 1, "mcap_sol": m, "lane": "sol"})
    d = analyze(store)
    assert "second_leg" in d["shadow"] and d["shadow"]["second_leg"]["n"] == 1
