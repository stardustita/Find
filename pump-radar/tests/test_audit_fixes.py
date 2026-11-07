"""Regressioni per i bug trovati in audit (2026-11): prezzi Jupiter, feature
acquirenti sempre a zero, PnL residuo dopo scaletta, backtest dal segnale."""
import time
import pytest
from pumpradar.agents.curve import CurveAgent
from pumpradar.agents.exit import ExitAgent
from pumpradar.ingest.enrich import Enricher, SOL_MINT
from pumpradar.runner import GradState, PostGradAgent, RunnerBook
from pumpradar.settings import Settings
from pumpradar.state import TokenState
from pumpradar.store import Store


def cfg(tmp_path):
    s = Settings(); s.db_path = str(tmp_path / "t.db"); return s

# ---------- Jupiter: la risposta e' {"data": {mint: {...}}} ----------
def test_jupiter_nested_data_unwrapped(tmp_path):
    import asyncio
    e = Enricher(cfg(tmp_path), None)
    async def fake(url, params=None):
        return {"data": {SOL_MINT: {"usdPrice": 200.0}}}
    e._get_json = fake
    assert asyncio.run(e.refresh_sol_price()) == 200.0 and e.sol_price == 200.0
    assert asyncio.run(e.prices_usd([SOL_MINT])) == {SOL_MINT: 200.0}

# ---------- feature acquirenti: finestre sovrapposte davano sempre 0 ----------
def test_curve_new_buyers_and_growth():
    now = time.time()
    st = TokenState(mint="M" * 32, created_at=now - 120, lane="sol", rtok=700e6)
    def tr(ts, trader):
        st.observe({"ts": ts, "trader": trader, "is_buy": True, "sol": 0.2, "tokens": 1e5,
                    "vsol": 40.0, "vtok": 9e8, "mcap_sol": 44.0, "slot": 1, "lane": "sol"})
    tr(now - 50, "A"); tr(now - 48, "B")          # finestra precedente (30-60s fa)
    tr(now - 5, "A"); tr(now - 4, "C"); tr(now - 3, "D")  # ultimi 30s
    F = CurveAgent().features(st)
    assert F["new_buyers_30s"] == 2               # C e D sono nuovi, A no
    assert F["buyer_growth"] == pytest.approx(1.5)

def test_runner_buyer_growth():
    now = time.time()
    st = GradState(pool="P" * 32, base_mint="M" * 32, created_at=now - 1200)
    st.price, st.liq_sol, st.mcap_sol, st.init_mcap_sol, st.peak_mcap, st.last_ts = 1.0, 90.0, 450.0, 411.0, 450.0, now
    def rec(ts, user):
        st.trades.append({"ts": ts, "user": user, "is_buy": True, "sol": 0.2, "tokens": 1.0, "price": 1.0, "mcap": 450.0, "liq": 90.0})
    rec(now - 800, "u1"); rec(now - 700, "u2")                    # finestra precedente
    rec(now - 100, "u2"); rec(now - 90, "u3"); rec(now - 80, "u4"); rec(now - 70, "u5")
    F = PostGradAgent().features(st)
    assert F["pg_new_buyers_5m"] == 3
    assert F["pg_buyer_growth"] == pytest.approx(2.0)

# ---------- PnL: la CLOSE dopo la scaletta vale solo sul residuo ----------
def test_curve_close_counts_only_residual(tmp_path):
    s = cfg(tmp_path); store = Store(s.db_path); ex = ExitAgent(s, store)
    pid = ex.open_position("M" * 32, 1, 100.0, 1.0)
    st = TokenState(mint="M" * 32, mcap_sol=200.0)
    pos = store.one("SELECT * FROM positions WHERE id=?", (pid,))
    r1 = ex.apply(pos, "SELL", "target 1.8x", 0.25, st)
    pos = store.one("SELECT * FROM positions WHERE id=?", (pid,))
    r2 = ex.apply(pos, "CLOSE", "trailing", 1.0, st)
    row = store.one("SELECT * FROM positions WHERE id=?", (pid,))
    expected = 0.10 * (1.0 - 0.17)  # 2x netto costi sull'intera size, una sola volta
    assert r1["pnl_sol"] == pytest.approx(0.02075, abs=1e-4)
    assert r2["pnl_sol"] == pytest.approx(0.06225, abs=1e-4)
    assert row["pnl_sol"] == pytest.approx(expected, abs=1e-4) and row["status"] == "closed"

