from __future__ import annotations
import hashlib, struct
from ..utils import INIT_VSOL, TOTAL_SUPPLY, b58encode as b58

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
AMM_PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
SOL_QUOTE = "11111111111111111111111111111111"  # Pubkey::default nei campi quote della curva
WSOL_MINT = "So11111111111111111111111111111111111111112"

DISC_TRADE = bytes.fromhex("bddb7fd34ee661ee")
DISC_CREATE = bytes.fromhex("1b72a94ddeeb6376")
DISC_COMPLETE = bytes.fromhex("5f72619cd42e9808")

def _event_disc(name: str) -> bytes:
    return hashlib.sha256(f"event:{name}".encode()).digest()[:8]

DISC_AMM_BUY = _event_disc("BuyEvent")
DISC_AMM_SELL = _event_disc("SellEvent")
DISC_AMM_POOL = _event_disc("CreatePoolEvent")

def is_sol_quote(mint: str | None) -> bool:
    return mint in (SOL_QUOTE, WSOL_MINT, "SOL", None, "")

def _u64(d: bytes, off: int) -> int:
    return struct.unpack_from("<Q", d, off)[0]

def _i64(d: bytes, off: int) -> int:
    return struct.unpack_from("<q", d, off)[0]

def _read_string(d: bytes, off: int) -> tuple[str, int]:
    if off + 4 > len(d):
        raise ValueError("string truncated")
    n = struct.unpack_from("<I", d, off)[0]
    off += 4
    if n > 10_000 or off + n > len(d):
        raise ValueError("string length invalid")
    return d[off:off+n].decode("utf-8", "replace"), off + n

def classify_lane(quote_mint: str, vsol: float, vtok: float, rtok: float, rsol: float = 0.0) -> str:
    """Classifica la famiglia di curva. Solo 'sol' è modellabile/tradabile.

    - cross: quote diverso da SOL (es. $PUMP); valori nei campi quote.
    - shallow: riserve SOL quasi nulle/economia non standard.
    - alt: mcap coerente ma invariante classica vsol-rsol=30 non rispettata.
    - sol: curva classica verificata.
    """
    if not vtok or not (3e8 <= float(vtok) <= 3e9):
        return "invalid"
    if rtok is None or float(rtok) < 0 or float(rtok) > float(vtok) * 1.05:
        return "invalid"
    if not is_sol_quote(quote_mint):
        return "cross"
    if not vsol or float(vsol) <= 0:
        return "shallow"
    if abs(float(vsol) - float(rsol or 0.0) - INIT_VSOL) <= 1.5:
        return "sol"
    if float(vsol) < 5.0:
        return "shallow"
    return "alt"

def decode_trade(d: bytes) -> dict | None:
    if len(d) < 300 or d[:8] != DISC_TRADE:
        return None
    try:
        mint = b58(d[8:40])
        sol_amount = _u64(d, 40) / 1e9
        token_amount = _u64(d, 48) / 1e6
        is_buy = d[56] == 1
        user = b58(d[57:89])
        ts_chain = _i64(d, 89)
        vsol = _u64(d, 97) / 1e9
        vtok = _u64(d, 105) / 1e6
        rsol = _u64(d, 113) / 1e9
        rtok = _u64(d, 121) / 1e6
        fee_bps = _u64(d, 161)
        fee = _u64(d, 169) / 1e9
        creator = b58(d[177:209])
        creator_fee = _u64(d, 217) / 1e9
        ix_name, off = _read_string(d, 258)
        off += 1   # mayhem_mode
        off += 32  # cashback/buyback fee fields
        if off + 4 > len(d):
            return None
        n_share = struct.unpack_from("<I", d, off)[0]
        off += 4
        tail_fixed = 32 + 8 * 6
        if n_share:
            remaining = len(d) - off - tail_fixed
            # tollera il campo trailing non documentato da 0 o 8 byte
            elem_total = None
            for trailing in (8, 0):
                rem = remaining - trailing
                if rem >= 0 and rem % n_share == 0:
                    elem_total = rem
                    break
            if elem_total is None:
                return None
            off += elem_total
        if off + tail_fixed > len(d):
            return None
        quote_raw = d[off:off+32]
        quote_mint = SOL_QUOTE if not any(quote_raw) else b58(quote_raw)
        off += 32
        quote_amount_raw = _u64(d, off)
        vquote_raw = _u64(d, off + 8)
        rquote_raw = _u64(d, off + 16)
        # SOL ha 9 decimali; i token pump usati come quote hanno 6 decimali.
        qdiv = 1e9 if is_sol_quote(quote_mint) else 1e6
        return {
            "mint": mint, "trader": user, "user": user, "is_buy": is_buy,
            "ts_chain": ts_chain, "sol_amount": sol_amount, "token_amount": token_amount,
            "vsol": vsol, "vtok": vtok, "rsol": rsol, "rtok": rtok,
            "fee_bps": fee_bps, "fee": fee, "creator": creator, "creator_fee": creator_fee,
            "ix": ix_name, "quote_mint": quote_mint, "is_sol_quote": is_sol_quote(quote_mint),
            "quote_amount": quote_amount_raw / qdiv, "vquote": vquote_raw / qdiv,
            "rquote": rquote_raw / qdiv, "quote_amount_raw": quote_amount_raw,
            "vquote_raw": vquote_raw, "rquote_raw": rquote_raw,
            "n_shareholders": n_share,
        }
    except Exception:
        return None

