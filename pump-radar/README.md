# PUMPRADAR — sistema di segnalazione real-time per pump.fun

Sistema locale e gratuito che osserva in tempo reale lanci, trade e graduation su pump.fun, li valuta con **8 agenti specializzati** e gestisce due orizzonti diversi:

1. **Curva (0–15 min)** — selezione e timing prima della graduation;
2. **Post-graduation (PumpSwap)** — dove avvengono davvero molti movimenti da 10x/100x.

Non promette di “predire il 100x”. I numeri pubblici del dominio indicano che solo una piccola minoranza dei token gradua e una frazione ancora minore raggiunge capitalizzazioni elevate. PumpRadar è progettato per **filtrare il rumore, evitare trappole strutturali, entrare solo quando il rapporto payoff/rischio è favorevole e misurare il proprio risultato netto**.

> ⚠️ Strumento di ricerca, non consulenza finanziaria. Parte in paper trading. Con memecoin si può perdere il 100% del capitale.

## Avvio in 60 secondi

```bash
cd pump-radar
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pumpradar doctor      # verifica feed, AMM e prezzo SOL
python -m pumpradar sim         # prova offline su mercato sintetico
python -m pumpradar sim --dashboard  # stessa prova con dashboard web
python -m pumpradar run         # live + dashboard http://127.0.0.1:8787
```

Su Linux/macOS puoi usare `./run.sh`; su Windows `run.bat`.

## Comandi

| Comando | Uso |
|---|---|
| `python -m pumpradar doctor` | diagnostica gratuita dei feed |
| `python -m pumpradar run` | segnali live + dashboard |
| `python -m pumpradar run --no-dashboard` | solo console/Telegram |
| `python -m pumpradar sim --tokens 600 --speed 200` | validazione offline end-to-end |
| `python -m pumpradar capture --minutes 60` | raccolta dataset |
| `python -m pumpradar label` | calcola esiti realizzati |
| `python -m pumpradar train` | addestra modello calibrato sui tuoi dati |
| `python -m pumpradar report` | segnali, P&L paper, wallet con timing migliore |
| `python -m pumpradar backtest` | hit-rate dei segnali già etichettati |
| `python -m pumpradar prune` | manutenzione database |

## Come funziona

```text
logsSubscribe RPC gratuito
  ├─ TradeEvent/CreateEvent/CompleteEvent pump.fun
  │    ├─ corsia SOL      → curva classica, tradabile
  │    ├─ corsia ALT      → osservata, mai tradata automaticamente
  │    ├─ corsia SHALLOW  → osservata, mai tradata automaticamente
  │    └─ corsia CROSS    → quote diverso da SOL, prezzo derivato se possibile
  └─ Buy/Sell/CreatePool PumpSwap
       └─ motore runner post-graduation

Agenti curva → decisore → segnali → agente uscita → paper P&L
Agenti pool  → runner   → segnali → book runner  → paper P&L
                         ↓
                 etichette → training → modello
```

Gli agenti non si parlano tra loro: leggono/scrivono una lavagna condivisa (`TokenState`/`GradState`). Questo rende il comportamento riproducibile e testabile.

## Perché il feed è diverso

Il comodo `subscribeTokenTrade` di terze parti richiede una API key finanziata. PumpRadar invece:

- si iscrive con `logsSubscribe` al programma pump.fun;
- decodifica eventi Anchor/Borsh con layout verificato;
- riceve **tutti** i trade, incluso il wallet di ogni operazione;
- calcola riserve, market cap e progresso curva senza API a pagamento;
- classifica le famiglie di curva e scarta eventi incoerenti.

Per continuità 24/7 puoi opzionalmente usare un RPC con free tier (senza carta) tramite `PR_RPC_WS_URLS`.

## Strategia operativa

### Curva
- finestra decisionale 20–180 secondi;
- gate contro graduation ingegnerizzate, bundle, cloni, distribuzione e vendite del dev;
- piano: uscita 25% a 1.8x, 25% a 3x, 25% a 6x, trailing 35%, stop 42%, time-stop 13 min.

### Post-graduation
- pool tracciato solo se sembra una graduation reale;
- feature su liquidità, turnover, compratori unici, momentum, wash trading e vendite del creator;
- piano: 20% a 2x, 20% a 5x, 20% a 15x, 15% a 50x, residuo con trailing 35%, stop 45%.

Il secondo motore è essenziale: la curva termina intorno a ~410 SOL di market cap; i movimenti eccezionali avvengono dopo, nel pool AMM.

## Validazione prima del denaro

Per almeno due settimane:

```bash
python -m pumpradar run
python -m pumpradar label
python -m pumpradar report
python -m pumpradar train
```

Il training usa split temporale, esclude graduation ingegnerizzate, calibra le probabilità e valuta l’expected value netto. Se EV non è positivo, il report lo mostra: non “aggiustare” aumentando la size.

## Struttura

```text
pumpradar/
  ingest/     decoder on-chain, feed curva, feed AMM, enrichment
  agents/     curva, wallet, creator, rischio, narrativa, contesto, scorer, uscita
  runner.py   motore post-graduation
  learning/   labeler e trainer
  api/        dashboard locale
  sim.py      mercato sintetico calibrato
  orchestrator.py
  store.py    SQLite WAL
 tests/       test deterministici su decoder, agenti, runner e training
 docs/        architettura, playbook operativo e report di audit (docs/AUDIT.md)
```

Nessun auto-trading con chiavi private è abilitato: prima l’edge va dimostrato in paper trading.
