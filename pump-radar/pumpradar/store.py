from __future__ import annotations
import json, sqlite3, threading, time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS tokens(
 mint TEXT PRIMARY KEY, name TEXT, symbol TEXT, uri TEXT, creator TEXT,
 created_at REAL, first_seen REAL, init_sol REAL, init_mcap_sol REAL,
 mayhem INTEGER DEFAULT 0, pool TEXT, state TEXT DEFAULT 'new', last_ts REAL,
 bonded_at REAL, dead_at REAL, meta_json TEXT, meta_name TEXT, meta_symbol TEXT,
 meta_desc TEXT, meta_twitter TEXT, meta_telegram TEXT, meta_website TEXT,
 image_hash TEXT, creator_sig TEXT, quote_mint TEXT, lane TEXT);
CREATE INDEX IF NOT EXISTS ix_tokens_created ON tokens(created_at);
CREATE INDEX IF NOT EXISTS ix_tokens_state ON tokens(state);
CREATE INDEX IF NOT EXISTS ix_tokens_creator ON tokens(creator);
CREATE TABLE IF NOT EXISTS trades(
 id INTEGER PRIMARY KEY AUTOINCREMENT, mint TEXT, ts REAL, tx TEXT, trader TEXT,
 is_buy INTEGER, sol REAL, tokens REAL, vsol REAL, vtok REAL, rsol REAL, rtok REAL,
 mcap_sol REAL, slot INTEGER, source TEXT, lane TEXT, quote_mint TEXT);
