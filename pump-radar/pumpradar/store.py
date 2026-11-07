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
CREATE TABLE IF NOT EXISTS launch_bars(
 mint TEXT, bucket INTEGER, lane TEXT, n_trades INTEGER, buy_sol REAL, sell_sol REAL,
 n_buyers INTEGER, mcap_sol REAL, PRIMARY KEY(mint, bucket));
CREATE TABLE IF NOT EXISTS shadow_signals(
 id INTEGER PRIMARY KEY AUTOINCREMENT, strategy TEXT, kind TEXT, mint TEXT, pool TEXT,
 ts REAL, entry_mcap REAL, context TEXT);
CREATE INDEX IF NOT EXISTS ix_shadow_strategy ON shadow_signals(strategy, ts);
CREATE TABLE IF NOT EXISTS hypotheses(
 id INTEGER PRIMARY KEY AUTOINCREMENT, rule_key TEXT UNIQUE, created_ts REAL,
 dimension TEXT, cohort TEXT, n INTEGER, ev_pct REAL, med_pct REAL, pos_share REAL,
 baseline_ev_pct REAL, z REAL, verdict TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS creator_stats(
 creator TEXT PRIMARY KEY, n_launches INTEGER, n_grad INTEGER, grad_rate REAL,
 med_peak REAL, fast_dead_share REAL, last_ts REAL, updated REAL);
CREATE TABLE IF NOT EXISTS wallet_flags(
 wallet TEXT PRIMARY KEY, n_tokens INTEGER, n_repeat_creators INTEGER,
 max_creator_launches INTEGER, bonded_share REAL, updated REAL);
CREATE TABLE IF NOT EXISTS launch_facts(
 mint TEXT PRIMARY KEY, creator TEXT, created_at REAL, lane TEXT, graduated INTEGER DEFAULT 0,
 first_mcap REAL, peak_mcap REAL, t_peak_s REAL, last_mcap REAL, lifespan_s REAL,
 n_trades INTEGER, buy_sol REAL, sell_sol REAL, uniq_buyers INTEGER, uniq_sellers INTEGER,
 top1_share REAL, dev_buy_60s REAL, snipe_share5s REAL, peak_mult REAL, last_mult REAL,
 creator_prior INTEGER);
CREATE TABLE IF NOT EXISTS pool_bars(
 pool TEXT, bucket INTEGER, n_trades INTEGER, buy_sol REAL, sell_sol REAL,
 n_buyers INTEGER, mcap_sol REAL, liq_sol REAL, PRIMARY KEY(pool, bucket));
CREATE INDEX IF NOT EXISTS ix_poolbars_bucket ON pool_bars(bucket);
CREATE TABLE IF NOT EXISTS sol_prices(ts INTEGER PRIMARY KEY, price REAL);
CREATE TABLE IF NOT EXISTS regime_log(
 hour INTEGER PRIMARY KEY, regime TEXT, grad_rate REAL, baseline REAL, n_launch INTEGER, med_life_s REAL);
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

    def add_bars(self, rows):
        if not rows: return
        with self._lock:
            self._conn.executemany("""INSERT OR REPLACE INTO launch_bars(mint,bucket,lane,n_trades,buy_sol,sell_sol,n_buyers,mcap_sol)
                VALUES(?,?,?,?,?,?,?,?)""", rows); self._conn.commit()

    def add_shadow(self, strategy, kind, mint, pool, ts, entry_mcap, context) -> int:
        cur = self.execute("INSERT INTO shadow_signals(strategy,kind,mint,pool,ts,entry_mcap,context) VALUES(?,?,?,?,?,?,?)",
                           (strategy, kind, mint, pool, ts, entry_mcap, json.dumps(context)))
        return int(cur.lastrowid)

    def add_hypothesis(self, rule_key, dimension, cohort, n, ev_pct, med_pct, pos_share, baseline_ev_pct, z, verdict, detail=""):
        """Registro IMMUTABILE delle ipotesi della fabbrica: una regola, un verdetto.
        INSERT OR IGNORE: la stessa regola non viene mai ri-giudicata sugli stessi dati."""
        import time as _t
        with self._lock:
            self._conn.execute("""INSERT OR IGNORE INTO hypotheses(rule_key,created_ts,dimension,cohort,n,ev_pct,med_pct,pos_share,baseline_ev_pct,z,verdict,detail)
                                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                               (rule_key, _t.time(), dimension, cohort, n, ev_pct, med_pct, pos_share, baseline_ev_pct, z, verdict, detail))
            self._conn.commit()

    def list_hypotheses(self, limit=50):
        return self.q("SELECT * FROM hypotheses ORDER BY created_ts DESC LIMIT ?", (limit,))

    def replace_actor_stats(self, creators, wallets):
        import time as _t
        now = _t.time()
        with self._lock:
            self._conn.execute("DELETE FROM creator_stats")
            self._conn.execute("DELETE FROM wallet_flags")
            self._conn.executemany("INSERT INTO creator_stats VALUES(?,?,?,?,?,?,?,?)",
                                   [(c["creator"], c["n_launches"], c["n_grad"], c["grad_rate"], c["med_peak"], c["fast_dead_share"], c["last_ts"], now) for c in creators])
            self._conn.executemany("INSERT INTO wallet_flags VALUES(?,?,?,?,?,?)",
                                   [(w["wallet"], w["n_tokens"], w["n_repeat_creators"], w["max_creator_launches"], w["bonded_share"], now) for w in wallets])
            self._conn.commit()

    # ---------------- database storico (cattura profonda) ----------------
    def add_launch_facts(self, f: dict):
        cols = ("mint,creator,created_at,lane,graduated,first_mcap,peak_mcap,t_peak_s,last_mcap,lifespan_s,"
                "n_trades,buy_sol,sell_sol,uniq_buyers,uniq_sellers,top1_share,dev_buy_60s,snipe_share5s,"
                "peak_mult,last_mult,creator_prior")
        with self._lock:
            self._conn.execute(f"INSERT OR IGNORE INTO launch_facts({cols}) VALUES({','.join('?' * 21)})",
                               tuple(f.get(k) for k in cols.split(",")))
            self._conn.commit()

    def compute_launch_facts(self, mint: str) -> bool:
        """Scheda completa di un lancio da barre+trade (SQL puro, point-in-time)."""
        tok = self.q("SELECT creator,created_at,lane,bonded_at FROM tokens WHERE mint=?", (mint,))
        bars = self.q("SELECT bucket,mcap_sol FROM launch_bars WHERE mint=? AND mcap_sol>0 ORDER BY bucket", (mint,))
        if not tok or not bars:
            return False
        t = tok[0]; created = float(t["created_at"] or bars[0]["bucket"])
        mcaps = [float(b["mcap_sol"]) for b in bars]
        first, peak = mcaps[0], max(mcaps)
        t_peak = float(bars[mcaps.index(peak)]["bucket"]) - created
        agg = self.q("""SELECT COUNT(*) n, COALESCE(SUM(CASE WHEN is_buy=1 THEN sol END),0) b,
                        COALESCE(SUM(CASE WHEN is_buy=0 THEN sol END),0) s,
                        COUNT(DISTINCT CASE WHEN is_buy=1 THEN trader END) ub,
                        COUNT(DISTINCT CASE WHEN is_buy=0 THEN trader END) us
                        FROM trades WHERE mint=?""", (mint,))[0]
        top = self.q("SELECT COALESCE(SUM(sol),0) t FROM trades WHERE mint=? AND is_buy=1 GROUP BY trader ORDER BY t DESC LIMIT 1", (mint,))
        dev = self.q("SELECT COALESCE(SUM(sol),0) t FROM trades WHERE mint=? AND is_buy=1 AND trader=? AND ts<=?",
                     (mint, t["creator"], created + 60)) if t["creator"] else []
        sn5 = self.q("SELECT COALESCE(SUM(sol),0) t FROM trades WHERE mint=? AND is_buy=1 AND ts<=?", (mint, created + 5))
        buy = float(agg["b"] or 0)
        prior = self.q("SELECT COUNT(*) c FROM tokens WHERE creator=? AND created_at<? AND mint<>?",
                       (t["creator"], created, mint))[0]["c"] if t["creator"] else 0
        self.add_launch_facts({
            "mint": mint, "creator": t["creator"], "created_at": created, "lane": t["lane"],
            "graduated": 1 if t["bonded_at"] else 0, "first_mcap": first, "peak_mcap": peak,
            "t_peak_s": t_peak, "last_mcap": mcaps[-1],
            "lifespan_s": float(bars[-1]["bucket"] - bars[0]["bucket"]),
            "n_trades": int(agg["n"] or 0), "buy_sol": buy, "sell_sol": float(agg["s"] or 0),
            "uniq_buyers": int(agg["ub"] or 0), "uniq_sellers": int(agg["us"] or 0),
            "top1_share": round(float(top[0]["t"]) / buy, 3) if top and buy > 0 else 0.0,
            "dev_buy_60s": float(dev[0]["t"]) if dev else 0.0,
            "snipe_share5s": round(float(sn5[0]["t"]) / buy, 3) if buy > 0 else 0.0,
            "peak_mult": round(peak / first, 3) if first else 0.0,
            "last_mult": round(mcaps[-1] / first, 3) if first else 0.0,
            "creator_prior": int(prior)})
        return True

    def backfill_launch_facts(self, older_than_s: int = 1800, limit: int = 5000) -> int:
        rows = self.q("""SELECT t.mint FROM tokens t LEFT JOIN launch_facts f ON f.mint=t.mint
                         WHERE f.mint IS NULL AND t.created_at<? ORDER BY t.created_at LIMIT ?""",
                      (time.time() - older_than_s, limit))
        return sum(1 for r in rows if self.compute_launch_facts(r["mint"]))

    def add_pool_bars(self, rows):
        with self._lock:
            self._conn.executemany(
                """INSERT OR REPLACE INTO pool_bars(pool,bucket,n_trades,buy_sol,sell_sol,n_buyers,mcap_sol,liq_sol)
                   VALUES(?,?,?,?,?,?,?,?)""", rows)
            self._conn.commit()

    def add_sol_price(self, ts, price):
        if not price or float(price) <= 0:
            return
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO sol_prices(ts,price) VALUES(?,?)",
                               (int(float(ts) // 60 * 60), float(price)))
            self._conn.commit()

    def add_regime(self, row):
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO regime_log(hour,regime,grad_rate,baseline,n_launch,med_life_s) VALUES(?,?,?,?,?,?)",
                               (int(row.get("hour") or 0), row.get("regime"), row.get("grad_rate"),
                                row.get("baseline"), row.get("n_launch"), row.get("med_life_s")))
            self._conn.commit()

    def prune(self, snapshot_days: int = 14, trade_days: int = 45, bars_days: int = 30) -> dict:
        now = time.time()
        a = self.execute("DELETE FROM snapshots WHERE ts < ?", (now - snapshot_days*86400,)).rowcount
        b = self.execute("DELETE FROM trades WHERE ts < ?", (now - trade_days*86400,)).rowcount
        c = self.execute("DELETE FROM amm_trades WHERE ts < ?", (now - trade_days*86400,)).rowcount
        d = self.execute("DELETE FROM launch_bars WHERE bucket < ?", (int(now - bars_days*86400),)).rowcount
        e = self.execute("DELETE FROM pool_bars WHERE bucket < ?", (int(now - bars_days*86400),)).rowcount
        self.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return {"snapshots_deleted": a, "trades_deleted": b, "amm_trades_deleted": c,
                "launch_bars_deleted": d, "pool_bars_deleted": e}