def decode_create(d: bytes) -> dict | None:
    if len(d) < 180 or d[:8] != DISC_CREATE:
        return None
    try:
        off = 8
        name, off = _read_string(d, off)
        symbol, off = _read_string(d, off)
        uri, off = _read_string(d, off)
        mint = b58(d[off:off+32]); off += 32
        curve = b58(d[off:off+32]); off += 32
        user = b58(d[off:off+32]); off += 32
        creator = b58(d[off:off+32]); off += 32
        ts_chain = _i64(d, off); off += 8
        vtok = _u64(d, off) / 1e6; off += 8
        vsol = _u64(d, off) / 1e9; off += 8
        rtok = _u64(d, off) / 1e6; off += 8
        supply = _u64(d, off) / 1e6; off += 8
        off += 32  # token_program
        mayhem = bool(d[off]) if off < len(d) else False; off += 1
        cashback = bool(d[off]) if off < len(d) else False; off += 1
        quote_mint = SOL_QUOTE
        vquote = vsol
        creator_fee_bps = 0
        holder_reward = False
        depth = 0
        if off + 32 <= len(d):
            raw = d[off:off+32]; off += 32
            quote_mint = SOL_QUOTE if not any(raw) else b58(raw)
            if off + 8 <= len(d):
                vquote = _u64(d, off) / (1e9 if is_sol_quote(quote_mint) else 1e6); off += 8
            if off + 8 <= len(d):
                creator_fee_bps = _u64(d, off); off += 8
            if off < len(d):
                holder_reward = bool(d[off]); off += 1
            if off < len(d):
                depth = int(d[off])
        return {
            "name": name, "symbol": symbol, "uri": uri, "mint": mint, "curve": curve,
            "bonding_curve": curve, "user": user, "creator": creator, "ts_chain": ts_chain,
            "vtok": vtok, "vsol": vsol, "rtok": rtok, "supply": supply or TOTAL_SUPPLY,
            "mayhem": mayhem, "is_mayhem_mode": mayhem, "cashback": cashback,
            "quote_mint": quote_mint, "is_sol_quote": is_sol_quote(quote_mint),
            "vquote": vquote, "creator_fee_bps": creator_fee_bps,
            "holder_reward": holder_reward, "depth": depth,
        }
    except Exception:
        return None

def decode_complete(d: bytes) -> dict | None:
    if len(d) < 112 or d[:8] != DISC_COMPLETE:
        return None
    try:
        user = b58(d[8:40]); mint = b58(d[40:72]); curve = b58(d[72:104])
        ts_chain = _i64(d, 104)
        quote_mint = SOL_QUOTE
        if len(d) >= 144:
            raw = d[112:144]
            quote_mint = SOL_QUOTE if not any(raw) else b58(raw)
        return {"user": user, "mint": mint, "curve": curve, "bonding_curve": curve,
                "ts_chain": ts_chain, "quote_mint": quote_mint,
                "is_sol_quote": is_sol_quote(quote_mint)}
    except Exception:
        return None

def amm_price(pool_quote_raw: float, pool_base_raw: float, base_decimals: int = 6, quote_decimals: int = 9) -> float:
    if not pool_base_raw:
        return 0.0
    return (float(pool_quote_raw) / (10 ** quote_decimals)) / (float(pool_base_raw) / (10 ** base_decimals))

def decode_amm_pool(d: bytes) -> dict | None:
    if len(d) < 205 or d[:8] != DISC_AMM_POOL:
        return None
    try:
        return {
            "timestamp": _i64(d, 8), "ts_chain": _i64(d, 8), "index": struct.unpack_from("<H", d, 16)[0],
            "creator": b58(d[18:50]), "base_mint": b58(d[50:82]), "quote_mint": b58(d[82:114]),
            "base_decimals": int(d[114]), "quote_decimals": int(d[115]),
            "base_amount_in": _u64(d, 116), "quote_amount_in": _u64(d, 124),
            "pool_base_amount": _u64(d, 132), "pool_quote_amount": _u64(d, 140),
            "lp_token_amount_out": _u64(d, 164) if len(d) >= 172 else 0,
            "pool": b58(d[173:205]),
            "coin_creator": b58(d[301:333]) if len(d) >= 333 else "",
        }
    except Exception:
        return None

def decode_amm_trade(d: bytes) -> dict | None:
    if len(d) < 184:
        return None
    if d[:8] == DISC_AMM_BUY:
        is_buy = True
    elif d[:8] == DISC_AMM_SELL:
        is_buy = False
    else:
        return None
    try:
        return {
            "timestamp": _i64(d, 8), "ts_chain": _i64(d, 8), "is_buy": is_buy,
            "base_amount": _u64(d, 16), "base_amount_out" if is_buy else "base_amount_in": _u64(d, 16),
            "pool_base": _u64(d, 48), "pool_quote": _u64(d, 56),
            "quote_amount": _u64(d, 64), "lp_fee": _u64(d, 80), "protocol_fee": _u64(d, 96),
            "pool": b58(d[120:152]), "user": b58(d[152:184]),
            "coin_creator": b58(d[312:344]) if len(d) >= 344 else "",
        }
    except Exception:
        return None
