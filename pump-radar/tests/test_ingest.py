import asyncio, base64, json, struct
from pumpradar.bus import Bus
from pumpradar.ingest.onchain import OnchainFeed
from pumpradar.ingest.amm import AmmFeed
from tests.test_decoders import trade_payload
from pumpradar.ingest.pumpevent import DISC_AMM_BUY

def notification(payload: bytes):
    return json.dumps({"params":{"result":{"value":{"signature":"sig","slot":123,"err":None,"logs":["Program log: test", "Program data: "+base64.b64encode(payload).decode()]}}}})

def test_onchain_feed_decodes_trade_event():
    async def go():
        bus=Bus(); q=bus.subscribe("trade"); feed=OnchainFeed(bus,["wss://example.invalid"])
        feed._handle(notification(trade_payload()))
        ev=await asyncio.wait_for(q.get(),1)
        assert ev["mint"] and ev["lane"]=="sol" and ev["marketCapSol"]>0 and ev["traderPublicKey"]
        assert feed.health()["counts"]["trade"]==1
    asyncio.run(go())

def test_amm_feed_decodes_trade_event():
    async def go():
        bus=Bus(); q=bus.subscribe("amm_trade"); feed=AmmFeed(bus,["wss://example.invalid"])
        d=bytearray(344); d[0:8]=DISC_AMM_BUY; d[8:16]=struct.pack("<q",1794010274); d[16:24]=struct.pack("<Q",1000000)
        d[48:56]=struct.pack("<Q",200000000*1000000); d[56:64]=struct.pack("<Q",90*10**9); d[64:72]=struct.pack("<Q",10**9)
        d[120:152]=bytes(range(96,128)); d[152:184]=bytes(range(32))
        feed._handle(notification(bytes(d)))
        ev=await asyncio.wait_for(q.get(),1)
        assert ev["is_buy"] and ev["pool"] and ev["user"]
        assert feed.health()["counts"]["trade"]==1
    asyncio.run(go())
