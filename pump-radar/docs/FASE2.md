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