def test_runner_close_counts_only_residual(tmp_path):
    s = cfg(tmp_path); store = Store(s.db_path); book = RunnerBook(s, store)
    st = GradState(pool="P" * 32, base_mint="M" * 32); st.price = 1.0
    pid = book.open_position(st, 1, 100.0, 90.0)
    st.mcap_sol = 200.0
    pos = store.one("SELECT * FROM positions WHERE id=?", (pid,))
    book.apply(pos, "SELL", "target 2x", 0.20, st)
    pos = store.one("SELECT * FROM positions WHERE id=?", (pid,))
    book.apply(pos, "CLOSE", "trailing", 1.0, st)
    row = store.one("SELECT * FROM positions WHERE id=?", (pid,))
    assert row["pnl_sol"] == pytest.approx(0.15 * (1.0 - 0.156), abs=1e-3) and row["status"] == "closed"

# ---------- backtest: i picchi PRIMA del segnale non contano ----------
def test_backtest_is_signal_relative(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PR_DB_PATH", str(tmp_path / "bt.db"))
    from pumpradar.cli import _backtest
    store = Store(str(tmp_path / "bt.db")); t0 = time.time() - 5000; mint = "B" * 32
    store.upsert_token({"mint": mint, "name": "B", "symbol": "B", "uri": "", "creator": "d",
                        "created_at": t0, "first_seen": t0, "init_sol": 0, "init_mcap_sol": 100,
                        "mayhem": 0, "pool": "pump", "state": "dead", "last_ts": t0, "creator_sig": None,
                        "quote_mint": "SOL", "lane": "sol"})
    store.add_trade({"mint": mint, "ts": t0 + 50, "trader": "w", "is_buy": True, "sol": 1, "tokens": 1,
                     "mcap_sol": 500.0, "lane": "sol"})                      # picco pre-segnale: ignorato
    sid = store.add_signal({"mint": mint, "ts": t0 + 100, "tier": "ENTRY", "score": 0.5, "price_sol": 1,
                            "mcap_sol": 100.0, "age_s": 100, "sol_price": 150, "gates": {}, "plan": {}, "features": {}})
    store.add_trade({"mint": mint, "ts": t0 + 300, "trader": "w", "is_buy": True, "sol": 1, "tokens": 1,
                     "mcap_sol": 190.0, "lane": "sol"})                      # +90% dopo il segnale
    _backtest(None)
    out = capsys.readouterr().out
    assert "hit15=1" in out and "1.90x" in out and "5.00x" not in out

# ---------- varie di robustezza ----------
def test_upsert_mint_only_and_local_dashboard(tmp_path):
    store = Store(str(tmp_path / "u.db")); store.upsert_token({"mint": "Z" * 32})
    assert store.one("SELECT mint FROM tokens WHERE mint=?", ("Z" * 32,)) is not None
    assert Settings().api_host == "127.0.0.1"

def test_api_positions_shows_current_not_peak(tmp_path):
    import json, threading, urllib.request
    from pumpradar.orchestrator import Orchestrator
    from pumpradar.api.server import build_server
    s = cfg(tmp_path); orch = Orchestrator(s)
    mint = "A" * 32
    orch.store.execute("INSERT INTO positions(mint,signal_id,opened_ts,entry_mcap,entry_price,size_sol,status,peak_mcap,kind) VALUES(?,1,?,100.0,1.0,0.1,'open',300.0,'curve')", (mint, time.time()))
    orch.states[mint] = TokenState(mint=mint, mcap_sol=150.0)
    server = build_server(orch, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/api/positions", timeout=5) as r:
            rows = json.loads(r.read())
        assert rows and rows[0]["mult"] == pytest.approx(1.5)  # corrente, non picco 3.0
    finally:
        server.shutdown()

def test_dashboard_falls_back_to_free_port(tmp_path):
    import socket
    from pumpradar.cli import _start_dashboard
    from pumpradar.orchestrator import Orchestrator
    s = cfg(tmp_path)
    blocker = socket.socket(); blocker.bind(("127.0.0.1", 0)); blocker.listen(1)
    s.api_port = blocker.getsockname()[1]; s.api_host = "127.0.0.1"
    orch = Orchestrator(s)
    server, port = _start_dashboard(orch, s, "test")
    try:
        assert server is not None and port == s.api_port + 1
    finally:
        if server: server.shutdown()
        blocker.close()

def test_dashboard_tokens_link_to_pumpfun():
    from pumpradar.api.server import HTML
    assert "https://pump.fun/coin/" in HTML and 'target="_blank"' in HTML
    assert HTML.count("lnk(r.mint") == 2 and "lnk(r.base_mint" in HTML  # segnali curva + posizioni + PG
