from __future__ import annotations
import asyncio, json, logging, time
from collections import defaultdict

from .agents.context import ContextAgent
from .agents.creator import CreatorAgent
from .agents.curve import CurveAgent
from .agents.exit import ExitAgent
from .agents.narrative import NarrativeAgent
from .agents.risk import RiskAgent
from .agents.scorer import ScorerAgent
from .agents.wallets import WalletGraphAgent
from .bus import Bus
from .ingest.amm import AmmFeed
from .ingest.enrich import Enricher
from .ingest.onchain import OnchainFeed
from .ingest.pumpevent import WSOL_MINT, amm_price, is_sol_quote
from .ingest.stream import PumpPortalStream, parse_trade
from .notify import Notifier
from .runner import GradState, PostGradAgent, RunnerBook, RunnerScorer
from .gem import slancio_signal
from .guardian import censor_check
from .shadow import esplosivo60_signal, pg_pullback_signal, second_leg_signal
from .state import TokenState
from .store import Store

log=logging.getLogger("orchestrator")
TIER_RANK={"NONE":0,"WATCH":1,"ENTRY":2,"STRONG":3}
PG_RANK={"NONE":0,"WATCH":1,"SETUP":2,"RUN":3}

class Orchestrator:
    def __init__(self, settings):
        self.s=settings; self.store=Store(settings.db_path); self.bus=Bus(); self.enr=Enricher(settings,self.store)
        self.feed=OnchainFeed(self.bus,list(settings.rpc_ws_urls),lambda:self.enr.sol_price)
        self.pp=PumpPortalStream(settings.ws_url,settings.ws_apikey,self.bus)
        self.amm=AmmFeed(self.bus,list(settings.rpc_ws_urls)); self.notifier=Notifier(settings)
        self.agents={"curve":CurveAgent(settings.grad_vsol),"walletgraph":WalletGraphAgent(self.store),
                     "creator":CreatorAgent(self.store),"risk":RiskAgent(settings),
                     "narrative":NarrativeAgent(settings,self.store,self.enr),"context":ContextAgent(self.enr)}
        self.scorer=ScorerAgent(settings,self.store); self.exit=ExitAgent(settings,self.store)
        self.pg_agent=PostGradAgent(); self.runner=RunnerScorer(settings); self.rbook=RunnerBook(settings,self.store)
        self.states={}; self.pools={}; self.trial_until={}; self.open_pos_mints=set(); self.open_runner_pools=set()
        self._trade_buf=[]; self._amm_buf=[]; self._orphans={}; self._seen_creates=set(); self._last_signal={}
        self._bars={}; self._shadow_last={}
        self._blacklist=set(); self._regime_label="unknown"; self._demoted=set(); self._tier_health={}; self._guardian_ts=0.0; self._knn=({},[],[])
        self._gem_times=[]
        self._entry_times=[]; self._signal_times=[]; self._pg_last_signal={}; self._quote_mints_seen=set(); self._tick_count=0
        self.started_at=time.time(); self.stats=defaultdict(int); self._top_pg_score=0.0

    async def _supervise(self, name, factory):
        while True:
            try: await factory()
            except asyncio.CancelledError: raise
            except Exception as e:
                self.stats[f"crash_{name}"]+=1; log.exception("task %s caduta (%s) — riavvio in 3s", name, e); await asyncio.sleep(3)

    async def run(self, with_stream=True):
        tasks=[
            asyncio.create_task(self._supervise("create", self._create_consumer)),
            asyncio.create_task(self._supervise("trade", self._trade_consumer)),
            asyncio.create_task(self._supervise("migrate", self._migrate_consumer)),
            asyncio.create_task(self._supervise("pool", self._pool_consumer)),
            asyncio.create_task(self._supervise("amm_trade", self._amm_trade_consumer)),
            asyncio.create_task(self._supervise("tick", self._tick_loop)),
            asyncio.create_task(self._supervise("flush", self._flush_loop)),
            asyncio.create_task(self._supervise("housekeeping", self._housekeeping)),
            asyncio.create_task(self._supervise("heartbeat", self._heartbeat)),
        ]
        if with_stream:
            tasks.append(asyncio.create_task(self._supervise("sol_price", self.enr.sol_price_loop)))
            tasks.append(asyncio.create_task(self._supervise("quote_prices", self._quote_price_loop)))
            if self.s.feed in ("onchain","both"): tasks.append(asyncio.create_task(self._supervise("onchain", self.feed.run)))
            if self.s.feed in ("pumpportal","both"):
                tasks.append(asyncio.create_task(self._supervise("pumpportal", self.pp.run)))
                if self.s.trade_stream: tasks.append(asyncio.create_task(self._supervise("pp_subs", self.pp.pump_subscriptions)))
            if self.s.amm_enabled: tasks.append(asyncio.create_task(self._supervise("amm", self.amm.run)))
        log.info("orchestratore avviato | feed=%s | amm=%s | db=%s", self.s.feed, self.s.amm_enabled, self.s.db_path)
        await asyncio.gather(*tasks)

    # ---------------- creates ----------------
    async def _create_consumer(self):
        q=self.bus.subscribe("create")
        while True:
            ev=await q.get()
            try: await self._on_create(ev)
            except Exception as e: log.exception("on_create: %s", e)
    async def _on_create(self, ev):
        mint=ev.get("mint")
        if not mint or not isinstance(mint,str) or len(mint)<32 or mint in self._seen_creates: return
        self._seen_creates.add(mint); ts=float(ev.get("_ts") or time.time()); lane=ev.get("lane","sol")
        st=TokenState(mint=mint,name=ev.get("name") or "",symbol=ev.get("symbol") or "",uri=ev.get("uri") or "",
                      creator=ev.get("traderPublicKey") or "",created_at=ts,lane=lane,quote_mint=ev.get("quoteMint","SOL"),
                      curve_std=bool(ev.get("curve_std",lane=="sol")),mayhem=bool(ev.get("is_mayhem_mode")),pool=ev.get("pool") or "pump",
                      vsol=float(ev.get("vSolInBondingCurve") or 30.0),vtok=float(ev.get("vTokensInBondingCurve") or 1_073_000_000.0),
                      rtok=float(ev.get("realTokenReserves") or 793_100_000.0),mcap_sol=ev.get("marketCapSol"))
        if st.mcap_sol: st.peak_mcap=float(st.mcap_sol)
        self.states[mint]=st; self.stats["creates"]+=1; self.agents["context"].observe_create(ts)
        self.store.upsert_token({"mint":mint,"name":st.name,"symbol":st.symbol,"uri":st.uri,"creator":st.creator,
            "created_at":ts,"first_seen":time.time(),"init_sol":float(ev.get("solAmount") or 0),"init_mcap_sol":st.mcap_sol,
            "mayhem":int(st.mayhem),"pool":st.pool,"state":"new","last_ts":ts,"creator_sig":ev.get("signature"),
            "quote_mint":st.quote_mint,"lane":lane})
        try: st.meta["creator_prior"]=int(self.store.q("SELECT COUNT(*) c FROM tokens WHERE creator=? AND created_at<?",(st.creator,ts))[0]["c"]) if st.creator else 0
        except Exception: st.meta["creator_prior"]=0
        self.trial_until[mint]=time.time()+75.0
        if self.s.trade_stream and self.s.feed in ("pumpportal","both"): self.pp.subscribe_trades([mint])
        asyncio.create_task(self._enrich_meta(st))
    async def _enrich_meta(self, st):
        try:
            meta=await self.enr.fetch_metadata(st.uri)
            if meta:
                st.meta=dict(meta); st.meta["image_reuse"]=self.enr.image_reuse(meta.get("image_hash"))
                self.store.execute("""UPDATE tokens SET meta_json=?,meta_name=?,meta_symbol=?,meta_desc=?,meta_twitter=?,meta_telegram=?,meta_website=?,image_hash=? WHERE mint=?""",
                    (json.dumps(meta),meta.get("name"),meta.get("symbol"),meta.get("description"),meta.get("twitter"),meta.get("telegram"),meta.get("website"),meta.get("image_hash"),st.mint))
                if meta.get("name") and not st.name: st.name=meta["name"]
                if meta.get("symbol") and not st.symbol: st.symbol=meta["symbol"]
        except Exception as e: log.debug("meta %s: %s", st.mint, e)

    # ---------------- trades ----------------
    async def _trade_consumer(self):
        q=self.bus.subscribe("trade")
        while True:
            ev=await q.get(); mint=ev.get("mint")
            if not mint: continue
            tr=parse_trade(ev,self.enr.sol_price)
            if tr is None: continue
            st=self.states.get(mint)
            if st is None:
                self.stats["trades_orphan"]+=1; self._maybe_recover(mint,tr); continue
            st.observe(tr); self.stats["trades"]+=1; self._update_bar(st,tr)
            if tr.get("quote_mint") and tr.get("lane")=="cross": self._quote_mints_seen.add(str(tr["quote_mint"]))
            if st.state in ("new","watch") or mint in self.open_pos_mints: self._trade_buf.append(tr)
    def _maybe_recover(self, mint, tr):
        if tr.get("lane")!="sol": return
        now=float(tr.get("ts") or time.time()); rec=self._orphans.get(mint)
        if rec is None: rec=[0,now,now,0.0]; self._orphans[mint]=rec
        rec[0]+=1; rec[2]=now; rec[3]+=float(tr.get("sol") or 0)
        if rec[0]>=5 and rec[2]-rec[1]<=20:
            st=TokenState(mint=mint,symbol=mint[:6],created_at=rec[1],lane="sol",quote_mint="SOL",curve_std=True,state="watch",persist=True)
            self.states[mint]=st; self._seen_creates.add(mint); self._orphans.pop(mint,None); self.stats["recovered"]+=1
            self.store.upsert_token({"mint":mint,"name":"","symbol":mint[:6],"uri":"","creator":"","created_at":rec[1],"first_seen":now,
                "init_sol":0,"init_mcap_sol":tr.get("mcap_sol"),"mayhem":0,"pool":"pump","state":"watch","last_ts":now,"creator_sig":None,"quote_mint":"SOL","lane":"sol"})
            st.observe(tr); self._trade_buf.append(tr); log.info("token recuperato da trade orfani: %s", mint[:8])
        if len(self._orphans)>50000:
            cutoff=now-300
            for m in [m for m,r in self._orphans.items() if r[2]<cutoff][:10000]: self._orphans.pop(m,None)
    def _refresh_guardian_sync(self, now):
        """Guardiani (Fase 5): blacklist Sentinella, regime, retrocessioni Revisore,
        indice Oracolo. Ricalcolati al massimo ogni 15 min, in thread separato."""
        if now-self._guardian_ts<900: return
        self._guardian_ts=now
        try:
            from .guardian import serial_ruggers, tier_health
            from .learning.census import launch_summaries
            from .learning.knn import _index as knn_index
            from .learning.regime import current_regime
            summaries=launch_summaries(self.store)
            self._blacklist=serial_ruggers(summaries)
            self._regime_label=str(current_regime(self.store).get("regime","unknown"))
            self._tier_health=tier_health(self.store)
            self._demoted={k for k,v in self._tier_health.items() if v["demote"]}
            self._knn=knn_index(summaries)
            log.info("🛡️ Guardiani: blacklist=%d creator · regime=%s · tier retrocessi=%s",
                     len(self._blacklist), self._regime_label, sorted(self._demoted) or "nessuno")
        except Exception as e: log.debug("guardian refresh: %s", e)
    def _twins_veto(self, base_mint):
        """Oracolo-Veto: i gemelli storici del lancio sconsigliano il pool."""
        try:
            from .learning.knn import twins_from_index
            fps, means, stds = self._knn
            if base_mint not in fps: return None
            t = twins_from_index(fps, means, stds, base_mint, 25)
            if "error" not in t and t["med_peak"] < 1.05 and t["p2x"] < 0.08:
                return "gemelli_negativi"
        except Exception: pass
        return None
    def _update_bar(self, st, tr):
        """Aggregato 5s per ogni lancio (primi 30 min di vita), anche se scartato:
        e' il dataset senza survivorship bias della Fase 1."""
        try:
            ts=float(tr.get("ts") or 0)
            if not ts or ts-(st.created_at or ts)>1800: return
            b=int(ts//5*5); key=(st.mint,b); acc=self._bars.get(key)
            if acc is None: acc=self._bars[key]=[0,0.0,0.0,set(),0.0,st.lane]
            acc[0]+=1
            if tr.get("is_buy"):
                acc[1]+=float(tr.get("sol") or 0)
                if tr.get("trader"): acc[3].add(tr["trader"])
            else: acc[2]+=float(tr.get("sol") or 0)
            if tr.get("mcap_sol"): acc[4]=float(tr["mcap_sol"])
        except Exception: pass
    def _flush_bars(self):
        if not self._bars: return
        nowb=int(time.time()//5*5); ready=[k for k in self._bars if k[1]<nowb]
        if not ready: return
        rows=[]
        for k in ready:
            acc=self._bars.pop(k)
            rows.append((k[0],k[1],acc[5],acc[0],round(acc[1],4),round(acc[2],4),len(acc[3]),acc[4] or None))
        try: self.store.add_bars(rows); self.stats["bars_written"]+=len(rows)
        except Exception as e: log.debug("bars: %s", e)
    async def _flush_loop(self):
        while True:
            await asyncio.sleep(0.4)
            if self._trade_buf:
                buf,self._trade_buf=self._trade_buf,[]
                for tr in buf:
                    try: self.store.add_trade(tr)
                    except Exception as e: log.debug("flush trade: %s", e)
            self._flush_bars()
            if self._amm_buf:
                buf,self._amm_buf=self._amm_buf,[]
                with self.store._lock:
                    self.store._conn.executemany("""INSERT INTO amm_trades(pool,ts,tx,trader,is_buy,sol,tokens,price,mcap_sol,liq_sol) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        [(x["pool"],x["ts"],x.get("tx"),x.get("trader"),1 if x.get("is_buy") else 0,x.get("sol"),x.get("tokens"),x.get("price"),x.get("mcap_sol"),x.get("liq_sol")) for x in buf]); self.store._conn.commit()
    async def _migrate_consumer(self):
        q=self.bus.subscribe("migrate")
        while True:
            ev=await q.get(); mint=ev.get("mint"); st=self.states.get(mint) if mint else None
            if st is None or st.state=="bonded": continue
            st.state="bonded"; st.bonded_at=time.time(); self.store.set_state(mint,"bonded"); self.stats["bonded"]+=1
            log.info("🎓 BONDED %s %s (%.0fs, %d buyers, %.1f SOL)", st.symbol or mint[:6], mint[:8], st.age(), len(st.buyers), st.buy_sol_total)
            await self.notifier.send(f"🎓 <b>BONDED</b> ${st.symbol} <code>{mint}</code>\n{st.age():.0f}s · {len(st.buyers)} buyers · {st.buy_sol_total:.1f} SOL", html=True)

    # ---------------- AMM / post-grad ----------------
    async def _pool_consumer(self):
        q=self.bus.subscribe("pool_created")
        while True:
            ev=await q.get()
            try: self._on_pool(ev)
            except Exception as e: log.exception("on_pool: %s", e)
    def _on_pool(self, ev):
        pool=ev.get("pool"); base=ev.get("base_mint"); quote=ev.get("quote_mint")
        if not pool or not base or pool in self.pools: return
        if not is_sol_quote(quote) or base==WSOL_MINT: self.stats["pools_non_sol"]+=1; return
        bdec=int(ev.get("base_decimals",6)); qdec=int(ev.get("quote_decimals",9))
        base_tokens=float(ev.get("pool_base_amount") or 0)/(10**bdec); liq=float(ev.get("pool_quote_amount") or 0)/(10**qdec)
        known=self.store.one("SELECT 1 FROM tokens WHERE mint=?", (base,)) is not None
        looks_grad=140e6<=base_tokens<=320e6 and 50<=liq<=140
        if not (looks_grad or known): self.stats["pools_not_grad"]+=1; return
        now=time.time(); price=amm_price(ev.get("pool_quote_amount") or 0, ev.get("pool_base_amount") or 0, bdec, qdec); mcap=price*1e9
        token=self.states.get(base); st=GradState(pool=pool,base_mint=base,quote_mint=quote,bdec=bdec,qdec=qdec,creator=ev.get("coin_creator") or ev.get("creator") or "",created_at=now,mayhem=bool(token.mayhem) if token else False)
        st.init_liq_sol=liq; st.init_mcap_sol=mcap; st.liq_sol=liq; st.mcap_sol=mcap; st.price=price; st.peak_mcap=mcap; st.state="watch"
        self.pools[pool]=st; self.stats["pools"]+=1
        self.store.execute("""INSERT OR REPLACE INTO pools(pool,base_mint,quote_mint,bdec,qdec,supply,creator,created_ts,init_liq_sol,init_mcap_sol,mayhem,state,last_ts,peak_mcap) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (pool,base,quote,bdec,qdec,1e9,st.creator,now,liq,mcap,int(st.mayhem),"watch",now,mcap))
        log.info("🏊 POOL graduation %s liq=%.1f SOL mcap≈%.0f SOL", base[:8], liq, mcap)
    async def _amm_trade_consumer(self):
        q=self.bus.subscribe("amm_trade")
        while True:
            ev=await q.get(); st=self.pools.get(ev.get("pool"))
            if st is None: self.stats["amm_orphan"]+=1; continue
            st.observe(ev); self.stats["amm_trades"]+=1
            if st.track:
                self._amm_buf.append({"pool":st.pool,"ts":float(ev.get("_ts") or time.time()),"tx":ev.get("signature"),"trader":ev.get("user"),"is_buy":ev.get("is_buy"),"sol":float(ev.get("quote_amount") or 0)/(10**st.qdec),"tokens":float(ev.get("base_amount") or 0)/(10**st.bdec),"price":st.price,"mcap_sol":st.mcap_sol,"liq_sol":st.liq_sol})
    async def _pg_tick(self, now):
        if not self.pools: return
        self.open_runner_pools={r["pool"] for r in self.store.q("SELECT pool FROM positions WHERE status='open' AND kind='runner' AND pool IS NOT NULL")}
        items=sorted(self.pools.values(), key=lambda x:x.last_ts or x.created_at, reverse=True)[:self.s.runner_max_tracked_pools]
        feats={}
        for st in items:
            if now-(st.last_ts or st.created_at)>1800 and st.pool not in self.open_runner_pools:
                self.pools.pop(st.pool,None); continue
            F=self.pg_agent.features(st); feats[st.pool]=F; d=self.runner.decide(F); st.last_score=d["score"]; self.stats["pg_scored"]+=1
            if now-self._shadow_last.get(st.pool,0)>1800:
                ctx=pg_pullback_signal(st,F,now)
                if ctx:
                    self._shadow_last[st.pool]=now; self.store.add_shadow("pg_pullback","pg",st.base_mint,st.pool,now,st.mcap_sol,ctx); self.stats["shadow_pg_pullback"]+=1
                    log.info("👻 SHADOW pg_pullback %s mcap=%.0f SOL dd=%.0f%% ath=%.1fx", st.base_mint[:8], st.mcap_sol, ctx["drawdown"]*100, ctx["ath_mult"])
            if PG_RANK[d["tier"]]>=PG_RANK["SETUP"]: st.confirm_count+=1
            else: st.confirm_count=0
            tok=self.states.get(st.base_mint)  # la posizione curva continua a vivere sul prezzo AMM dopo la graduation
            if tok is not None and st.mcap_sol:
                tok.mcap_sol=st.mcap_sol; tok.peak_mcap=max(tok.peak_mcap or 0.0, st.mcap_sol)
            self._top_pg_score=max(self._top_pg_score,d["score"])
            for k,v in d["gates"].items():
                if not v: self.stats[f"pg_gate_ko_{k}"]+=1
            tier=d["tier"]
            if PG_RANK[tier]>=PG_RANK["SETUP"]:
                veto=[]
                if st.creator and st.creator in self._blacklist: veto.append("creator_serial_rugger")
                if f"pg:{tier}" in self._demoted: veto.append("tier_retrocesso_revisore")
                tw=self._twins_veto(st.base_mint)
                if tw: veto.append(tw)
                if veto:
                    self.stats["pg_censored"]+=1
                    log.info("🛡️ CENSORE PG %s %s → osservazione: %s", tier, st.base_mint[:8], ",".join(veto))
                    d={**d,"tier":"WATCH","gates":{**d.get("gates",{}),"censore":veto}}; tier="WATCH"
            if PG_RANK[tier]>PG_RANK.get(st.last_tier,0) and tier!="NONE" and now-self._pg_last_signal.get(st.pool,0)>60:
                self._pg_last_signal[st.pool]=now; st.last_tier=tier; st.track=True; await self._pg_emit(st,d,F)
            if PG_RANK[tier]>=PG_RANK["SETUP"] and st.confirm_count>=int(getattr(self.s,"entry_confirm_ticks",2)) and st.last_signal_id and not st.opened_episode:
                if self.rbook.open_count()<self.s.runner_max_open and self.exit.realized_today()>-float(getattr(self.s,"max_daily_loss_sol",1.0)):
                    if not self.store.one("SELECT id FROM positions WHERE pool=? AND status='open'", (st.pool,)):
                        self.rbook.open_position(st,st.last_signal_id,st.mcap_sol,st.liq_sol); self.open_runner_pools.add(st.pool); st.opened_episode=True
            if PG_RANK[tier]<PG_RANK["SETUP"]: st.opened_episode=False
        for res in self.rbook.tick(self.pools,feats):
            self.stats["pg_exits"]+=1; self.bus.publish("exit",res)
            log.info("%s RUNNER %s %s %.2fx pnl=%+.4f SOL — %s", "🟢" if res["pnl_sol"]>0 else "🔴", res["action"], res["mint"][:8], res["mult"], res["pnl_sol"], res["reason"])
    async def _pg_emit(self, st, d, F):
        sid=self.store.add_pg_signal({"pool":st.pool,"base_mint":st.base_mint,"ts":time.time(),"tier":d["tier"],"score":d["score"],"price":st.price,"mcap_sol":st.mcap_sol,"liq_sol":st.liq_sol,"age_s":F.get("pg_age_s",0),"gates":d["gates"],"plan":d["plan"],"features":F}); st.last_signal_id=sid
        self.stats[f"pg_signal_{d['tier'].lower()}"]+=1; self.bus.publish("pg_signal",{"pool":st.pool,"base_mint":st.base_mint,"tier":d["tier"],"score":d["score"],"mcap_sol":st.mcap_sol,"liq_sol":st.liq_sol})
        log.info("🏃 PG %s %s score=%.3f mcap=%.0f SOL liq=%.1f age=%.0fs", d["tier"], st.base_mint[:8], d["score"], st.mcap_sol, st.liq_sol, F.get("pg_age_s",0))

    # ---------------- tick ----------------
    async def _tick_loop(self):
        while True:
            await asyncio.sleep(self.s.tick_seconds); await self._tick()
    async def _tick(self):
        self._tick_count+=1; now=time.time(); self.agents["context"].tick()
        await asyncio.to_thread(self._refresh_guardian_sync, now)
        if self._tick_count%15==0:
            self.open_pos_mints={r["mint"] for r in self.store.q("SELECT mint FROM positions WHERE status='open' AND kind='curve'")}
        feats={}; alive=0
        for mint,st in list(self.states.items()):
            if st.state=="dead": continue
            if st.state=="bonded":
                if mint in self.open_pos_mints: feats[mint]=self.agents["curve"].features(st)
                continue
            age=st.age(now); idle=now-(st.last_ts or st.created_at)
            if st.state=="new":
                F0=self.agents["curve"].features(st)
                promote=F0.get("buy_sol_60s",0)>=self.s.prefilter_min_sol_60s and F0.get("unique_buyers_life",0)>=self.s.prefilter_min_buyers
                if promote or (age<20 and st.n_trades>0):
                    st.state="watch"; st.persist=True; self.store.set_state(mint,"watch"); self.stats["promoted"]+=1
                elif now>self.trial_until.get(mint,now):
                    st.state="dead"; self.store.set_state(mint,"dead"); self._flush_token_stats(st); st.trades.clear(); self.stats["rejected"]+=1; continue
            if st.state!="watch": continue
            if (idle>self.s.kill_no_buy_seconds and age>self.s.kill_no_buy_seconds) or age>self.s.max_watch_seconds*4:
                st.state="dead"; self.store.set_state(mint,"dead"); self._flush_token_stats(st)
                if mint not in self.open_pos_mints: st.trades.clear()
                continue
            alive+=1; F=self._features(st); feats[mint]=F
            if "shadow_sl" not in st.meta:
                ctx=second_leg_signal(st,F,now)
                if ctx:
                    st.meta["shadow_sl"]=now; self.store.add_shadow("second_leg","curve",mint,"",now,F.get("mcap_sol",0),ctx); self.stats["shadow_second_leg"]+=1
                    log.info("👻 SHADOW second_leg %s mcap=%.0f SOL dd=%.0f%% buyers60=%d", mint[:8], F.get("mcap_sol",0), ctx["drawdown"]*100, ctx["buyers_60s"])
            if "shadow_ex" not in st.meta:
                ctx=esplosivo60_signal(st,F,now)
                if ctx:
                    st.meta["shadow_ex"]=now; self.store.add_shadow("esplosivo60","curve",mint,"",now,F.get("mcap_sol",0),ctx); self.stats["shadow_esplosivo60"]+=1
                    log.info("👻 SHADOW esplosivo60 %s mcap=%.0f SOL ret60=%.0f%% buyers60=%d", mint[:8], F.get("mcap_sol",0), ctx["ret_from_min"]*100, ctx["buyers_60s"])
            if "gem_fired" not in st.meta:
                gctx=slancio_signal(st,F,now)
                if gctx:
                    st.meta["gem_fired"]=now; await self._gem_emit(st,F,gctx,now)
            d=self.scorer.decide(st,F,self.enr.sol_price); st.last_score=d["score"]; self.stats["scored"]+=1
            if now-st._last_snap>=self.s.snapshot_every_s:
                st._last_snap=now; self.store.add_snapshot(mint,now,age,F.get("mcap_sol",0),F,d["score"],d.get("p_bond"),d.get("p_2x"),d.get("p_5x"))
            tier=d["tier"]
            if tier in ("ENTRY","STRONG"):
                st.meta["entry_confirm"]=int(st.meta.get("entry_confirm",0))+1
                if st.meta["entry_confirm"]<int(getattr(self.s,"entry_confirm_ticks",2)):
                    tier="WATCH"; d={**d,"tier":"WATCH","plan":{}}   # spike di un solo tick: solo osservazione
            else:
                st.meta["entry_confirm"]=0
            if tier in ("ENTRY","STRONG"):
                self._entry_times=[t for t in self._entry_times if now-t<3600]
                if len(self._entry_times)>=self.s.max_entry_per_hour: tier="WATCH"; d={**d,"tier":"WATCH","plan":{}}
            if tier in ("ENTRY","STRONG"):
                reasons=censor_check(st,F,now,self._blacklist,self._regime_label)
                if f"curve:{tier}" in self._demoted: reasons.append("tier_retrocesso_revisore")
                if reasons:
                    self.stats["censored"]+=1
                    log.info("🛡️ CENSORE %s %s → osservazione: %s", tier, mint[:8], ",".join(reasons))
                    d={**d,"tier":"WATCH","plan":{},"gates":{**d.get("gates",{}),"censore":reasons}}; tier="WATCH"
            if TIER_RANK[tier]>TIER_RANK.get(st.last_tier,0) and tier!="NONE" and now-self._last_signal.get(mint,0)>45:
                self._signal_times=[t for t in self._signal_times if now-t<3600]
                if len(self._signal_times)>=self.s.max_signals_per_hour:
                    st.last_tier=tier; self._last_signal[mint]=now; self.stats["signals_rate_limited"]+=1; continue
                self._last_signal[mint]=now; st.last_tier=tier; self._signal_times.append(now)
                if tier in ("ENTRY","STRONG"): self._entry_times.append(now)
                await self._emit(st,d,F)
        for res in self.exit.tick(self.states,feats):
            self.stats["exits"]+=1; self.bus.publish("exit",res)
            log.info("%s %s %s %.2fx pnl=%+.4f SOL — %s", "🟢" if res["pnl_sol"]>0 else "🔴", res["action"], res["mint"][:8], res["mult"], res["pnl_sol"], res["reason"])
        await self._pg_tick(now); self.stats["alive"]=alive; self.stats["tracked_states"]=len(self.states)
    def _features(self, st):
        F={}
        for name,agent in self.agents.items():
            try:
                if name=="walletgraph": agent.observe(st,{})
                F.update(agent.features(st) or {})
            except Exception as e: log.debug("agent %s: %s", name, e)
        F["creator_prior_launches"]=float(st.meta.get("creator_prior",0) or 0)
        return F
    async def _gem_emit(self, st, F, ctx, now):
        """Motore GEMME: alert in tempo reale durante la formazione dell'esplosione.
        Passa dal Censore come ogni emissione operativa; il Revisore lo retrocede
        da solo se la sua finestra di 100 segnali risolti torna negativa."""
        reasons=censor_check(st,F,now,self._blacklist,self._regime_label)
        if "curve:SLANCIO" in self._demoted: reasons.append("tier_retrocesso_revisore")
        if reasons:
            self.stats["gem_censored"]+=1
            log.info("🛡️ GEMMA censurata %s: %s", st.mint[:8], ",".join(reasons))
            return
        self._gem_times=[t for t in self._gem_times if now-t<3600]
        if len(self._gem_times)>=20:
            self.stats["gem_rate_limited"]+=1; return
        self._gem_times.append(now)
        d={"tier":"SLANCIO","score":round(min(1.0,0.5+float(ctx["ret_from_min"])),3),
           "gates":{"censore":[],"pattern":"slancio_intra_minuto",**ctx},
           "plan":{"ladder":[{"mult":1.8,"sell_pct":.25},{"mult":3.0,"sell_pct":.25},{"mult":6.0,"sell_pct":.25}],
                   "stop_loss_pct":0.35,"size_sol":float(getattr(self.s,"paper_size_sol",0.05) or 0.05)}}
        log.info("🚀 GEMMA %s mcap=%.0f SOL ret=%.0f%% buyers15=%d (pattern madre: p2x=%.0f%%)",
                 st.mint[:8], F.get("mcap_sol",0), ctx["ret_from_min"]*100, ctx["buyers_15s"], ctx["pattern_base_p2x"]*100)
        await self._emit(st,d,F)
    async def _emit(self, st, d, F):
        sig={"mint":st.mint,"ts":time.time(),"tier":d["tier"],"score":d["score"],"price_sol":F.get("price_sol"),"mcap_sol":F.get("mcap_sol"),"age_s":F.get("age_s"),"sol_price":self.enr.sol_price,"gates":d["gates"],"plan":d["plan"],"features":F}
        sid=self.store.add_signal(sig); st.signals.append({"ts":sig["ts"],"tier":sig["tier"],"score":sig["score"],"id":sid}); self.stats[f"signal_{d['tier'].lower()}"]+=1
        self.bus.publish("signal",{**sig,"id":sid,"name":st.name,"symbol":st.symbol})
        can_open = d["tier"] in ("STRONG","SLANCIO")  # ricostruzione: il prior non calibrato non autorizza posizioni
        if d["tier"] in ("ENTRY","STRONG","SLANCIO") and can_open and self.exit.open_count()<self.s.max_open_positions:
            if self.exit.realized_today()<=-float(getattr(self.s,"max_daily_loss_sol",1.0)):
                self.stats["open_skipped_daily_loss"]+=1
            elif not self.store.one("SELECT id FROM positions WHERE mint=? AND status='open' AND kind='curve'", (st.mint,)):
                self.exit.open_position(st.mint,sid,F.get("mcap_sol",0),F.get("price_sol",0)); self.open_pos_mints.add(st.mint)
        await self.notifier.alert(st,d,F,self.enr.sol_price,sig)
    def _flush_token_stats(self, st):
        try:
            self.store.execute("""INSERT INTO token_stats(mint,n_buys,n_sells,buy_sol,sell_sol,n_buyers,peak_mcap,last_mcap,lifetime_s,state,lane) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(mint) DO UPDATE SET n_buys=excluded.n_buys,n_sells=excluded.n_sells,buy_sol=excluded.buy_sol,sell_sol=excluded.sell_sol,n_buyers=excluded.n_buyers,peak_mcap=excluded.peak_mcap,last_mcap=excluded.last_mcap,lifetime_s=excluded.lifetime_s,state=excluded.state,lane=excluded.lane""",
                (st.mint,st.n_buys,st.n_sells,st.buy_sol_total,st.sell_sol_total,len(st.buyers),st.peak_mcap,st.mcap_sol,max(0.0,(st.last_ts or st.created_at)-st.created_at),st.state,st.lane))
        except Exception as e: log.debug("token_stats: %s", e)
    async def _housekeeping(self):
        last_checkpoint=time.time()
        while True:
            await asyncio.sleep(30); now=time.time()
            for m,st in list(self.states.items()):
                if st.state=="dead" and st.n_trades: self._flush_token_stats(st); st.n_trades=0
            cutoff=now-self.s.max_watch_seconds*6
            for m,st in list(self.states.items()):
                if st.state in ("dead","bonded") and (st.last_ts or st.created_at)<cutoff and m not in self.open_pos_mints:
                    self.states.pop(m,None); self._seen_creates.discard(m); self.trial_until.pop(m,None)
            if now-last_checkpoint>600: last_checkpoint=now; self.store.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    async def _quote_price_loop(self):
        while True:
            await asyncio.sleep(60)
            try:
                # quote_prices e' indicizzato per mint QUOTE (cross): mai scrivere chiavi di token sol-lane
                unknown=[m for m in self._quote_mints_seen if m not in self.feed.quote_prices][:50]
                if unknown and self.enr.sol_price:
                    usd=await self.enr.prices_usd(unknown)
                    for m,p in usd.items(): self.feed.quote_prices[m]=p/self.enr.sol_price
            except Exception as e: log.debug("quote prices: %s", e)
    async def _heartbeat(self):
        while True:
            await asyncio.sleep(60); s=dict(self.stats); gates=sorted(((k.replace("pg_gate_ko_",""),v) for k,v in s.items() if k.startswith("pg_gate_ko_")), key=lambda x:-x[1])[:3]
            log.info("♥ feed trade/s=%.1f | curve trades=%d | watch=%d | pools=%d pg_scored=%d top_pg=%.3f | WATCH=%d ENTRY=%d PG=%d/%d | gateKO=%s", self.feed.health().get("trades_per_s",0), s.get("trades",0), s.get("alive",0), len(self.pools), s.get("pg_scored",0), self._top_pg_score, s.get("signal_watch",0), s.get("signal_entry",0)+s.get("signal_strong",0), s.get("pg_signal_watch",0), s.get("pg_signal_setup",0)+s.get("pg_signal_run",0), gates)
    def health(self):
        fh=self.feed.health() if self.s.feed in ("onchain","both") else {}; ah=self.amm.health() if self.s.amm_enabled else {}
        return {"uptime_s":round(time.time()-self.started_at,1),"feed":self.s.feed,"ws_connected":self.feed.connected if self.s.feed in ("onchain","both") else self.pp.connected,
                "ws_reconnects":fh.get("reconnects",self.pp.reconnects),"events":fh.get("counts",{}).get("notif",self.pp.events),
                "trades_per_s":fh.get("trades_per_s",0),"notif_per_s":fh.get("notif_per_s",0),"feed_counts":fh.get("counts",{}),
                "lanes_pct":fh.get("lanes_pct",{}),"amm":ah,"pools_tracked":len(self.pools),"pg_top_score":round(self._top_pg_score,3),
                "sol_price":self.enr.sol_price,"open_positions":self.exit.open_count(),"open_runner_positions":self.rbook.open_count(),
                "realized_today_sol":round(self.exit.realized_today(),5),"model":"trained" if self.scorer.model is not None else "prior","stats":dict(self.stats)}
