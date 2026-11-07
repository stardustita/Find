from __future__ import annotations
import argparse, asyncio, json, logging, random
from pathlib import Path
from .logging_setup import setup_logging
from .settings import Settings
log=logging.getLogger("cli")

def _settings(): return Settings.load()

def _pid_alive(pid):
    try:
        import os
        os.kill(pid, 0); return True
    except PermissionError:
        return True
    except Exception:
        return False

def _acquire_instance_lock(path=None):
    """Lock anti-doppia-istanza (anche da cartelle diverse): un solo motore live per macchina."""
    import os, tempfile
    path=path or (Path(tempfile.gettempdir())/"pumpradar-instance.lock")
    for _ in range(2):
        try:
            fd=os.open(str(path), os.O_CREAT|os.O_EXCL|os.O_WRONLY); os.write(fd, str(os.getpid()).encode()); os.close(fd); return path
        except FileExistsError:
            try: pid=int(Path(path).read_text().strip() or 0)
            except Exception: pid=0
            if pid and _pid_alive(pid): return None
            try: Path(path).unlink()   # lock residuo di un processo morto
            except Exception: return None
    return None

def _release_instance_lock(path):
    try:
        if path: Path(path).unlink()
    except Exception: pass

def _start_dashboard(orch, s, label="live"):
    """Avvia la dashboard sulla prima porta libera a partire da s.api_port:
    se 8787 e' occupata (altra istanza o altro programma) prova 8788, 8789..."""
    from .api.server import build_server
    import threading
    for port in range(int(s.api_port), int(s.api_port)+10):
        try:
            server=build_server(orch, s.api_host, port)
        except OSError:
            continue
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"\n  ▸ Dashboard {label}:  http://127.0.0.1:{port}\n", flush=True)
        return server, port
    print("  ▸ Dashboard non avviata: porte occupate; il motore continua in headless.\n", flush=True)
    return None, None

async def _run_live(args):
    lock=_acquire_instance_lock()
    if lock is None:
        print("\n  ✖ Un'altra istanza di PumpRadar e' gia' in esecuzione su questa macchina (probabilmente avviata da un'altra cartella).\n    Chiudila con Ctrl+C nella sua console, oppure usa quella gia' aperta: una sola istanza = un solo database coerente.\n", flush=True); return
    try: await _run_live_locked(args)
    finally: _release_instance_lock(lock)

async def _run_live_locked(args):
    from .orchestrator import Orchestrator
    s=_settings(); orch=Orchestrator(s); server=None
    if not args.no_dashboard:
        server,_port=_start_dashboard(orch,s,"live")
    try: await orch.run()
    finally:
        if server: server.shutdown()

async def _fake_meta(uri: str) -> dict:
    r=random.Random(uri or "x")
    return {"description":"sim "*r.randint(0,20),"twitter":"x.com/a" if r.random()<0.4 else "","telegram":"t.me/a" if r.random()<0.3 else "","website":"","image_hash":f"h{r.randint(0,50)}","image_reuse":1}

async def _periodic_label(orch, speed):
    from .learning.labeler import Labeler
    lab=Labeler(orch.store, orch.s)
    while True:
        await asyncio.sleep(max(2.0,30.0/max(1,speed)))
        try: lab.label_outcomes(); lab.update_wallet_skill()
        except Exception as e: log.debug("label: %s", e)

async def _run_sim(args):
    from .orchestrator import Orchestrator
    from .sim import SimMarket
    s=_settings(); s.tick_seconds=max(0.05,s.tick_seconds/args.speed); s.trade_stream=False; s.narrative_enabled=False
    orch=Orchestrator(s); orch.enr.sol_price=150.0; orch.enr.fetch_metadata=_fake_meta
    if args.dashboard:
        _start_dashboard(orch,s,"simulazione")
    market=SimMarket(orch.bus,n_tokens=args.tokens,speed=args.speed)
    print(f"  ▸ SIM: {args.tokens} token sintetici, tempo x{args.speed} (mercato sintetico calibrato, nessun denaro)\n", flush=True)
    orch_task=asyncio.create_task(orch.run(with_stream=False)); label_task=asyncio.create_task(_periodic_label(orch,args.speed))
    try: await market.run(); await asyncio.sleep(2)
    finally:
        for t in (label_task,orch_task): t.cancel()
        await asyncio.gather(label_task,orch_task,return_exceptions=True)
    _print_report(orch.store)

