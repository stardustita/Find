# Ricostruzione — audit completo e nuovo strato segnali (GEMME)

Richiesta: analizzare tutto, eliminare il superfluo, e ottenere alert in tempo
reale sui token *prima* che diventino gemme. Metodo invariato: i dati decidono.

## Audit: cosa dicono 8 fasi di prove

### Debolezze strutturali (verificate, non opinioni)
1. **Lo score curva non discrimina.** Quintili piatti/negativi su n=801: la
   selezione ENTRY/STRONG/WATCH è falsificata in ogni sottogruppo.
2. **Un modello non calibrato autorizzava posizioni.** In `_emit`, bastava
   l'esistenza di un file modello perché ENTRY aprisse. Corretto: ora solo
   STRONG e SLANCIO possono aprire (paper), il prior non autorizza nulla.
3. **I pattern completi arrivano tardi.** Esplosione 60s: fenomeno reale
   (p(2x) 70,7%) ma a +60s è già prezzata (griglia onesta 7/7 negativa).
   `second_leg` morta in ombra (n=35, −36,7%). Momentum inseguito = perdente.
4. **Riempimenti paper ottimistici** (niente latenza/slippage simulati):
   `analyze` resta il giudice perché simula il percorso dai trade reali, ma
   ogni EV va letto come limite superiore.
5. **`pg_pullback` è lenta per natura**: le graduation sono ~1,6% dei lanci;
   il checkpoint n=30 richiede settimane-mesi. Resta in ombra, è il suo posto.

### Superfluo identificato
- **Agente narrative**: disabilitato da sempre, mai validato → congelato
  (resta nel registro agenti ma non influenza nulla).
- **Tier ENTRY operativo**: falsificato (EV −29,4%) e in attesa di
  retrocessione automatica (finestra n=22/50) → non apre più posizioni.
- **Comandi legacy** (`capture`): superati da `run`+`launch_bars`, mantenuti
  solo per compatibilità dei test.
- **Score e prior probabilistici** (p_bond/p_2x): restano come *sensori* e
  materia di analisi, mai più come autorità di emissione.

### Cosa è stato tenuto (perché validato dai dati)
Feed on-chain gratuito con wallet di ogni trade · `launch_bars` (censimento
senza survivorship) · Censimento/Meteorologo/Fabbrica con griglia onesta ·
Guardiani (Censore/Sentinella/Revisore/Oracolo-Veto) · strategie ombra ·
misurazione EV eseguibile con mediana e benchmark SOL.

## Il nuovo motore: GEMME (`pumpradar/gem.py`)

L'unica geometria mai testata onestamente: **entrare durante la formazione**
dell'esplosione, con informazione disponibile in quell'istante (per
costruzione, zero look-ahead):

- età 18–90s, prezzo ≥ +25% dal minimo di nascita, non già ritirato >15%
  dal picco;
- ≥5 compratori distinti negli ultimi 15s, buy/sell 30s ≥1,3, momentum
  degli ultimi 15s ancora ≥ +3%;
- niente flag engineered/distribution.

Emissione: alert in tempo reale (console 🚀, Telegram, dashboard) + posizione
paper, tier **SLANCIO**. Ogni alert dichiara i tassi base del pattern madre.
Passa dal **Censore** (blacklist, regime, caduta) come ogni operatività.

### Come verrà giudicato (pre-registrato, automatico)
- `analyze`: riga SLANCIO con EV eseguibile, mediana, positivi — stessa
  metrica di tutti i tier storici.
- **Revisore**: ultimi 100 segnali risolti con EV<0 (n≥50) → retrocessione
  automatica a osservazione, senza intervento umano.
- Lettura di controllo a n=30 risolti nell'autopsy settimanale.

Se SLANCIO morirà come le ipotesi precedenti, morirà in settimane, a costo
zero, con le prove in mano — e il sistema avrà comunque smesso di segnalare
scam: nel frattempo le uniche emissioni operative possibili sono SLANCIO
censurato e ciò che il Revisore non ha (ancora) retrocesso.
