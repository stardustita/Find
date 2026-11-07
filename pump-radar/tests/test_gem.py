"""Ricostruzione: motore GEMME (slancio intra-minuto) ed emissione censurata."""
import asyncio
import time
from pumpradar.gem import slancio_signal
from pumpradar.orchestrator import Orchestrator
from pumpradar.settings import Settings
from pumpradar.state import TokenState

def _exploding(now, creator="OKCREATOR"):
    st = TokenState(mint="M" * 32, created_at=now - 40, lane="sol", creator=creator)
    st.min_mcap, st.peak_mcap, st.mcap_sol, st.last_ts = 30.0, 52.0, 50.0, now
    series = [(now - 40, 30.0), (now - 20, 38.0), (now - 10, 46.0), (now - 2, 50.0)]
    for ts, m in series:
        st.trades.append({"ts": ts, "trader": "w0", "is_buy": True, "sol": 0.4, "mcap_sol": m})
    for i in range(6):
        st.trades.append({"ts": now - 5, "trader": f"b{i}", "is_buy": True, "sol": 0.3, "mcap_sol": 50.0})
    return st

F = {"age_s": 40, "mcap_sol": 50.0, "buy_sell_ratio_30s": 2.0, "risk_engineered": 0, "risk_distribution": 0}

def test_slancio_fires_and_vetoes():
    now = time.time()
    ctx = slancio_signal(_exploding(now), F, now)
    assert ctx is not None and ctx["ret_from_min"] > 0.25 and ctx["buyers_15s"] >= 5
    st = _exploding(now); st.mcap_sol = 34.0            # solo +13% dal minimo
    assert slancio_signal(st, {**F, "mcap_sol": 34.0}, now) is None
    st = _exploding(now); st.peak_mcap = 100.0          # gia' ritracciato del 50%
    assert slancio_signal(st, F, now) is None
    st = _exploding(now)                                # momentum piatto negli ultimi 15s
    for t in st.trades: t["mcap_sol"] = 50.0
    assert slancio_signal(st, F, now) is None

def _orch(tmp_path):
    s = Settings(); s.db_path = str(tmp_path / "g.db")
    return Orchestrator(s)

def test_gem_emit_censored_by_blacklist(tmp_path):
    orch = _orch(tmp_path); now = time.time()
    st = _exploding(now, creator="RUGCREATOR"); orch.states[st.mint] = st
    orch._blacklist = {"RUGCREATOR"}
    ctx = slancio_signal(st, F, now)
    asyncio.run(orch._gem_emit(st, F, ctx, now))
    assert orch.stats["gem_censored"] >= 1
    assert orch.store.q("SELECT COUNT(*) c FROM signals WHERE tier='SLANCIO'")[0]["c"] == 0

def test_gem_emit_records_signal(tmp_path):
    orch = _orch(tmp_path); now = time.time()
    st = _exploding(now); orch.states[st.mint] = st
    ctx = slancio_signal(st, F, now)
    asyncio.run(orch._gem_emit(st, F, ctx, now))
    rows = orch.store.q("SELECT tier,gates FROM signals WHERE tier='SLANCIO'")
    assert len(rows) == 1 and "slancio_intra_minuto" in rows[0]["gates"]
