# Fase 1+2 — Dati senza survivorship e strategie ombra

## Fase 1 — `launch_bars`: la memoria di TUTTI i lanci

Prima: dettaglio solo per i token promossi in watch → ogni dataset ereditava il
filtro che doveva giudicare (survivorship bias). Ora l'orchestratore aggrega
**barre da 5 secondi per ogni lancio** (primi 30 minuti di vita): numero trade,
SOL comprati/venduti, compratori unici, ultimo market cap. Anche il token morto
in 8 secondi lascia la sua barra. Pulizia automatica a 30 giorni (`prune`).

Verifica in simulazione: 250 lanci → 1.600 barre, 250/250 mint presenti.
È il dataset su cui, tra qualche settimana, si potranno misurare i tassi base
veri per coorte (ora del giorno, corsia, creator, pattern dei primi 60 secondi)
senza il filtro di mezzo.

## Fase 2 — Strategie ombra

Due ipotesi nate dai dati (gara stop-vs-target 56% vs 18%; nessuna variante di
ingresso/uscita salva la selezione attuale). Vivono in `pumpradar/shadow.py`,
sono **solo registrate** in `shadow_signals` (mai posizioni, mai notifiche) e
vengono giudicate da `analyze` con la stessa metrica EV-eseguibile dei segnali veri.

### `second_leg` (curva)
Ha già fatto ≥2x dal minimo → crollo del 45–78% dal picco **senza morire** →
nuova ondata: ≥8 compratori unici in 60s, buy/sell 30s ≥1.4, prezzo in recupero
(+4% in 60s), niente engineered/distribution. Una volta per token.

### `pg_pullback` (post-graduation)
Pool a ≥1.8x dal prezzo iniziale → ritraccia 25–55% dal picco → liquidità ≥8 SOL
sopravvissuta, ≥10 compratori unici in 5 min, ritorno di prezzo positivo a 1 min,
creator non in vendita. Cooldown 30 min per pool.

## Promozione (pre-registrata, non negoziabile)

Una strategia ombra diventa candidata operativa solo con:
1. n ≥ 30 segnali risolti in ombra;
2. EV eseguibile medio > 0 con quota di positivi > 40%;
3. conferma su un secondo periodo disjoint (i 30 successivi non peggiorano sotto −5%);
4. confronto col benchmark (stesso periodo, tenere SOL / non fare nulla).

Sotto queste soglie resta ombra. Se dopo ~200 segnali risolti nessuna strategia
le supera, la conclusione registrata è: nessun edge trovato con questi strumenti
gratuiti — e il sistema continua come radar di osservazione, non come macchina
di segnali operativi.

## Lettura in `analyze`

Sezione "Strategie OMBRA": per strategia, n / hit / EV netto eseguibile /
quota positivi — direttamente confrontabile con le righe dei tier reali.

## Registro dei verdetti (aggiornato coi dati reali)

### 2026-11-07 — primo giro di dati (801 segnali curva, 80 PG, DB utente)

- **`second_leg`: RIGETTATA al primo checkpoint.** n=35 (soglia: 30),
  EV netto −36,7%, positivi 9%, hit1.8 solo 3% — peggio persino dei WATCH curva
  (−23,4%). La "seconda ondata di compratori" dopo un crollo del 45–78% e', nei
  dati, liquidita' di uscita per chi vende: l'ipotesi e' falsificata, non "da
  ritoccare". Restera' registrata in ombra (costo zero) ma non verra' mai
  promossa ne' ritarata: ritoccare le soglie di un'ipotesi morta sarebbe la
  taratura sequenziale che questo metodo sostituisce.
- **`pg_pullback`: IN RACCOLTA.** n=2 (entrambi picco 2x in 15 min, ma solo 1/2
  netto positivo: anche i "vincitori" esigono disciplina di uscita). Nessuna
  conclusione possibile; il tasso di fuoco e' lento (le graduation sono ~1% dei
  lanci), il checkpoint n=30 e' questione di settimane-mesi di `run` acceso.
- **Tier PG `RUN` (operativo paper): pareggio, non edge.** EV +1,4% su n=35 ma
  positivi solo 34% (< 40% richiesti): resta com'e', non e' una promozione.
- **Miraggio da coda registrato:** tier PG WATCH a EV medio +1187,9% con
  positivi 44% — media dominata da 1–2 moonshot su un bucket residuale non
  operativo. Da qui la **mediana del netto** in ogni riga di `analyze`
  (colonna `mediana=`): il trade tipico si legge li', la media resta come
  misura della coda.
- **Curva, chiusura definitiva a n=801:** ogni sottogruppo negativo (miglior
  fascia Q4 −17,7%; ingressi a progresso 0,30–0,72 tra −43% e −44%;
  `not_bundle` ancora il peggiore dei gate grandi: il filtro bundle e'
  confermato). Nessuna ulteriore analisi sulla selezione storica.

Prossima lente, quando i dati maturano: tassi base per coorte da `launch_bars`
(tutti i lanci, nessun filtro). Nessuna nuova strategia verra' inventata per
rimpiazzare `second_leg`: si promuove solo cio' che i dati propongono.
