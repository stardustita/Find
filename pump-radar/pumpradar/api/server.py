from __future__ import annotations
import json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HTML="""<!doctype html><html lang="it"><head><meta charset="utf-8"><title>PumpRadar</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>:root{--bg:#0b0e13;--panel:#131823;--line:#1f2733;--txt:#e6edf3;--dim:#8b98a9;--green:#25d07a;--yellow:#f5c542;--red:#f2545b;--blue:#4aa8ff}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:13px/1.45 ui-monospace,Menlo,monospace}header{display:flex;gap:14px;align-items:center;padding:12px 18px;border-bottom:1px solid var(--line);flex-wrap:wrap}h1{font-size:15px;margin:0;letter-spacing:.14em;color:var(--blue)}.badge{padding:2px 8px;border-radius:99px;border:1px solid var(--line);color:var(--dim);font-size:11px}.dot{width:8px;height:8px;border-radius:99px;display:inline-block;margin-right:6px}main{padding:14px 18px;display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;min-width:0}h2{font-size:11px;letter-spacing:.16em;color:var(--dim);margin:0 0 8px}.kv{display:grid;grid-template-columns:1fr auto;gap:3px 10px}.kv span:nth-child(odd){color:var(--dim)}table{width:100%;border-collapse:collapse;font-size:12px}th{text-align:left;color:var(--dim);font-weight:400;border-bottom:1px solid var(--line);padding:4px 5px;font-size:10.5px}td{padding:4px 5px;border-bottom:1px solid #171e29;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:190px}.STRONG,.RUN{color:var(--green);font-weight:700}a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}.ENTRY,.SETUP{color:var(--green)}.WATCH{color:var(--yellow)}#feed{height:180px;overflow:auto;font-size:11.5px;color:var(--dim)}.wide{grid-column:1/-1}.neg{color:var(--red)}.pos{color:var(--green)}</style></head><body>
<header><h1>◉ PUMPRADAR</h1><span class="badge"><span id="wsdot" class="dot" style="background:#666"></span><span id="ws">connessione…</span></span><span class="badge">modello: <b id="model">–</b></span><span class="badge">SOL <b id="solpx">–</b></span><span class="badge">trade/s <b id="tps">–</b></span><span class="badge">pool <b id="pools">–</b></span></header>
<main><section><h2>Stato sistema</h2><div class="kv" id="health"></div></section>
<section><h2>Qualità feed on-chain</h2><div class="kv" id="feedq"></div></section>
<section><h2>Segnali curva</h2><table id="sig"><thead><tr><th>ora</th><th>tier</th><th>sym</th><th>score</th><th>mcap</th><th>età</th><th>buyers</th></tr></thead><tbody></tbody></table></section>
<section><h2>Segnali post-graduation (caccia 100x)</h2><table id="pg"><thead><tr><th>ora</th><th>tier</th><th>token</th><th>score</th><th>mcap</th><th>liq</th><th>età</th></tr></thead><tbody></tbody></table></section>
<section><h2>Posizioni</h2><table id="pos"><thead><tr><th>tipo</th><th>token</th><th>mult</th><th>pnl SOL</th><th>stato</th><th>motivo</th></tr></thead><tbody></tbody></table></section>
<section class="wide"><h2>Flusso eventi</h2><div id="feed"></div></section></main>
<script>const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));function row(a,cls){return '<tr'+(cls?' class="'+cls+'"':'')+'>'+a.map(c=>'<td>'+esc(c)+'</td>').join('')+'</tr>'}
function lnk(m,l){return '<a href="https://pump.fun/coin/'+encodeURIComponent(m||'')+'" target="_blank" rel="noopener noreferrer" title="Apri su pump.fun">'+esc(l)+'</a>'}
function rowh(a,cls,raw){return '<tr'+(cls?' class="'+cls+'"':'')+'>'+a.map((c,i)=>'<td>'+(raw&&raw.includes(i)?c:esc(c))+'</td>').join('')+'</tr>'}
async function health(){try{const h=await(await fetch('/api/health')).json();$('ws').textContent=h.ws_connected?'live':'disconnesso';$('wsdot').style.background=h.ws_connected?'var(--green)':'var(--red)';$('model').textContent=h.model==='trained'?'AI addestrata':'prior esperto';$('solpx').textContent=(h.sol_price||0).toFixed(2)+'$';$('tps').textContent=h.trades_per_s||0;$('pools').textContent=h.pools_tracked||0;const st=h.stats||{};$('health').innerHTML=Object.entries({'token tracciati':st.tracked_states||0,'in watch':st.alive||0,'lanci visti':st.creates||0,'promossi':st.promoted||0,'scartati':st.rejected||0,'graduated':st.bonded||0,'recuperati':st.recovered||0,'segn. ENTRY':st.signal_entry||0,'segn. STRONG':st.signal_strong||0,'pool graduation':st.pools||0,'trade AMM':st.amm_trades||0,'posizioni curva':h.open_positions||0,'posizioni runner':h.open_runner_positions||0,'P&L oggi SOL':(h.realized_today_sol||0).toFixed(4),'reconnect':h.ws_reconnects||0}).map(([k,v])=>'<span>'+k+'</span><b>'+v+'</b>').join('');const c=h.feed_counts||{},lanes=h.lanes_pct||{},tot=Math.max(1,c.notif||0);$('feedq').innerHTML=Object.entries({'notifiche/s':h.notif_per_s||0,'trade decodificati':c.trade||0,'tx fallite %':(((c.tx_failed||0)/tot)*100).toFixed(1)+' %','corsia SOL %':(lanes.sol||0)+' %','corsia ALT %':((lanes.alt||0)+(lanes.shallow||0))+' %','corsia CROSS %':(lanes.cross||0)+' %','eventi invalidi':c.invalid||0,'AMM trade/s':(h.amm||{}).trades_per_s||0,'miglior score PG':h.pg_top_score||0}).map(([k,v])=>'<span>'+k+'</span><b>'+v+'</b>').join('')}catch(e){}}
async function tables(){try{const s=await(await fetch('/api/signals?limit=16')).json();document.querySelector('#sig tbody').innerHTML=s.map(r=>rowh([new Date(r.ts*1000).toLocaleTimeString('it-IT'),r.tier,lnk(r.mint,'$'+(r.symbol||(r.mint||'').slice(0,6))),(+r.score).toFixed(2),(+r.mcap_sol||0).toFixed(1)+'S',Math.round(r.age_s||0)+'s',r.buyers||0],r.tier,[2])).join('');const g=await(await fetch('/api/pg-signals?limit=16')).json();document.querySelector('#pg tbody').innerHTML=g.map(r=>rowh([new Date(r.ts*1000).toLocaleTimeString('it-IT'),r.tier,lnk(r.base_mint,(r.base_mint||'').slice(0,8)),(+r.score).toFixed(2),(+r.mcap_sol||0).toFixed(0)+'S',(+r.liq_sol||0).toFixed(1)+'S',Math.round(r.age_s||0)+'s'],r.tier,[2])).join('');const p=await(await fetch('/api/positions?limit=16')).json();document.querySelector('#pos tbody').innerHTML=p.map(r=>rowh([r.kind,lnk(r.mint,'$'+(r.symbol||(r.mint||'').slice(0,6))),((+r.mult)||0).toFixed(2)+'x',((+r.pnl_sol)||0).toFixed(4),r.status,r.reason||''],((+r.pnl_sol)||0)>0?'pos':(((+r.pnl_sol)||0)<0?'neg':''),[1])).join('')}catch(e){}}
const es=new EventSource('/events');es.onmessage=e=>{const d=JSON.parse(e.data);const el=document.createElement('div');el.textContent=new Date().toLocaleTimeString('it-IT')+' · feed '+((d.trades_per_s||0))+' trade/s · pool '+(d.pools_tracked||0)+' · segnali curva '+(d.stats?.signal_entry||0)+' · PG '+(d.stats?.pg_signal_setup||0);const f=$('feed');f.prepend(el);while(f.children.length>120)f.lastChild.remove()};health();tables();setInterval(health,2000);setInterval(tables,3000);</script></body></html>"""

