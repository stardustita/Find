from __future__ import annotations
import argparse, asyncio, json, logging, random, time
from .logging_setup import setup_logging
from .settings import Settings
log=logging.getLogger("cli")

def _settings(): return Settings.load()

async def _run_live(args):
    from .orchestrator import Orchestrator
    s=_settings(); orch=Orchestrator(s); server=None
    if not args.no_dashboard:
        from .api.server import build_server
        try:
            server=build_server(orch,s.api_host,s.api_port)
            import threading; threading.Thread(target=server.serve_forever,daemon=True).start()
            print(f"\n  ▸ Dashboard live:  http://127.0.0.1:{s.api_port}\n", flush=True)
        except OSError as e:
            print(f"  ▸ Dashboard non avviata ({e}); il motore continua in headless.\n", flush=True)
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
        from .api.server import build_server
        try:
            server=build_server(orch,s.api_host,s.api_port)
            import threading; threading.Thread(target=server.serve_forever,daemon=True).start()
            print(f"  ▸ Dashboard simulazione: http://127.0.0.1:{s.api_port}", flush=True)
        except OSError as e: print(f"  ▸ Dashboard non avviata: {e}", flush=True)
    market=SimMarket(orch.bus,n_tokens=args.tokens,speed=args.speed)
    print(f"  ▸ SIM: {args.tokens} token sintetici, tempo x{args.speed} (mercato sintetico calibrato, nessun denaro)\n", flush=True)
    orch_task=asyncio.create_task(orch.run(with_stream=False)); label_task=asyncio.create_task(_periodic_label(orch,args.speed))
    try: await market.run(); await asyncio.sleep(2)
    finally:
        for t in (label_task,orch_task): t.cancel()
        await asyncio.gather(label_task,orch_task,return_exceptions=True)
    _print_report(orch.store)

async def _capture(args):
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

def _backtest(args):
    from .orchestrator import Orchestrator
    s=Orchestrator(_settings()).store
    rows=s.q("""SELECT sg.tier,COUNT(*) n,AVG(o.max_mult_15m) avg15,SUM(CASE WHEN o.max_mult_15m>=1.8 THEN 1 ELSE 0 END) hit15,
                AVG(o.max_mult_24h) avg24,SUM(CASE WHEN o.max_mult_24h>=10 THEN 1 ELSE 0 END) hit10x,SUM(CASE WHEN o.max_mult_24h>=100 THEN 1 ELSE 0 END) hit100x
                FROM signals sg JOIN outcomes o ON o.mint=sg.mint GROUP BY sg.tier""")
    print("Backtest segnali curva (esiti da trades osservati; non include slippage reale/MEV):")
    for r in rows: print(f"  {r['tier']:<8} n={r['n']} hit15={r['hit15']} avg15={r['avg15'] or 0:.2f}x hit10x={r['hit10x']} hit100x={r['hit100x']}")
    if not rows: print("  nessun segnale etichettato: esegui prima label dopo una sessione di raccolta.")

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

def main(argv=None):
    ap=argparse.ArgumentParser("pumpradar"); ap.add_argument("-v","--verbose",action="store_true"); sub=ap.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("run"); r.add_argument("--no-dashboard",action="store_true")
    sm=sub.add_parser("sim"); sm.add_argument("--tokens",type=int,default=400); sm.add_argument("--speed",type=float,default=90.0); sm.add_argument("--dashboard",action="store_true")
    c=sub.add_parser("capture"); c.add_argument("--minutes",type=float,default=30.0)
    sub.add_parser("label")
    t=sub.add_parser("train"); t.add_argument("--min-rows",type=int,default=500); t.add_argument("--force",action="store_true")
    sub.add_parser("report"); sub.add_parser("backtest"); sub.add_parser("doctor")
    p=sub.add_parser("prune"); p.add_argument("--snapshot-days",type=int,default=14); p.add_argument("--trade-days",type=int,default=45)
    args=ap.parse_args(argv); setup_logging(args.verbose)
    if args.cmd=="run": asyncio.run(_run_live(args))
    elif args.cmd=="sim": asyncio.run(_run_sim(args))
    elif args.cmd=="capture": asyncio.run(_capture(args))
    elif args.cmd=="label": _label(args)
    elif args.cmd=="train": _train(args)
    elif args.cmd=="report": _report(args)
    elif args.cmd=="backtest": _backtest(args)
    elif args.cmd=="doctor": asyncio.run(_doctor(args))
    elif args.cmd=="prune":
        from .orchestrator import Orchestrator
        print(Orchestrator(_settings()).store.prune(args.snapshot_days,args.trade_days))

if __name__=="__main__": main()