async def _capture(args):
    lock=_acquire_instance_lock()
    if lock is None:
        print("\n  ✖ Un'altra istanza di PumpRadar e' gia' in esecuzione: capture rimandata.\n", flush=True); return
    try: await _capture_locked(args)
    finally: _release_instance_lock(lock)

async def _capture_locked(args):
    from .orchestrator import Orchestrator
    s=_settings(); orch=Orchestrator(s); print(f"  ▸ CAPTURE {args.minutes} minuti → {s.db_path}", flush=True)
    task=asyncio.create_task(orch.run())
    try: await asyncio.sleep(args.minutes*60)
    finally: task.cancel(); await asyncio.gather(task,return_exceptions=True)
    print(json.dumps(orch.health(),indent=2,default=str)[:3000])

def _label(args):
    from .orchestrator import Orchestrator
    from .learning.labeler import Labeler
    orch=Orchestrator(_settings()); lab=Labeler(orch.store,orch.s); n=lab.label_outcomes(); lab.update_wallet_skill(); print(f"etichettati: {n}")
    r=orch.store.one("SELECT COUNT(*) n,SUM(bonded) b,SUM(engineered) e,AVG(max_mult_15m) m15,MAX(max_mult_24h) best FROM outcomes")
    print(dict(r) if r else {})

def _train(args):
    from .orchestrator import Orchestrator
    from .learning.trainer import train
    orch=Orchestrator(_settings()); rep=train(orch.store,min_rows=args.min_rows,force=args.force); print(json.dumps(rep,indent=2,ensure_ascii=False)[:5000])

def _print_report(store):
    s=store
    print("\n=== SEGNALI (curva) ===")
    for r in s.q("SELECT tier,COUNT(*) n FROM signals GROUP BY tier ORDER BY n DESC"): print(f"  {r['tier']:<8} {r['n']}")
    print("=== SEGNALI (post-graduation) ===")
    for r in s.q("SELECT tier,COUNT(*) n FROM pg_signals GROUP BY tier ORDER BY n DESC"): print(f"  {r['tier']:<8} {r['n']}")
    print("=== POSIZIONI CHIUSE ===")
    for kind in ("curve","runner"):
        r=s.one("""SELECT COUNT(*) n,SUM(CASE WHEN pnl_sol>0 THEN 1 ELSE 0 END) w,SUM(pnl_sol) pnl,AVG(pnl_pct) avg,MAX(pnl_pct) best,MIN(pnl_pct) worst FROM positions WHERE status='closed' AND kind=?""", (kind,))
        if r and r["n"]: print(f"  {kind:<7} trades {r['n']}  win-rate {(r['w'] or 0)/r['n']*100:.1f}%  P&L {r['pnl']:+.4f} SOL  avg {(r['avg'] or 0)*100:+.1f}%  best {(r['best'] or 0)*100:+.0f}%  worst {(r['worst'] or 0)*100:+.0f}%")
        else: print(f"  {kind:<7} nessuna posizione chiusa")
    print("=== USCITE CURVA (motivi) ===")
    for r in s.q("SELECT reason,COUNT(*) n,COALESCE(SUM(pnl_sol),0) pnl FROM positions WHERE status='closed' AND kind='curve' GROUP BY reason ORDER BY n DESC LIMIT 8"):
        print(f"  {r['n']:>3}  {r['pnl']:+.4f} SOL  {r['reason']}")
    print("=== POSIZIONI APERTE ===")
    for r in s.q("SELECT kind,COUNT(*) n FROM positions WHERE status='open' GROUP BY kind"): print(f"  {r['kind']:<7} {r['n']}")
    print("=== ESITI ===")
    r=s.one("SELECT COUNT(*) n,SUM(bonded) b,SUM(engineered) e,AVG(max_mult_15m) m15,AVG(peak_mcap/entry_mcap) pk FROM outcomes WHERE entry_mcap>0")
    if r and r["n"]: print(f"  token {r['n']}  graduated {r['b'] or 0}  engineered {r['e'] or 0}  mult medio 15m {r['m15'] or 0:.2f}x  picco medio {r['pk'] or 0:.2f}x")
    print("=== WALLET (timing) ===")
    for r in s.q("SELECT addr,n_trades,wins,score FROM wallets WHERE wins>0 ORDER BY score DESC LIMIT 8"): print(f"  {r['addr'][:14]}… trades {r['n_trades']:<5} wins {r['wins']:<3} score {r['score']:.2f}")

