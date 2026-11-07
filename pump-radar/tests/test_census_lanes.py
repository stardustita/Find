"""Bug volumi cross (2026-11-07): gli importi della corsia cross sono nella
valuta di quotazione, NON in SOL. Mai sommarli ai SOL: ne' nei riassunti,
ne' nel report 24h, ne' nelle schede lancio. Regressione permanente."""
import time
from pumpradar.learning.census import launch_summaries
from pumpradar.learning.dayreport import dayreport, format_dayreport
from pumpradar.store import Store

def _seed(store, mint, lane, buy, now, mcap=50.0):
    store.add_bars([(mint, int(now), lane, 3, buy, 1.0, 2, mcap),
                    (mint, int(now) + 30, lane, 2, buy, 0.5, 1, mcap)])

def test_buy60_excludes_cross_quote(tmp_path):
    store = Store(str(tmp_path / "l.db")); now = time.time() - 7200
    _seed(store, "S" * 32, "sol", 10.0, now)
    _seed(store, "X" * 32, "cross", 999999.0, now)
    by = {r["mint"]: r for r in launch_summaries(store)}
    assert by["S" * 32]["buy60"] == 20.0                      # SOL veri (2 barre)
    assert by["X" * 32]["buy60"] == 0.0                       # quote, non SOL
    assert by["X" * 32]["buy60q"] == 1999998.0                # tenuto a parte

def test_dayreport_volumes_separated(tmp_path):
    store = Store(str(tmp_path / "d.db")); now = time.time()
    _seed(store, "S" * 32, "sol", 10.0, now - 3600)
    _seed(store, "X" * 32, "cross", 999999.0, now - 3600)
    d = dayreport(store, hours=24, now=now)
    assert d["vol"]["total_buy_sol"] == 20.0
    assert d["vol"]["cross_tokens"] == 1 and d["vol"]["total_buy_quote"] == 1999998.0
    txt = format_dayreport(d)
    assert "VOLUMI cross" in txt and "NON SOL" in txt and "1999998" in txt

def _cross_token(store, now):
    mint = "X" * 32
    store.upsert_token({"mint": mint, "name": "T", "symbol": "T", "uri": "", "creator": "DEV",
                        "created_at": now - 3600, "first_seen": now - 3600, "init_sol": 0,
                        "init_mcap_sol": 50.0, "mayhem": 0, "pool": "pump", "state": "dead",
                        "last_ts": now, "creator_sig": None, "quote_mint": "PUMP", "lane": "cross"})
    store.add_bars([(mint, int(now - 3600), "cross", 3, 5.0, 1.0, 2, 50.0)])
    store.add_trade({"mint": mint, "ts": now - 3500, "trader": "WHALE", "is_buy": True,
                     "sol": 900000.0, "tokens": 1, "mcap_sol": 50, "lane": "cross"})
    return mint

def test_launch_facts_cross_money_zeroed(tmp_path):
    store = Store(str(tmp_path / "f.db")); now = time.time()
    mint = _cross_token(store, now)
    assert store.compute_launch_facts(mint)
    f = store.q("SELECT * FROM launch_facts WHERE mint=?", (mint,))[0]
    assert f["buy_sol"] == 0.0 and f["n_trades"] == 1 and f["lane"] == "cross"

def test_backfill_heals_polluted_cross_facts(tmp_path):
    store = Store(str(tmp_path / "h.db")); now = time.time()
    mint = _cross_token(store, now)
    assert store.compute_launch_facts(mint)
    # simula una scheda scritta PRIMA della correzione (quote travestiti da SOL)
    store.execute("UPDATE launch_facts SET buy_sol=900000.0 WHERE mint=?", (mint,))
    assert store.backfill_launch_facts() >= 1
    f = store.q("SELECT buy_sol, n_trades FROM launch_facts WHERE mint=?", (mint,))[0]
    assert f["buy_sol"] == 0.0 and f["n_trades"] == 1