CREATE INDEX IF NOT EXISTS ix_trades_mint_ts ON trades(mint,ts);
CREATE INDEX IF NOT EXISTS ix_trades_trader ON trades(trader);
CREATE TABLE IF NOT EXISTS wallets(
 addr TEXT PRIMARY KEY, first_seen REAL, last_seen REAL, n_trades INTEGER DEFAULT 0,
 n_buys INTEGER DEFAULT 0, n_sells INTEGER DEFAULT 0, sol_bought REAL DEFAULT 0,
 sol_sold REAL DEFAULT 0, n_tokens INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
 score REAL DEFAULT 0.5, is_bot INTEGER DEFAULT 0, cluster TEXT, funded_by TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS wallet_tokens(
 wallet TEXT, mint TEXT, bought REAL DEFAULT 0, sold REAL DEFAULT 0, n INTEGER DEFAULT 0,
 first_ts REAL, last_ts REAL, PRIMARY KEY(wallet,mint));
CREATE INDEX IF NOT EXISTS ix_wt_mint ON wallet_tokens(mint);
CREATE TABLE IF NOT EXISTS snapshots(
 id INTEGER PRIMARY KEY AUTOINCREMENT, mint TEXT, ts REAL, age_s REAL, mcap_sol REAL,
 features TEXT, score REAL, p_bond REAL, p_2x REAL, p_5x REAL);
CREATE INDEX IF NOT EXISTS ix_snap_mint ON snapshots(mint,ts);
CREATE TABLE IF NOT EXISTS signals(
 id INTEGER PRIMARY KEY AUTOINCREMENT, mint TEXT, ts REAL, tier TEXT, score REAL,
 price_sol REAL, mcap_sol REAL, age_s REAL, sol_price REAL, gates TEXT, plan TEXT,
 features TEXT, notified INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_signals_mint ON signals(mint,ts);
CREATE TABLE IF NOT EXISTS outcomes(
 mint TEXT PRIMARY KEY, signal_id INTEGER, entry_ts REAL, entry_mcap REAL,
 max_mult_5m REAL, max_mult_15m REAL, max_mult_60m REAL, max_mult_6h REAL,
 max_mult_24h REAL, min_mult REAL, bonded INTEGER DEFAULT 0,
 engineered INTEGER DEFAULT 0, peak_mcap REAL, labeled_at REAL);
CREATE TABLE IF NOT EXISTS positions(
 id INTEGER PRIMARY KEY AUTOINCREMENT, mint TEXT, signal_id INTEGER,
 opened_ts REAL, closed_ts REAL, entry_mcap REAL, exit_mcap REAL,
 entry_price REAL, size_sol REAL, tokens REAL, pnl_sol REAL, pnl_pct REAL,
 status TEXT, reason TEXT, peak_mcap REAL, kind TEXT DEFAULT 'curve', pool TEXT);
CREATE TABLE IF NOT EXISTS token_stats(
 mint TEXT PRIMARY KEY, n_buys INTEGER, n_sells INTEGER, buy_sol REAL, sell_sol REAL,
 n_buyers INTEGER, peak_mcap REAL, last_mcap REAL, lifetime_s REAL, state TEXT, lane TEXT);
CREATE TABLE IF NOT EXISTS pools(
 pool TEXT PRIMARY KEY, base_mint TEXT, quote_mint TEXT, bdec INTEGER, qdec INTEGER,
 supply REAL, creator TEXT, created_ts REAL, init_liq_sol REAL, init_mcap_sol REAL,
 mayhem INTEGER DEFAULT 0, state TEXT DEFAULT 'new', last_ts REAL, peak_mcap REAL);
CREATE INDEX IF NOT EXISTS ix_pools_base ON pools(base_mint);
CREATE TABLE IF NOT EXISTS amm_trades(
 id INTEGER PRIMARY KEY AUTOINCREMENT, pool TEXT, ts REAL, tx TEXT, trader TEXT,
 is_buy INTEGER, sol REAL, tokens REAL, price REAL, mcap_sol REAL, liq_sol REAL);
CREATE INDEX IF NOT EXISTS ix_amm_pool_ts ON amm_trades(pool,ts);
CREATE TABLE IF NOT EXISTS pg_signals(
 id INTEGER PRIMARY KEY AUTOINCREMENT, pool TEXT, base_mint TEXT, ts REAL, tier TEXT,
 score REAL, price REAL, mcap_sol REAL, liq_sol REAL, age_s REAL, gates TEXT, plan TEXT, features TEXT);
CREATE INDEX IF NOT EXISTS ix_pg_mint ON pg_signals(base_mint,ts);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""

class Store:
    def __init__(self, path: str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self):
        wanted = {
            "tokens": {"quote_mint":"TEXT", "lane":"TEXT"},
            "trades": {"rsol":"REAL", "rtok":"REAL", "lane":"TEXT", "quote_mint":"TEXT"},
            "positions": {"kind":"TEXT DEFAULT 'curve'", "pool":"TEXT"},
        }
        for table, cols in wanted.items():
            existing = {r[1] for r in self._conn.execute(f"PRAGMA table_info({table})")}
            for col, typ in cols.items():
                if col not in existing:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")

    def conn(self):
        return self._conn

    def execute(self, sql: str, args: Iterable = ()):
        with self._lock:
            cur = self._conn.execute(sql, tuple(args))
            self._conn.commit()
            return cur

    def q(self, sql: str, args: Iterable = ()):
        with self._lock:
            return self._conn.execute(sql, tuple(args)).fetchall()

    def one(self, sql: str, args: Iterable = ()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def upsert_token(self, t: dict[str, Any]):
        cols = list(t.keys())
        if not cols: return
        if len(cols) == 1:
            self.execute(f"INSERT OR IGNORE INTO tokens ({cols[0]}) VALUES (?)", [t[cols[0]]]); return
        sql = f"INSERT INTO tokens ({','.join(cols)}) VALUES ({','.join('?'*len(cols))}) ON CONFLICT(mint) DO UPDATE SET " + ",".join(f"{c}=excluded.{c}" for c in cols if c != "mint")
        self.execute(sql, [t[c] for c in cols])

    def add_trade(self, e: dict[str, Any]):
        with self._lock:
            self._conn.execute(
                """INSERT INTO trades(mint,ts,tx,trader,is_buy,sol,tokens,vsol,vtok,rsol,rtok,mcap_sol,slot,source,lane,quote_mint)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (e.get("mint"), e.get("ts", time.time()), e.get("tx"), e.get("trader"),
                 1 if e.get("is_buy") else 0, float(e.get("sol") or 0), float(e.get("tokens") or 0),
                 e.get("vsol"), e.get("vtok"), e.get("rsol"), e.get("rtok"), e.get("mcap_sol"),
                 e.get("slot"), e.get("source"), e.get("lane"), e.get("quote_mint")))
            trader = e.get("trader")
            if trader:
                ts = float(e.get("ts") or time.time()); sol = float(e.get("sol") or 0); buy = bool(e.get("is_buy"))
                self._conn.execute(
                    """INSERT INTO wallets(addr,first_seen,last_seen,n_trades,n_buys,n_sells,sol_bought,sol_sold,n_tokens)
                       VALUES(?,?,?,1,?,?,?,?,0) ON CONFLICT(addr) DO UPDATE SET last_seen=excluded.last_seen,
                       n_trades=n_trades+1,n_buys=n_buys+excluded.n_buys,n_sells=n_sells+excluded.n_sells,
                       sol_bought=sol_bought+excluded.sol_bought,sol_sold=sol_sold+excluded.sol_sold""",
                    (trader, ts, ts, 1 if buy else 0, 0 if buy else 1, sol if buy else 0, 0 if buy else sol))
                self._conn.execute(
                    """INSERT INTO wallet_tokens(wallet,mint,bought,sold,n,first_ts,last_ts) VALUES(?,?,?,?,1,?,?)
                       ON CONFLICT(wallet,mint) DO UPDATE SET bought=bought+excluded.bought,sold=sold+excluded.sold,n=n+1,last_ts=excluded.last_ts""",
                    (trader, e.get("mint"), sol if buy else 0, 0 if buy else sol, ts, ts))
                n = self._conn.execute("SELECT COUNT(*) FROM wallet_tokens WHERE wallet=?", (trader,)).fetchone()[0]
                self._conn.execute("UPDATE wallets SET n_tokens=? WHERE addr=?", (n, trader))
            self._conn.commit()

    def add_snapshot(self, mint, ts, age_s, mcap_sol, features, score, p_bond=None, p2x=None, p5x=None):
        self.execute("INSERT INTO snapshots(mint,ts,age_s,mcap_sol,features,score,p_bond,p_2x,p_5x) VALUES(?,?,?,?,?,?,?,?,?)",
                     (mint, ts, age_s, mcap_sol, json.dumps(features), score, p_bond, p2x, p5x))

    def add_signal(self, s: dict[str, Any]) -> int:
        cur = self.execute("""INSERT INTO signals(mint,ts,tier,score,price_sol,mcap_sol,age_s,sol_price,gates,plan,features)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (s["mint"], s["ts"], s["tier"], s["score"], s.get("price_sol"), s.get("mcap_sol"), s.get("age_s"), s.get("sol_price"), json.dumps(s.get("gates", {})), json.dumps(s.get("plan", {})), json.dumps(s.get("features", {}))))
        return int(cur.lastrowid)

    def add_pg_signal(self, s: dict[str, Any]) -> int:
        cur = self.execute("""INSERT INTO pg_signals(pool,base_mint,ts,tier,score,price,mcap_sol,liq_sol,age_s,gates,plan,features)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (s["pool"], s["base_mint"], s["ts"], s["tier"], s["score"], s.get("price"), s.get("mcap_sol"), s.get("liq_sol"), s.get("age_s"), json.dumps(s.get("gates", {})), json.dumps(s.get("plan", {})), json.dumps(s.get("features", {}))))
        return int(cur.lastrowid)

    def set_state(self, mint: str, state: str, ts: float | None = None):
        ts = ts or time.time()
        if state == "bonded":
            self.execute("UPDATE tokens SET state=?, bonded_at=?, last_ts=? WHERE mint=?", (state, ts, ts, mint))
        elif state == "dead":
            self.execute("UPDATE tokens SET state=?, dead_at=?, last_ts=? WHERE mint=?", (state, ts, ts, mint))
        else:
            self.execute("UPDATE tokens SET state=?, last_ts=? WHERE mint=?", (state, ts, mint))

    def kv_set(self, k: str, v: Any):
        self.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v if isinstance(v, str) else json.dumps(v)))

    def kv_get(self, k: str, default=None):
        r = self.one("SELECT v FROM kv WHERE k=?", (k,))
        if not r:
            return default
        try:
            return json.loads(r["v"])
        except Exception:
            return r["v"]

    def prune(self, snapshot_days: int = 14, trade_days: int = 45) -> dict:
        now = time.time()
        a = self.execute("DELETE FROM snapshots WHERE ts < ?", (now - snapshot_days*86400,)).rowcount
        b = self.execute("DELETE FROM trades WHERE ts < ?", (now - trade_days*86400,)).rowcount
        c = self.execute("DELETE FROM amm_trades WHERE ts < ?", (now - trade_days*86400,)).rowcount
        self.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return {"snapshots_deleted": a, "trades_deleted": b, "amm_trades_deleted": c}
