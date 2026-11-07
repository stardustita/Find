from __future__ import annotations
import math

INIT_VSOL = 30.0                    # SOL virtuali iniziali della curva classica
GRAD_VSOL = 115.0                   # 30 virtuali + ~85 reali alla graduation
INIT_VTOK = 1_073_000_000.0         # token virtuali iniziali (unità intere)
INIT_RTOK = 793_100_000.0           # token reali iniziali nella curva
TOKEN_OFFSET = INIT_VTOK - INIT_RTOK
TOTAL_SUPPLY = 1_000_000_000.0
CURVE_K = INIT_VSOL * INIT_VTOK

_ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_CACHE: dict[bytes, str] = {}

def b58encode(data: bytes) -> str:
    cached = _B58_CACHE.get(data)
    if cached is not None:
        return cached
    zeros = len(data) - len(data.lstrip(b"\x00"))
    n = int.from_bytes(data, "big") if data else 0
    chars = []
    while n:
        n, r = divmod(n, 58)
        chars.append(_ALPH[r])
    out = "1" * zeros + "".join(reversed(chars))
    if len(_B58_CACHE) < 500_000:
        _B58_CACHE[data] = out
    return out

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))

def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default

def spot_price_sol(vsol: float, vtok: float) -> float:
    return safe_div(vsol, vtok)

def mcap_sol(vsol: float, vtok: float, supply: float = TOTAL_SUPPLY) -> float:
    return safe_div(vsol * supply, vtok)

def curve_progress(vsol: float) -> float:
    """Progresso 0..1 verso graduation per la curva classica (30->115 SOL virtuali)."""
    if not vsol:
        return 0.0
    return clamp((vsol - INIT_VSOL) / (GRAD_VSOL - INIT_VSOL))

def progress_from_rtok(rtok: float) -> float:
    """Progresso esatto ricavato dai token reali rimasti.

    Invariante verificata sui dati: vtok = rtok + 279.9M e k = vsol*vtok.
    Da rtok si ricava quindi la vsol implicita senza dipendere dalla valuta quote.
    NON è sold_tokens/793.1M: la curva non è lineare in token.
    """
    if rtok is None:
        return 0.0
    vtok_equiv = max(1.0, float(rtok) + TOKEN_OFFSET)
    implied_vsol = CURVE_K / vtok_equiv
    return clamp((implied_vsol - INIT_VSOL) / (GRAD_VSOL - INIT_VSOL))

def hhi(values) -> float:
    vals = [float(v) for v in values if v and float(v) > 0]
    total = sum(vals)
    if total <= 0:
        return 1.0
    return sum((v / total) ** 2 for v in vals)

def gini(values) -> float:
    vals = sorted(float(v) for v in values if v is not None and float(v) >= 0)
    n = len(vals)
    total = sum(vals)
    if n == 0 or total <= 0:
        return 1.0
    weighted = sum((i + 1) * v for i, v in enumerate(vals))
    return clamp((2 * weighted) / (n * total) - (n + 1) / n, 0.0, 1.0)

def cosine_similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / math.sqrt(len(a) * len(b))

def progress_check(sol_in: float, fee_bps: float = 100.0) -> float:
    """Progresso dopo un acquisto netto su curva nuova; utile nei test/documentazione."""
    net = max(0.0, sol_in) * (1 - fee_bps / 10_000)
    return clamp(net / (GRAD_VSOL - INIT_VSOL))
