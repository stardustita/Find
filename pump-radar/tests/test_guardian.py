"""Fase 5 — Guardiani: censore, sentinella, revisore."""
import time
from pumpradar.guardian import censor_check, format_guardian, serial_ruggers, tier_health
from pumpradar.state import TokenState
from pumpradar.store import Store

def _st(now, creator="CREATOROK", buyers=6, mcap=100.0, peak=110.0):
    st = TokenState(mint="G" * 32, created_at=now - 90, lane="sol", creator=creator)
    st.mcap_sol, st.peak_mcap, st.last_ts = mcap, peak, now
    for i in range(buyers):
        st.trades.append({"ts": now - 10, "trader": f"w{i}", "is_buy": True, "sol": 0.3, "mcap_sol": mcap})
    return st

def test_censor_pass_and_vetoes():
    now = time.time()
    F = {"mcap_sol": 100.0, "risk_engineered": 0, "risk_distribution": 0}
    assert censor_check(_st(now), F, now) == []
    assert "pochi_compratori_60s" in censor_check(_st(now, buyers=2), F, now)
    assert "gia_in_caduta" in censor_check(_st(now, mcap=60.0, peak=110.0), {**F, "mcap_sol": 60.0}, now)
    assert "creator_serial_rugger" in censor_check(_st(now, creator="RUG"), F, now, blacklist={"RUG"})
    assert "regime_toxic" in censor_check(_st(now), F, now, regime_label="toxic")

def test_sentinel_concentration():
    now = time.time()
    st = _st(now, buyers=3)
    st.trades = [{"ts": now - 80, "trader": "WHALE", "is_buy": True, "sol": 9.0, "mcap_sol": 50.0},
                 {"ts": now - 10, "trader": "w1", "is_buy": True, "sol": 0.5, "mcap_sol": 100.0},
                 {"ts": now - 10, "trader": "w2", "is_buy": True, "sol": 0.5, "mcap_sol": 100.0}]
    assert "concentrazione_sospetta" in censor_check(st, {"mcap_sol": 100.0}, now)

def test_serial_ruggers():
    sums = ([{"creator": "RUG", "lifespan_s": 100} for _ in range(12)]
            + [{"creator": "OK", "lifespan_s": 2000} for _ in range(12)]
            + [{"creator": "SMALL", "lifespan_s": 60} for _ in range(5)])
    assert serial_ruggers(sums) == {"RUG"}

def test_tier_health_demotes_losing_tier(tmp_path):
    store = Store(str(tmp_path / "g.db")); t0 = time.time() - 100000; mint = "L" * 32
    for i in range(60):
        ts = t0 + i * 1000
        store.add_signal({"mint": mint, "ts": ts, "tier": "STRONG", "score": 0.9, "price_sol": 1,
                          "mcap_sol": 100.0, "age_s": 60, "sol_price": 150, "gates": {}, "plan": {}, "features": {}})
        store.add_trade({"mint": mint, "ts": ts + 500, "trader": "w", "is_buy": True,
                         "sol": 1, "tokens": 1, "mcap_sol": 40.0, "lane": "sol"})
    h = tier_health(store)
    assert h["curve:STRONG"]["demote"] and h["curve:STRONG"]["ev_pct"] < -50
    assert "RETROCESSO" in format_guardian(set(), "neutral", h)
