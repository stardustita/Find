"""Taratura 2026-11 sui dati reali dell'utente (528 token, 24 posizioni curva,
win-rate 0%): gli ingressi inseguivano i massimi. Questi test bloccano le regressioni."""
import time
from pumpradar.agents.exit import ExitAgent
from pumpradar.agents.scorer import ScorerAgent
from pumpradar.settings import Settings
from pumpradar.state import TokenState
from pumpradar.store import Store

def cfg(tmp_path):
    s = Settings(); s.db_path = str(tmp_path / "t.db"); return s

def good_features():
    return {
        "age_s": 60, "risk_engineered": 0, "curve_progress": 0.25, "unique_buyers_life": 20,
        "burst_300ms_share": 0.1, "single_token_wallet_share": 0.2, "risk_sell_pressure_30s": 0.8,
        "dev_hold_pct": 0.05, "risk_clone_image": 0, "buy_sol_30s": 1.2, "risk_distribution": 0,
        "lane_sol": 1, "sol_per_s_30s": 0.30, "buy_sell_ratio_life": 5.0, "repeat_buyer_share": 0.3,
        "retail_share": 0.7, "nar_social_score": 1.0, "nar_buzz_hits": 2, "smart_share_buyers": 0.2,
        "cohort_cosine_max": 0.1, "creator_bonded_rate": 0.4, "creator_known": 1, "buyer_growth": 1.5,
        "risk_junk_name": 0, "nar_symbol_random_pen": 0, "dev_sold_flag": 0, "ctx_congestion": 0.1,
        "top1_buy_share": 0.2, "max_slot_sol_share": 0.1, "mcap_sol": 80.0,
        "mcap_ret_30s": 0.3, "flow_decel": 0.1,
    }

def test_good_token_can_enter(tmp_path):
    s = cfg(tmp_path); scorer = ScorerAgent(s, Store(s.db_path))
    d = scorer.decide(TokenState(mint="M" * 32), good_features(), 150)
    assert d["tier"] in ("ENTRY", "STRONG") and d["plan"], d["gates"]

def test_late_curve_and_big_mcap_never_enter(tmp_path):
    s = cfg(tmp_path); scorer = ScorerAgent(s, Store(s.db_path)); st = TokenState(mint="M" * 32)
    F = good_features(); F["curve_progress"] = 0.65
    d = scorer.decide(st, F, 150)
    assert d["tier"] in ("WATCH", "NONE") and not d["plan"] and not d["gates"]["entry_window"]
    F = good_features(); F["mcap_sol"] = 260.0
    d = scorer.decide(st, F, 150)
    assert d["tier"] in ("WATCH", "NONE") and not d["gates"]["entry_mcap_cap"]

def test_vertical_spike_and_exhausted_flow_blocked(tmp_path):
    s = cfg(tmp_path); scorer = ScorerAgent(s, Store(s.db_path)); st = TokenState(mint="M" * 32)
    F = good_features(); F["mcap_ret_30s"] = 1.6   # +160% in 30s: stai inseguendo
    d = scorer.decide(st, F, 150)
    assert d["tier"] in ("WATCH", "NONE") and not d["gates"]["not_chasing"]
    F = good_features(); F["flow_decel"] = 0.8; F["risk_sell_pressure_30s"] = 1.5
    d = scorer.decide(st, F, 150)
    assert d["tier"] in ("WATCH", "NONE") and not d["gates"]["flow_not_exhausted"]

def test_exit_breakeven_and_dead_token(tmp_path):
    s = cfg(tmp_path); store = Store(s.db_path); ex = ExitAgent(s, store)
    pid = ex.open_position("M" * 32, 1, 100.0, 1.0)
    store.execute("UPDATE positions SET peak_mcap=135.0 WHERE id=?", (pid,))
    pos = store.one("SELECT * FROM positions WHERE id=?", (pid,))
    st = TokenState(mint="M" * 32, mcap_sol=101.0); st.last_ts = time.time()
    res = ex.evaluate(pos, st, {})
    assert res and res[0] == "CLOSE" and "pareggio" in res[1]
    pid2 = ex.open_position("N" * 32, 1, 100.0, 1.0)
    pos2 = store.one("SELECT * FROM positions WHERE id=?", (pid2,))
    st2 = TokenState(mint="N" * 32, mcap_sol=95.0); st2.last_ts = time.time() - 120
    res = ex.evaluate(pos2, st2, {})
    assert res and res[0] == "CLOSE" and "inattivo" in res[1]
