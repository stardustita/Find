"""Report 24h: analisi completa dei lanci recenti dal censimento."""
import time
from pumpradar.learning.dayreport import dayreport, format_dayreport
from pumpradar.store import Store

RISER = [(o, 30 + o * 0.3) for o in range(0, 901, 30)]
DEAD = [(0, 30.0), (30, 28.0), (60, 20.0)]

def _launch(store, mint, creator, created, path, bonded=False):
    store.upsert_token({"mint": mint, "name": "T", "symbol": "T", "uri": "", "creator": creator,
                        "created_at": created, "first_seen": created, "init_sol": 0,
                        "init_mcap_sol": path[0][1], "mayhem": 0, "pool": "pump", "state": "x",
                        "last_ts": created, "creator_sig": None, "quote_mint": "SOL", "lane": "sol"})
    if bonded:
        store.execute("UPDATE tokens SET bonded_at=? WHERE mint=?", (created + 600, mint))
    store.add_bars([(mint, int(created + off), "sol", 3, 2.0, 0.5, 4, m) for off, m in path])

def test_dayreport_window_and_sections(tmp_path):
    store = Store(str(tmp_path / "d.db")); now = time.time()
    _launch(store, "R" * 32, "C1", now - 3600, RISER, bonded=True)
    _launch(store, "S" * 32, "C2", now - 7200, RISER)
    _launch(store, "D" * 32, "C3", now - 1800, DEAD)
    _launch(store, "O" * 32, "C1", now - 90000, RISER, bonded=True)   # fuori finestra 24h
    store.add_trade({"mint": "R" * 32, "ts": now - 3540, "trader": "W1", "is_buy": True,
                     "sol": 1.0, "tokens": 1, "mcap_sol": 40, "lane": "sol"})
    store.execute("INSERT OR IGNORE INTO wallets(addr,first_seen,last_seen) VALUES('W1',?,?)", (now - 100, now))
    store.execute("UPDATE wallets SET first_seen=? WHERE addr='W1'", (now - 100,))
    d = dayreport(store, hours=24, now=now)
    assert d["n_launches"] == 3 and d["graduated"] == 1
    assert d["peak"]["ge10"] >= 1 and d["top_peak"][0]["mint"] == "R" * 32
    assert d["wallets"]["unique_traders"] >= 1 and d["wallets"]["new_wallets"] == 1
    txt = format_dayreport(d)
    assert "REPORT ULTIME 24H" in txt and "Visualizzatori" in txt and "copertura" in txt

def test_dayreport_empty(tmp_path):
    store = Store(str(tmp_path / "e.db"))
    assert "nessun lancio" in format_dayreport(dayreport(store, hours=24))