def build_server(orch, host="0.0.0.0", port=8787):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def _json(self, obj, status=200):
            body=json.dumps(obj).encode(); self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_GET(self):
            u=urlparse(self.path); qs=parse_qs(u.query)
            try: limit=max(1,min(200,int((qs.get("limit") or [30])[0])))
            except Exception: limit=30
            try:
                if u.path=="/":
                    body=HTML.encode(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body); return
                if u.path=="/api/health": return self._json(orch.health())
                if u.path=="/api/signals":
                    rows=orch.store.q("SELECT * FROM signals ORDER BY ts DESC LIMIT ?", (limit,)); out=[]
                    for r in rows:
                        try: f=json.loads(r["features"] or "{}")
                        except Exception: f={}
                        sym=orch.store.one("SELECT symbol FROM tokens WHERE mint=?", (r["mint"],))
                        out.append({"ts":r["ts"],"tier":r["tier"],"mint":r["mint"],"score":r["score"],"mcap_sol":r["mcap_sol"],"age_s":r["age_s"],"buyers":f.get("unique_buyers_life"),"symbol":sym["symbol"] if sym else ""})
                    return self._json(out)
                if u.path=="/api/pg-signals":
                    rows=orch.store.q("SELECT * FROM pg_signals ORDER BY ts DESC LIMIT ?", (limit,)); return self._json([dict(r) for r in rows])
                if u.path=="/api/positions":
                    rows=orch.store.q("SELECT * FROM positions ORDER BY opened_ts DESC LIMIT ?", (limit,)); out=[]
                    for r in rows:
                        sym=orch.store.one("SELECT symbol FROM tokens WHERE mint=?", (r["mint"],)); e=float(r["entry_mcap"] or 0) or 1e-9
                        cur=None
                        if r["status"]=="open":  # multiplo corrente, non il picco
                            if r["kind"]=="runner":
                                gs=orch.pools.get(r["pool"] or ""); cur=gs.mcap_sol if gs else None
                            else:
                                stt=orch.states.get(r["mint"]); cur=stt.mcap_sol if stt else None
                        if cur is None: cur=float(r["exit_mcap"] or r["peak_mcap"] or e)
                        out.append({"mint":r["mint"],"symbol":sym["symbol"] if sym else "","kind":r["kind"],"pool":r["pool"],"mult":cur/e,"pnl_sol":r["pnl_sol"],"status":r["status"],"reason":r["reason"],"entry_mcap":e,"peak_mcap":r["peak_mcap"]})
                    return self._json(out)
                if u.path=="/api/stats":
                    s=orch.store; closed=s.one("SELECT COUNT(*) n,SUM(CASE WHEN pnl_sol>0 THEN 1 ELSE 0 END) w,SUM(pnl_sol) pnl,AVG(pnl_pct) avg_pct FROM positions WHERE status='closed'")
                    return self._json({"health":orch.health(),"closed_positions":dict(closed) if closed else {},"signals_by_tier":[dict(r) for r in s.q("SELECT tier,COUNT(*) n FROM signals GROUP BY tier")],"pg_signals_by_tier":[dict(r) for r in s.q("SELECT tier,COUNT(*) n FROM pg_signals GROUP BY tier")],"tokens_by_state":[dict(r) for r in s.q("SELECT state,COUNT(*) n FROM tokens GROUP BY state")]})
                if u.path=="/events":
                    self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.send_header("Cache-Control","no-cache"); self.end_headers()
                    try:
                        while True:
                            self.wfile.write(f"data: {json.dumps(orch.health())}\n\n".encode()); self.wfile.flush(); time.sleep(2)
                    except Exception: return
                return self._json({"error":"not found"},404)
            except Exception as e: return self._json({"error":str(e)},500)
    return ThreadingHTTPServer((host,port), Handler)

# compatibilità col nome usato in versioni precedenti
def build_app(orch): return build_server(orch, orch.s.api_host, orch.s.api_port)