def _report(args):
    from .orchestrator import Orchestrator
    _print_report(Orchestrator(_settings()).store)

def _analyze(args):
    from .orchestrator import Orchestrator
    from .learning.analyze import analyze, format_report
    store = Orchestrator(_settings()).store
    d = analyze(store)
    print(format_report(d))
    if args.json:
        Path(args.json).write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  ▸ dettaglio JSON salvato in {args.json}")

def _optimize(args):
    from .orchestrator import Orchestrator
    from .learning.optimize import optimize, format_optimize
    store = Orchestrator(_settings()).store
    for kind in ("curve", "pg"):
        print(format_optimize(optimize(store, kind)))
        print()

def _backtest(args):
    from .orchestrator import Orchestrator
    s=Orchestrator(_settings()).store
    # finestre calcolate DAL timestamp e DAL prezzo del segnale: il vecchio backtest
    # partiva dal primo trade del token e attribuiva al segnale anche picchi precedenti.
    rows=s.q("""SELECT sg.tier,COUNT(*) n,
                AVG((SELECT MAX(t.mcap_sol) FROM trades t WHERE t.mint=sg.mint AND t.ts BETWEEN sg.ts AND sg.ts+900)/sg.mcap_sol) avg15,
                SUM(CASE WHEN (SELECT MAX(t.mcap_sol) FROM trades t WHERE t.mint=sg.mint AND t.ts BETWEEN sg.ts AND sg.ts+900)>=1.8*sg.mcap_sol THEN 1 ELSE 0 END) hit15,
                AVG((SELECT MAX(t.mcap_sol) FROM trades t WHERE t.mint=sg.mint AND t.ts BETWEEN sg.ts AND sg.ts+86400)/sg.mcap_sol) avg24,
                SUM(CASE WHEN (SELECT MAX(t.mcap_sol) FROM trades t WHERE t.mint=sg.mint AND t.ts BETWEEN sg.ts AND sg.ts+86400)>=10*sg.mcap_sol THEN 1 ELSE 0 END) hit10x,
                SUM(CASE WHEN (SELECT MAX(t.mcap_sol) FROM trades t WHERE t.mint=sg.mint AND t.ts BETWEEN sg.ts AND sg.ts+86400)>=100*sg.mcap_sol THEN 1 ELSE 0 END) hit100x
                FROM signals sg WHERE sg.mcap_sol>0 GROUP BY sg.tier""")
    print("Backtest segnali curva (finestre dal segnale; esiti da trade osservati, senza slippage reale/MEV):")
    for r in rows: print(f"  {r['tier']:<8} n={r['n']} hit15={r['hit15']} avg15={r['avg15'] or 0:.2f}x avg24={r['avg24'] or 0:.2f}x hit10x={r['hit10x']} hit100x={r['hit100x']}")
    if not rows: print("  nessun segnale etichettato: esegui prima label dopo una sessione di raccolta.")
    rows=s.q("""SELECT pg.tier,COUNT(*) n,
                AVG((SELECT MAX(a.mcap_sol) FROM amm_trades a WHERE a.pool=pg.pool AND a.ts BETWEEN pg.ts AND pg.ts+3600)/pg.mcap_sol) avg1h,
                AVG((SELECT MAX(a.mcap_sol) FROM amm_trades a WHERE a.pool=pg.pool AND a.ts BETWEEN pg.ts AND pg.ts+86400)/pg.mcap_sol) avg24,
                SUM(CASE WHEN (SELECT MAX(a.mcap_sol) FROM amm_trades a WHERE a.pool=pg.pool AND a.ts BETWEEN pg.ts AND pg.ts+86400)>=2*pg.mcap_sol THEN 1 ELSE 0 END) hit2x,
                SUM(CASE WHEN (SELECT MAX(a.mcap_sol) FROM amm_trades a WHERE a.pool=pg.pool AND a.ts BETWEEN pg.ts AND pg.ts+86400)>=10*pg.mcap_sol THEN 1 ELSE 0 END) hit10x,
                SUM(CASE WHEN (SELECT MAX(a.mcap_sol) FROM amm_trades a WHERE a.pool=pg.pool AND a.ts BETWEEN pg.ts AND pg.ts+86400)>=100*pg.mcap_sol THEN 1 ELSE 0 END) hit100x
                FROM pg_signals pg WHERE pg.mcap_sol>0 GROUP BY pg.tier""")
    print("Backtest segnali post-graduation (finestre dal segnale, trade AMM tracciati):")
    for r in rows: print(f"  {r['tier']:<8} n={r['n']} avg1h={r['avg1h'] or 0:.2f}x avg24={r['avg24'] or 0:.2f}x hit2x={r['hit2x']} hit10x={r['hit10x']} hit100x={r['hit100x']}")
    if not rows: print("  nessun segnale post-graduation ancora.")

