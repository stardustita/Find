# Taratura sui dati reali (novembre 2026)

Prima sessione live dell'utente, analizzata invece di "aggiustare a sensazione".

## I numeri che hanno guidato le modifiche

| Misura | Valore | Lettura |
|---|---|---|
| Token etichettati | 528 | campione sufficiente per diagnosticare |
| Graduati | 4 (0,76%) | coerente col tasso base pubblico (~0,84%) |
| Segnali curva ENTRY+STRONG | 26 | selettività apparente ok |
| Posizioni curva chiuse | 24 | — |
| **Win-rate curva** | **0,0%** | nessuna posizione ha toccato il 1° target (1.8x) |
| **P&L curva** | **−1,11 SOL, media −46%, migliore −4%** | ingressi sistematicamente sui massimi locali |
| Peggiore uscita | −93% | token morti tra un tick e l'altro, uscita tardiva |

Conclusione: il prior premiava le metriche che nei pump&dump raggiungono il massimo
pochi secondi prima del crollo (velocità di acquisto, pressione buy). Non è sfortuna:
è un bias strutturale di selezione, e si corregge restringendo gli ingressi.

## Modifiche applicate

### Ingresso curva
1. **Gate di ingresso separati dai gate di qualità** (`entry_gates`): chi li fallisce
   resta WATCH (osservazione in dashboard), mai posizione:
   - progresso curva solo tra 3% e 45% (prima: fino al 72%);
   - market cap di ingresso ≤ 150 SOL (`max_entry_mcap_sol`);
   - **anti-inseguimento**: niente ingresso se il prezzo è già salito >85% in 30s
     (`mcap_ret_30s`, nuova feature);
   - **flusso non esaurito**: niente ingresso se il flusso buy sta decelerando
     mentre la pressione di vendita sale (`flow_decel`, nuova feature).
2. **Conferma a 2 tick** (~4s live): gli spike da un solo tick diventano WATCH.
   Vale anche per l'apertura posizioni del runner post-graduation.
3. **Gate base più stretti**: compratori unici ≥8 (da 6), bundle più severo,
   pressione di vendita <1.8 (da 2.5).
4. **Soglie alzate**: ENTRY ≥0.50, STRONG ≥0.60 (config.yaml).
5. **Prior non calibrato = operatività ridotta**: senza modello addestrato, le
   posizioni paper curva si aprono solo su STRONG. Con modello addestrato, anche ENTRY.

### Uscite
6. **Stop curva 35%** (da 42%).
7. **Stop a pareggio**: dopo un picco ≥1.3x, uscita a 1.03x invece di ridare tutto.
8. **Token inattivo** (nessun trade da 45s e sotto +5%): chiusura immediata.
9. **Momentum esaurito**: dopo 4 minuti sotto +5%, chiusura (prima: 13 minuti).
10. Pareggio anche per il runner (picco ≥1.6x → uscita a 1.03x).

### Limiti di rischio (prima configurati ma mai applicati)
11. `max_daily_loss_sol` ora blocca davvero nuove aperture (curva e runner).
12. `report` mostra la **tabella dei motivi di uscita** con P&L per motivo:
    è lo strumento per la prossima taratura.

## Cosa aspettarsi

- **Molti meno segnali ENTRY curva**: è voluto. In simulazione la curva ora produce
  quasi solo WATCH e il motore operativo principale è il post-graduation (RUN),
  coerente con dove avvengono i movimenti veri.
- I WATCH restano visibili in dashboard (token cliccabili verso pump.fun) ma non
  aprono posizioni né notifiche Telegram.
- Dopo 1–2 settimane di nuovi dati: `label` + `report` + `backtest`, poi `train`.
  Con un modello calibrato, ENTRY torna operativo con soglie misurate, non euristiche.

## Se vuoi più segnali (sconsigliato finché l'EV è negativo)

In `config.yaml`: abbassa `min_alert_score` a 0.46–0.48, oppure alza
`max_entry_mcap_sol` / `entry_max_progress`. Fallo solo a fronte di un EV
misurato positivo nel `report`, mai per noia: ogni segnale in più con EV
negativo accelera solo le perdite (anche se paper, inquina le statistiche).
