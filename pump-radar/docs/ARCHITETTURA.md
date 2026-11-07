# Architettura e analisi

## 1. Tesi

Un token pump.fun nasce intorno a 28 SOL di market cap e la bonding curve si chiude intorno a 410 SOL. Quindi:

- il “100x da zero” non è un evento della curva;
- è un evento post-graduation, nella coda di una distribuzione molto asimmetrica;
- classificare direttamente “farà 100x” con pochi positivi produce quasi certamente overfitting.

PumpRadar adotta quindi una strategia in tre parti:

1. **Selezione**: eliminare il 97–99% dei lanci e le trappole strutturali.
2. **Timing**: entrare quando accelerazione, compratori unici e pressione buy sono coerenti.
3. **Uscita**: incassare a scaletta e proteggere il residuo; gran parte dei movimenti viene restituita rapidamente.

## 2. Numeri usati per calibrare il sistema

Da analisi pubbliche su centinaia di migliaia di lanci:

- graduation: circa 0,84–2% dei lanci;
- molte graduation rapide sono ingegnerizzate da pochi wallet;
- graduation organica mediana: circa 10 minuti;
- volume mediano per graduare: circa 281 SOL;
- circa 0,3% dei token raggiunge 1M$ e circa 0,05% raggiunge 10M$;
- fee di curva circa 1% per lato, più slippage e priority fee.

Queste sono calibrazioni, non garanzie: il mercato cambia e il sistema deve rimisurarsi con `label`, `report` e `train`.

## 3. Feed gratuito

### Curva pump.fun

`logsSubscribe` con filtro sul programma `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`. I log contengono eventi Borsh/Anchor:

- `CreateEvent`: nome, simbolo, URI, mint, creator;
- `TradeEvent`: mint, importo, token, buy/sell, wallet, riserve virtuali/reali, fee e campi quote;
- `CompleteEvent`: graduation.

Il decoder verifica discriminatori, lunghezze e invarianti. Gli eventi incoerenti vengono contati e scartati, non interpretati “a intuito”.

### Tre famiglie di curve

Misurando il flusso reale emergono famiglie diverse:

| Corsia | Criterio | Uso |
|---|---|---|
| `sol` | quote SOL e `vsol-rsol≈30` | tradabile |
| `alt` | mcap coerente ma invariante classica assente | solo osservazione |
| `shallow` | riserve SOL quasi nulle | solo osservazione |
| `cross` | quote diverso da SOL (es. $PUMP) | osservazione; prezzo SOL se quote prezzabile |

Il market cap `vsol/vtok × supply` è stato confrontato con oracoli pubblici. Il progresso graduation usa invece i token reali rimasti:

```text
vtok_implicita = rtok + 279.9M
vsol_implicita = (30 × 1.073B) / vtok_implicita
progresso = (vsol_implicita - 30) / 85
```

Non si usa `sold_tokens/793.1M`, perché la curva non è lineare in token.

### PumpSwap

Dopo `CompleteEvent`, il pool AMM viene riconosciuto dalla firma tipica di graduation (circa 206,9M token e 85 SOL iniziali). Gli eventi `BuyEvent`/`SellEvent` danno riserve del pool, importi e wallet. Da qui prezzo, liquidità e market cap sono calcolati localmente.

## 4. Agenti

| Agente | Domanda a cui risponde |
|---|---|
| Curva | Il capitale entra con accelerazione reale o manipolata? |
| Wallet-graph | Compratori indipendenti o bundle/sybil? Esiste overlap con coorti storicamente vincenti? |
| Creator | Il deployer ha track record? Sta vendendo? Quanto detiene? |
| Rischio | Graduation ingegnerizzata, clone, junk, distribuzione? |
| Narrativa | Nome/ticker/social/descrizione hanno qualità minima? |
| Contesto | Il mercato è saturo di lanci? SOL aiuta o penalizza? |
| Scorer | Quanto conviene rischiare a questo prezzo, ora? |
| Uscita | Quando vendere in parte, chiudere o proteggere il picco? |
| Runner | Il pool post-graduation ha liquidità, turnover e distribuzione da movimento esteso? |

## 5. Decisore e modello

All’avvio usa un **prior trasparente**: pesi leggibili e monotoni in `agents/scorer.py`. Non è una probabilità calibrata.

Dopo raccolta dati, `trainer.py`:

- crea esempi dagli snapshot;
- label: entro 15 minuti il prezzo tocca almeno 1.8x;
- esclude graduation ingegnerizzate;
- split temporale 70/30;
- gradient boosting con calibrazione isotonica;
- valuta AUC, precision nella coda ed EV netto;
- rifiuta training su dati sintetici senza `--force` esplicito.

## 6. Persistenza a tre livelli

Il firehose globale produce milioni di eventi/giorno. Salvare tutto sarebbe inutile e costoso:

- dettaglio completo per token in watch e posizioni;
- aggregati compatti per token scartati;
- snapshot periodici per training;
- trade AMM completi solo per pool tracciati.

SQLite in WAL è sufficiente su un PC domestico.

## 7. Limiti dichiarati

- Nessun modello elimina l’incertezza: hit-rate basso può essere compatibile con EV positivo, e viceversa.
- RPC pubblici possono limitare o interrompere la connessione; il sistema fa failover ma possono esserci buchi.
- Lo slippage reale può superare il 15% nei picchi; il paper trading non cattura tutto il MEV.
- Nuove varianti del programma possono cambiare layout: i test sui decoder devono fallire prima che il sistema operi su dati errati.
- Nessun auto-trading: invio transazioni e custodia chiavi richiedono un livello separato di sicurezza e validazione.

## 8. Roadmap sensata

1. Due settimane di paper trading e raccolta.
2. Primo training solo con dati reali sufficienti.
3. Confronto prior vs modello out-of-sample.
4. Micro-capitale manuale solo se EV netto positivo.
5. Eventuale esecuzione automatica separata, con limiti hardware/software, kill-switch e chiavi dedicate mai esposte.