async def _doctor(args):
    import asyncio as _a
    from .bus import Bus
    from .ingest.amm import AmmFeed
    from .ingest.enrich import Enricher
    from .ingest.onchain import OnchainFeed
    s=_settings(); print("1) feed on-chain curva (logsSubscribe + decode Borsh)…")
    bus=Bus(); feed=OnchainFeed(bus,list(s.rpc_ws_urls)); task=_a.create_task(feed.run()); await _a.sleep(12); task.cancel(); await _a.gather(task,return_exceptions=True)
    h=feed.health(); print(f"   notifiche={h['counts'].get('notif',0)} trade={h['counts'].get('trade',0)} ({h['trades_per_s']}/s) corsie={h['lanes_pct']}")
    if not h['counts'].get('trade',0): print("   FAIL: nessun trade decodificato. Controlla rete/firewall/RPC oppure configura PR_RPC_WS_URLS con un endpoint WS raggiungibile.")
    print("2) feed AMM post-graduation…"); bus2=Bus(); amm=AmmFeed(bus2,list(s.rpc_ws_urls)); task=_a.create_task(amm.run()); await _a.sleep(12); task.cancel(); await _a.gather(task,return_exceptions=True)
    h=amm.health(); print(f"   AMM trade={h['counts'].get('trade',0)} ({h['trades_per_s']}/s) pool={h['pools_created']}")
    if not h['counts'].get('trade',0): print("   FAIL: nessun trade AMM decodificato. Il feed PumpSwap non è raggiungibile da questa rete.")
    print("3) prezzo SOL (Jupiter, gratuito)…"); e=Enricher(s,None); px=await e.refresh_sol_price(); print(f"   SOL = {px:.2f}$" + ("  (fallback: sorgente non raggiungibile)" if not e.sol_price else ""))
    print("4) Telegram:", "configurato" if s.telegram_token else "non configurato (opzionale)")
    print("5) RPC WS:", ", ".join(s.rpc_ws_urls))

def _lab_store():
    from .store import Store
    return Store(_settings().db_path)

def _census(args):
    from .learning.census import census, format_census
    print(format_census(census(_lab_store())))

def _regime(args):
    from .learning.regime import format_regime, regime_series
    print(format_regime(regime_series(_lab_store())))

def _factory(args):
    from .learning.factory import format_factory, run_factory
    print(format_factory(run_factory(_lab_store())))

def _actors(args):
    from .learning.actors import build_actor_stats, format_actors
    print(format_actors(build_actor_stats(_lab_store())))

