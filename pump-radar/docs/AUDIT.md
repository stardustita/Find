# Audit completo — PumpRadar

Audit di codice, test e funzionamento eseguito sull'intero progetto (12 moduli core,
8 agenti, 2 motori di uscita, learning, API, CLI). Metodo: lettura integrale del
codice, lint mirato (ruff F/E9), test di regressione scritti per ogni bug, suite
completa e simulazione end-to-end.

## Bug trovati e corretti

| # | Severità | Bug | Correzione |
|---|---|---|---|
| 1 | **Alta** | Prezzo SOL Jupiter mai aggiornato: l'API restituisce `{"data": {mint: {...}}}` e il parser non scartava l'involucro → fallback silenzioso a 150$ e prezzi cross sempre assenti | `_unwrap_prices()` in `enrich.py`, usato da prezzo SOL e `prices_usd` |
| 2 | **Alta** | PnL doppio alla chiusura: dopo vendite parziali a scaletta, la `CLOSE` (stop/trailing) contabilizzava il 100% della size invece del residuo | `apply()` di exit e runner scala la CLOSE su `1 − venduto` |
| 3 | **Alta** | Backtest curva fuorviante: le finestre partivano dal primo trade del token, attribuendo al segnale anche picchi precedenti al segnale stesso | Backtest riscritto: finestre e multipli calcolati da timestamp e prezzo **del segnale**; aggiunto backtest post-graduation |
| 4 | Media | `new_buyers_30s` sempre 0: differenza tra insiemi di finestre sovrapposte (30s ⊂ 60s) | Base corretta: compratori dei 30s precedenti come riferimento |
| 5 | Media | `buyer_growth` (curva) e `pg_buyer_growth` (runner) sempre ~0 per lo stesso errore di finestre sovrapposte | Rapporto tra compratori recenti e finestra precedente disgiunta |
| 6 | Media | Posizioni curva dopo la graduation: prezzo congelato a ~410 SOL, exit manager cieco | Il tick post-graduation sincronizza mcap/picco del token dal pool AMM |
| 7 | Media | Leakage nel training: snapshot dello stesso token presenti sia in train sia in test | Split temporale **per token** (insiemi di mint disgiunti) |
| 8 | Media | Dashboard esposta su `0.0.0.0` senza autenticazione | Default `127.0.0.1`; accesso LAN solo con `PR_API_HOST=0.0.0.0` esplicito |
| 9 | Bassa | Telegram/webhook ricevevano anche i segnali WATCH (spam) | Notifiche esterne solo per ENTRY/STRONG |
| 10 | Bassa | `max_signals_per_hour` configurato ma mai applicato | Rate-limit orario applicato nell'orchestratore |
| 11 | Bassa | Fallimento transitorio nel fetch metadata cachato per sempre | Cache solo per fetch riusciti |
| 12 | Bassa | `_quote_price_loop` scriveva chiavi di token SOL-lane nella mappa dei prezzi quote | Rimossa la scrittura errata |
| 13 | Bassa | `/api/positions`: per le aperte mostrava il multiplo di picco, non quello corrente; `limit` non validato | Multiplo corrente da stato live; limit clampato 1–200 |
| 14 | Bassa | `realized_today` usava la mezzanotte UTC | Mezzanotte locale |
| 15 | Bassa | `upsert_token` con sola chiave primaria generava SQL invalido | Guardia `INSERT OR IGNORE` |
| 16 | Cosmetica | 9 import inutilizzati | Rimossi (ruff F401) |

Ogni correzione 1–7 e 13/15 ha un test di regressione in `tests/test_audit_fixes.py`.

## Verifica funzionamento

- **Suite test: 26/26 superati** (decoder Borsh, classificazione corsie, handler feed,
  pipeline agenti, gate, runner post-graduation, uscite a scaletta, trainer,
  regressioni audit).
- **Simulazione end-to-end**: segnali curva, graduation, pool PumpSwap, segnali PG,
  posizioni paper, etichettatura e report funzionanti dopo le modifiche.
- **Backtest sui dati simulati già raccolti**: con la nuova misura dal segnale,
  ENTRY hit15=2/8, STRONG hit15=3/4, PG RUN avg24=1.52x (numeri sintetici, solo
  a conferma che la misura è onesta, non dell'edge).
- **Live**: non verificabile dalla sandbox di sviluppo (rete limitata agli host
  pacchetti/GitHub); il `doctor` segnala correttamente il FAIL con istruzioni.
  Sul PC dell'utente il feed è quello validato sul campo.

## Limiti noti (dichiarati, non nascosti)

1. **Survivorship nei dati di training**: gli snapshot esistono solo per i token
   promossi in watch dal prefiltro. Il modello impara a distinguere *tra i già
   filtrati*, non sull'universo grezzo. Accettabile per il ranking, da ricordare
   quando si interpreta l'AUC.
2. **Paper ≠ reale**: slippage/MEV reali nei picchi possono superare il 15%
   modellato; le label da trade osservati sovrastimano la riempibilità.
3. **RPC pubblici**: failover e reconnect presenti, ma per un 24/7 stabile serve
   un endpoint free-tier personale (`PR_RPC_WS_URLS`).
4. **Layout pump.fun**: se il programma cambia gli eventi, i decoder vanno
   ri-validati; i test sui discriminator sono la prima linea di difesa.
5. **Quote cross**: il mcap in SOL dipende dal prezzo Jupiter del token quote;
   se non è quotato, la corsia resta osservativa (mai tradata).
6. Il prior esperto **non è una probabilità calibrata**: diventa tale solo dopo
   `train` su dati reali sufficienti, con EV out-of-sample positivo.

## Migliorie future sensate (non ancora implementate)

- Persistenza aggregata anche per un campione di token scartati (riduce il
  survivorship bias del punto 1).
- Pesi del prior ri-stimati automaticamente a ogni training e salvati in config.
- Health-check periodico dei decoder contro un oracolo esterno (Dexscreener)
  con allarme se il mcap calcolato diverge.
- Export CSV dei segnali con esiti per analisi esterna.
