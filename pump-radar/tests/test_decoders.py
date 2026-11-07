import struct
import pytest
from pumpradar.ingest.pumpevent import (DISC_AMM_BUY, DISC_AMM_POOL, DISC_COMPLETE,
    DISC_CREATE, DISC_TRADE, SOL_QUOTE, amm_price, decode_amm_pool, decode_amm_trade,
    decode_complete, decode_create, decode_trade, is_sol_quote, classify_lane)
from pumpradar.utils import progress_from_rtok

def u64(v): return struct.pack("<Q", int(v))
def put(d, off, b): d[off:off+len(b)] = b

def trade_payload(cross=False, vsol_sol=50.541035069):
    d=bytearray(391)
    put(d,0,DISC_TRADE); put(d,8,bytes(range(32))); put(d,40,u64(2.372039298*1e9)); put(d,48,u64(28551947142489))
    d[56]=0; put(d,57,bytes(range(32,64))); put(d,89,struct.pack("<q",1794010274))
    vsol_raw=int(vsol_sol*1e9); rsol_raw=int((20.541035069 if not cross else 0)*1e9)
    put(d,97,u64(0 if cross else vsol_raw)); put(d,105,u64(636908209079386)); put(d,113,u64(0 if cross else rsol_raw)); put(d,121,u64(357008209079386))
    put(d,258,struct.pack("<I",4)+b"sell")
    off=266+1+32; put(d,off,struct.pack("<I",0)); off+=4
    put(d,off,bytes(32) if not cross else bytes(range(64,96))); off+=32
    if cross:
        put(d,off,u64(16145841)); put(d,off+8,u64(244306510000)); put(d,off+16,u64(1000000))
    else:
        put(d,off,u64(2.372039298*1e9)); put(d,off+8,u64(vsol_raw)); put(d,off+16,u64(rsol_raw))
    return bytes(d)

def test_trade_sol_quote_consistency():
    t=decode_trade(trade_payload())
    assert t and t["is_sol_quote"] and t["is_buy"] is False
    assert t["quote_amount"] == pytest.approx(t["sol_amount"])
    assert t["vquote"] == pytest.approx(t["vsol"])
    assert t["rquote"] == pytest.approx(t["rsol"])
    assert t["vtok"] == pytest.approx(636908209.079386)
    assert t["rtok"] == pytest.approx(357008209.079386)
    assert classify_lane(t["quote_mint"], t["vsol"], t["vtok"], t["rtok"], t["rsol"]) == "sol"

def test_trade_cross_quote_decoded():
    t=decode_trade(trade_payload(cross=True, vsol_sol=0))
    assert t and not t["is_sol_quote"] and t["vsol"]==0 and t["vquote"]>0
    assert classify_lane(t["quote_mint"], t["vsol"], t["vtok"], t["rtok"], t["rsol"]) == "cross"

def test_progress_from_rtok_matches_sol_progress_for_standard_curve():
    # rtok=357,008,209 token reali rimasti -> vsol implicita 50.541 -> progresso 24.2%
    assert progress_from_rtok(357_008_209) == pytest.approx((50.541035069-30)/85, abs=0.01)
    assert progress_from_rtok(793_100_000) == pytest.approx(0.0, abs=1e-9)
    assert progress_from_rtok(0) == pytest.approx(1.0)

def test_create_and_complete_decode():
    payload=DISC_CREATE+struct.pack("<I",4)+b"Test"+struct.pack("<I",4)+b"TEST"+struct.pack("<I",12)+b"ipfs://abcde"
    payload+=bytes(range(32))+bytes(range(32,64))+bytes(range(64,96))+bytes(range(96,128))
    payload+=struct.pack("<q",1794010274)+u64(1073000000*1000000)+u64(30*10**9)+u64(793100000*1000000)+u64(1000000000*1000000)
    payload+=bytes(32)+bytes([0,0])+bytes(32)+u64(30*10**9)+u64(100)+bytes([0,0])
    c=decode_create(payload); assert c and c["symbol"]=="TEST" and c["vsol"]==30.0 and c["vtok"]==1073000000.0
    comp=bytearray(144); put(comp,0,DISC_COMPLETE); put(comp,8,bytes(range(32))); put(comp,40,bytes(range(32,64))); put(comp,72,bytes(range(64,96))); put(comp,104,struct.pack("<q",1794010274))
    k=decode_complete(bytes(comp)); assert k and k["mint"] and k["is_sol_quote"]

def test_amm_decoders_and_price():
    pool=bytearray(333); put(pool,0,DISC_AMM_POOL); put(pool,8,struct.pack("<q",1794010274)); put(pool,18,bytes(range(32))); put(pool,50,bytes(range(32,64))); put(pool,82,bytes(range(64,96)))
    pool[114]=6; pool[115]=9; put(pool,116,u64(206900000*1000000)); put(pool,124,u64(85*10**9)); put(pool,132,u64(206900000*1000000)); put(pool,140,u64(85*10**9)); put(pool,173,bytes(range(96,128)))
    p=decode_amm_pool(bytes(pool)); assert p and p["pool_base_amount"]==206900000*1000000
    assert amm_price(p["pool_quote_amount"], p["pool_base_amount"], 6, 9)*1e9 == pytest.approx(410.8, rel=0.02)
    tr=bytearray(344); put(tr,0,DISC_AMM_BUY); put(tr,8,struct.pack("<q",1794010274)); put(tr,16,u64(1000000)); put(tr,48,u64(200000000*1000000)); put(tr,56,u64(90*10**9)); put(tr,64,u64(10**9)); put(tr,120,bytes(range(96,128))); put(tr,152,bytes(range(32)))
    t=decode_amm_trade(bytes(tr)); assert t and t["is_buy"] and t["pool"] and t["user"]

def test_wrong_discriminator_rejected():
    d=trade_payload(); assert decode_create(d) is None; assert decode_amm_pool(d) is None; assert decode_complete(d) is None
    assert is_sol_quote(SOL_QUOTE)