def _knn(args):
    from .learning.knn import find_twins, format_twins
    print(format_twins(find_twins(_lab_store(), args.mint, args.k)))

def _verify(args):
    from .learning.verify import format_verify, verify
    print(format_verify(verify(_lab_store())))

def _guardian(args):
    from .guardian import format_guardian, serial_ruggers, tier_health
    from .learning.census import launch_summaries
    from .learning.regime import current_regime
    store=_lab_store()
    print(format_guardian(serial_ruggers(launch_summaries(store)),
                          str(current_regime(store).get("regime", "unknown")), tier_health(store)))

def _autopsy(args):
    import time as _t
    from .learning.autopsy import build_autopsy, send_telegram
    s=_settings(); md=build_autopsy(_lab_store())
    out=Path("reports"); out.mkdir(exist_ok=True)
    f=out/f"autopsy-{_t.strftime('%Y-%m-%d')}.md"; f.write_text(md, encoding="utf-8")  # emoji nel report: su Windows il default cp1252 esplode
    try: print(md)
    except UnicodeEncodeError: print(md.encode("ascii", "replace").decode())
    print(f"\n[autopsy salvata in {f}]")
    if args.send:
        print("inviata su Telegram" if send_telegram(s, md) else "Telegram non configurato (TELEGRAM_TOKEN / TELEGRAM_CHAT)")

def main(argv=None):
    ap=argparse.ArgumentParser("pumpradar"); ap.add_argument("-v","--verbose",action="store_true"); sub=ap.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("run"); r.add_argument("--no-dashboard",action="store_true")
    sm=sub.add_parser("sim"); sm.add_argument("--tokens",type=int,default=400); sm.add_argument("--speed",type=float,default=90.0); sm.add_argument("--dashboard",action="store_true")
    c=sub.add_parser("capture"); c.add_argument("--minutes",type=float,default=30.0)
    sub.add_parser("label")
    t=sub.add_parser("train"); t.add_argument("--min-rows",type=int,default=500); t.add_argument("--force",action="store_true")
    sub.add_parser("report"); sub.add_parser("backtest")
    an=sub.add_parser("analyze"); an.add_argument("--json",type=str,default="")
    sub.add_parser("optimize")
    sub.add_parser("census"); sub.add_parser("regime"); sub.add_parser("factory"); sub.add_parser("actors")
    kn=sub.add_parser("knn"); kn.add_argument("mint"); kn.add_argument("--k",type=int,default=25)
    au=sub.add_parser("autopsy"); au.add_argument("--send",action="store_true")
    sub.add_parser("guardian"); sub.add_parser("verify")
    sub.add_parser("doctor")
    p=sub.add_parser("prune"); p.add_argument("--snapshot-days",type=int,default=14); p.add_argument("--trade-days",type=int,default=45)
    args=ap.parse_args(argv); setup_logging(args.verbose)
    if args.cmd=="run": asyncio.run(_run_live(args))
    elif args.cmd=="sim": asyncio.run(_run_sim(args))
    elif args.cmd=="capture": asyncio.run(_capture(args))
    elif args.cmd=="label": _label(args)
    elif args.cmd=="train": _train(args)
    elif args.cmd=="report": _report(args)
    elif args.cmd=="analyze": _analyze(args)
    elif args.cmd=="optimize": _optimize(args)
    elif args.cmd=="census": _census(args)
    elif args.cmd=="regime": _regime(args)
    elif args.cmd=="factory": _factory(args)
    elif args.cmd=="actors": _actors(args)
    elif args.cmd=="knn": _knn(args)
    elif args.cmd=="autopsy": _autopsy(args)
    elif args.cmd=="guardian": _guardian(args)
    elif args.cmd=="verify": _verify(args)
    elif args.cmd=="backtest": _backtest(args)
    elif args.cmd=="doctor": asyncio.run(_doctor(args))
    elif args.cmd=="prune":
        from .orchestrator import Orchestrator
        print(Orchestrator(_settings()).store.prune(args.snapshot_days,args.trade_days))

if __name__=="__main__": main()
