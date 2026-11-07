from __future__ import annotations
import asyncio, random, time, uuid
from .ingest.pumpevent import WSOL_MINT

PROG={"patched":False,"speed":60.0,"real_time":time.time}

def start_virtual_clock(speed: float):
    if PROG.get("patched"): return
    real=time.time; t0=real(); PROG.update({"patched":True,"speed":speed,"real_time":real})
    time.time=lambda: t0+(real()-t0)*speed

def _mint(prefix, i):
    return (f"SIM{prefix}{i:04d}"+uuid.uuid4().hex)[:44].ljust(32,"x")

class SimMarket:
    CLASSES=[("dead",0.885),("pump_dump",0.060),("organic",0.045),("engineered",0.008),("mega",0.002)]
    def __init__(self, bus, n_tokens=400, speed=60.0, seed=42):
        self.bus=bus; self.n=n_tokens; self.speed=max(1.0,speed); self.rng=random.Random(seed); PROG["speed"]=speed
        self.smart=[f"SMART{i:03d}"+uuid.uuid4().hex[:12] for i in range(30)]
        self.retail=[uuid.uuid4().hex[:32] for _ in range(3000)]; self.snipers=[uuid.uuid4().hex[:32] for _ in range(60)]
    def _class(self):
        r=self.rng.random(); acc=0.0
        for name,p in self.CLASSES:
            acc+=p
            if r<=acc: return name
        return "dead"
    def _schedule(self, cls):
        rng=self.rng; ev=[]
        if cls=="dead":
            for i in range(rng.randint(2,11)):
                ev.append((1+i*rng.uniform(1.5,8),{"trader":rng.choice(self.retail),"is_buy":True,"sol":round(rng.lognormvariate(-2.6,0.7),4)}))
            if rng.random()<0.4: ev.append((rng.uniform(20,70),{"trader":rng.choice(self.retail),"is_buy":False,"sol":round(rng.uniform(0.05,0.3),4)}))
        elif cls=="pump_dump":
            nb=rng.randint(18,45)
            for i in range(nb): ev.append((2+i*rng.uniform(0.7,2.2),{"trader":rng.choice(self.retail),"is_buy":True,"sol":round(rng.lognormvariate(-1.5,0.6),4)}))
            for i in range(rng.randint(6,16)): ev.append((nb*1.4+i*rng.uniform(0.4,2.0),{"trader":rng.choice(self.retail),"is_buy":False,"sol":round(rng.lognormvariate(-0.9,0.5),4)}))
        elif cls=="organic":
            nb=rng.randint(45,130); target=rng.uniform(120,420); acc=0.0
            for i in range(nb):
                t=2+i*rng.uniform(0.8,3.0); sol=max(0.03,min(6.0,target*rng.paretovariate(2.2)*0.05)); acc+=sol
                w=rng.choice(self.smart) if rng.random()<0.18 else rng.choice(self.retail)
                ev.append((t,{"trader":w,"is_buy":True,"sol":round(sol,4)}))
                if acc>60 and rng.random()<0.25: ev.append((t+rng.uniform(0.5,4),{"trader":rng.choice(self.retail),"is_buy":False,"sol":round(sol*rng.uniform(0.3,1.1),4)}))
        elif cls=="engineered":
            w=rng.choice(self.snipers); ev.append((1.0,{"trader":w,"is_buy":True,"sol":round(rng.uniform(18,45),3)}))
            for i in range(rng.randint(1,3)): ev.append((1.2+i*0.3,{"trader":rng.choice(self.snipers),"is_buy":True,"sol":round(rng.uniform(18,45),3)}))
            for i in range(rng.randint(2,6)): ev.append((8+i*2,{"trader":w,"is_buy":False,"sol":round(rng.uniform(5,25),3)}))
        else:
            nb=rng.randint(120,260)
            for i in range(nb):
                t=2+i*rng.uniform(0.4,1.6); sol=round(max(0.05,min(9.0,rng.paretovariate(1.9)*1.4)),4)
                w=rng.choice(self.smart) if rng.random()<0.30 else rng.choice(self.retail)
                ev.append((t,{"trader":w,"is_buy":True,"sol":sol}))
                if rng.random()<0.18: ev.append((t+rng.uniform(0.3,3),{"trader":rng.choice(self.retail),"is_buy":False,"sol":round(sol*rng.uniform(0.2,0.8),4)}))
        ev.sort(key=lambda x:x[0]); return ev
    async def run(self):
        start_virtual_clock(self.speed)
        await asyncio.gather(*(self._one(i) for i in range(self.n)))
    async def _one(self, i):
        rng=random.Random(self.rng.random())
        await asyncio.sleep((i*2.0+rng.uniform(0,2))/self.speed)
        cls=self._class(); mint=_mint(cls[:3].upper(),i); creator=uuid.uuid4().hex[:32]
        vsol,vtok=30.0,1_073_000_000.0; k=vsol*vtok; last=0.0
        self.bus.publish("create",{"_ts":time.time(),"mint":mint,"txType":"create","traderPublicKey":creator,"solAmount":0.0,
            "vSolInBondingCurve":vsol,"vTokensInBondingCurve":vtok,"marketCapSol":vsol*1e9/vtok,
            "name":f"Sim {cls} {i}","symbol":f"S{i:04d}","uri":"","is_mayhem_mode":False,"pool":"pump",
            "lane":"sol","quoteMint":"SOL","signature":uuid.uuid4().hex})
        graduated=False
        for off,tr in self._schedule(cls):
            await asyncio.sleep(max(0.0,(off-last))/self.speed); last=off
            if tr["is_buy"]:
                before=vtok; net=tr["sol"]*0.99; vsol+=net; vtok=k/vsol; tokens=before-vtok
            else:
                tokens=tr["sol"]*vtok/max(vsol,1e-9); vtok+=tokens; vsol=k/vtok
            rtok=max(0.0,793_100_000.0-(1_073_000_000.0-vtok))
            self.bus.publish("trade",{"_ts":time.time(),"mint":mint,"txType":"buy" if tr["is_buy"] else "sell",
                "signature":uuid.uuid4().hex,"traderPublicKey":tr["trader"],"solAmount":tr["sol"],"tokenAmount":tokens,
                "vSolInBondingCurve":vsol,"vTokensInBondingCurve":vtok,"marketCapSol":vsol*1e9/vtok,
                "realTokenReserves":rtok,"realSolReserves":max(0.0,vsol-30.0),"lane":"sol","quoteMint":"SOL","slot":int(time.time()/0.4)})
            if vsol>=115:
                graduated=True; break
        if graduated or cls in ("organic","mega") and vsol>80:
            self.bus.publish("migrate",{"_ts":time.time(),"mint":mint,"txType":"migrate"})
            await self._postgrad(mint, strong=(cls=="mega"))
    async def _postgrad(self, mint, strong=False):
        rng=random.Random(mint)
        pool=("POOL"+uuid.uuid4().hex)[:44].ljust(32,"p")
        pbase=int(206_900_000*1e6); pquote=int(85*1e9); k=pbase*pquote
        self.bus.publish("pool_created",{"_ts":time.time(),"pool":pool,"base_mint":mint,"quote_mint":WSOL_MINT,
            "base_decimals":6,"quote_decimals":9,"pool_base_amount":pbase,"pool_quote_amount":pquote,
            "creator":uuid.uuid4().hex[:32],"coin_creator":uuid.uuid4().hex[:32],"signature":uuid.uuid4().hex})
        n=140 if strong else 80; last=0.0
        for i in range(n):
            off=5+i*rng.uniform(1,4); await asyncio.sleep(max(0.0,off-last)/self.speed); last=off
            buy=rng.random()<0.72; sol=rng.uniform(0.08,0.9)*(3.0 if strong and i>40 else 1.0)
            if buy:
                dq=int(sol*1e9); new_pquote=pquote+dq; new_pbase=k//new_pquote; base_amount=pbase-new_pbase; pquote,pbase=new_pquote,new_pbase
            else:
                base_amount=int(rng.uniform(100_000,900_000)*1e6); new_pbase=pbase+base_amount; new_pquote=k//new_pbase; sol=(pquote-new_pquote)/1e9; pquote,pbase=new_pquote,new_pbase
            user=rng.choice(self.smart) if rng.random()<0.25 else rng.choice(self.retail)
            self.bus.publish("amm_trade",{"_ts":time.time(),"pool":pool,"user":user,"is_buy":buy,
                "quote_amount":int(abs(sol)*1e9),"base_amount":int(base_amount),"pool_base":pbase,"pool_quote":pquote,
                "signature":uuid.uuid4().hex,"slot":int(time.time()/0.4)})
