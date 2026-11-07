from __future__ import annotations
import asyncio, json, logging, time, urllib.request
log=logging.getLogger("notify")
def _post(url,payload):
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","User-Agent":"pumpradar/1.0"})
    with urllib.request.urlopen(req,timeout=10) as r: return r.status
class Notifier:
    def __init__(self, settings): self.s=settings; self.count=0
    def format_signal(self, st, d, F, sol_price):
        mcap=float(F.get("mcap_sol",0) or 0); usd=mcap*(sol_price or 0); plan=d.get("plan") or {}
        ladder=" → ".join(f"{l['mult']}x({int(l['sell_pct']*100)}%)" for l in plan.get("ladder",[])) or "—"
        icon={"STRONG":"🟢🟢","ENTRY":"🟢","WATCH":"👀","SLANCIO":"🚀"}.get(d.get("tier"),"•")
        return (f"{icon} <b>{d.get('tier')}</b> ${st.symbol} — score <b>{d.get('score',0):.2f}</b>\n"
                f"<code>{st.mint}</code>\n⏱ {F.get('age_s',0):.0f}s | mcap {mcap:.1f} SOL (~${usd:,.0f}) | curva {F.get('curve_progress',0)*100:.0f}%\n"
                f"📈 buy30 {F.get('buy_sol_30s',0):.2f} SOL | B/S {F.get('buy_sell_ratio_life',0):.1f} | buyers {int(F.get('unique_buyers_life',0) or 0)}\n"
                f"🎯 size {plan.get('size_sol','?')} SOL | {ladder} | stop {int(float(plan.get('stop_loss_pct',0.42))*100)}%")
    async def alert(self, st, d, F, sol_price, sig=None):
        self.count+=1; txt=self.format_signal(st,d,F,sol_price)
        if d.get("tier") in ("ENTRY","STRONG","SLANCIO"):
            print(f"[{time.strftime('%H:%M:%S')}] {d['tier']:<6} ${st.symbol:<12} score={d['score']:.3f} mcap={F.get('mcap_sol',0):.1f}SOL age={F.get('age_s',0):.0f}s buyers={int(F.get('unique_buyers_life',0) or 0)}", flush=True)
            await self.send(txt, html=True)   # esterni solo per segnali operativi: i WATCH restano in dashboard/log
        else: log.debug(txt)
    async def send(self, text, html=False):
        if self.s.telegram_token and self.s.telegram_chat:
            try: await asyncio.to_thread(_post, f"https://api.telegram.org/bot{self.s.telegram_token}/sendMessage", {"chat_id":self.s.telegram_chat,"text":text,"parse_mode":"HTML" if html else None,"disable_web_page_preview":True})
            except Exception as e: log.debug("telegram: %s", e)
        if self.s.webhook_url:
            try: await asyncio.to_thread(_post, self.s.webhook_url, {"text":text})
            except Exception: pass
