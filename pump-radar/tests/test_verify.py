"""VERIFICA: banco offline senza look-ahead per le regole intra-minuto."""
from pumpradar.learning.verify import RULES, _eval, verify

def _bars(created, mcaps, buy=1.0, sell=0.2, buyers=2, step=5):
    return [(created + step * i, buy, sell, buyers, m) for i, m in enumerate(mcaps)]

def _riser(created):
    return {"created_at": created, "bars": _bars(created, [30 * (1.06 ** i) for i in range(25)])}

def _dead(created):
    return {"created_at": created, "bars": _bars(created, [30.0] * 10, buy=0.1, sell=0.1, buyers=0)}

def test_slancio_catches_gradual_riser():
    out = _eval([_riser(1000)], RULES["slancio (live)"])
    assert out["n"] == 1 and out["ev_pct"] > 0

def test_entry_is_next_bar_not_signal_bar():
    # condizioni soddisfatte a t=1020 (mcap 40), poi crollo a 12 dalla barra dopo:
    # se l'ingresso fosse alla barra del segnale, il netto sarebbe ~0.13 (stop);
    # con ingresso alla barra successiva (12) il netto e' ~0.83 (solo costi).
    bars = _bars(1000, [30, 32, 34, 37, 40, 12, 12, 12, 12, 12])
    out = _eval([{"created_at": 1000, "bars": bars}], RULES["slancio (live)"])
    assert out["n"] == 1 and out["ev_pct"] > -50

def test_dead_token_never_fires():
    out = _eval([_dead(1000)], RULES["slancio (live)"])
    assert out["n"] == 0

def test_verify_structure_and_split():
    rows = [_riser(1000 + i * 100000) for i in range(20)] + [_dead(5000 + i * 100000) for i in range(20)]
    v = verify(None, summaries=rows)
    assert v["n_launches"] == 40
    assert "controllo_esplosivo60" in v["rules"] and "controllo_base30" in v["rules"]
    assert v["rules"]["slancio (live)"]["test(40% recenti)"]["n"] > 0
    assert v["rules"]["slancio (live)"]["verdict"] in ("PROMETTENTE", "NON VERIFICATA")
