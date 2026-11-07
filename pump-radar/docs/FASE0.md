# Fase 0 — Archeologia sui dati reali

Strumento: `python -m pumpradar analyze` (opzione `--json out.json` per i dettagli).

## Perché esiste

Il `backtest` classico misura i **picchi teorici** dopo il segnale. Sui dati reali
dell'utente ha prodotto il paradosso: STRONG 0/14, WATCH 49/218 hit e tutti i 10x.
Ma un picco non è un guadagno: un token può toccare 2x per un tick incomprabile e
crollare mentre vendi. Fase 0 risponde alla domanda corretta:

> *Applicando il nostro piano di uscita (scaletta/trailing/stop, costi inclusi)
> al percorso reale registrato dopo ogni segnale, quanto avremmo reso?*

## Cosa calcola

Per ogni segnale storico (curva e post-graduation):

- **percorso reale**: serie dei market cap dei trade successivi al segnale (fino a 24h);
- **EV eseguibile**: simulazione del piano sul percorso (fill ai prezzi dei trade,
  costi curva 17% / AMM 15,6%), con motivo di uscita (stop/trailing/time_stop/horizon);
- **stratificazioni**:
  - per tier (la classifica che conta: EV netto, quota di trade positivi);
  - **quintili di score**: se l'EV non cresce da Q1 a Q5, lo score non ordina il futuro;
  - **dissezione WATCH**: per gate fallito, progresso curva al segnale, fascia di
    score, market cap di ingresso — per trovare quale sottogruppo contiene i vincitori;
  - motivi di uscita aggregati (dove il piano perde: stop? trailing tardivi? horizon?).

## Come si legge (decisioni, non curiosità)

| Osservazione | Decisione |
|---|---|
| Un sottogruppo WATCH (es. progresso 0.72–0.90) ha EV eseguibile positivo con n≥30 | Candidato a strategia ombra dedicata nella Fase 2 |
| Quintili piatti o decrescenti | Lo score euristico va spento per quella corsia fino al training |
| EV da picco positivo ma EV eseguibile negativo | Il piano di uscita, non la selezione, è il problema: ottimizzare le uscite (Fase 3) |
| Tutti gli EV negativi ovunque | Nessun edge con gli strumenti attuali: il metodo lo dichiara e si ferma |

## Limiti dichiarati

- I percorsi esistono solo per i token **tracciati** (watch/posizioni e pool seguiti):
  survivorship noto del dataset storico. La Fase 1 (aggregati per tutti i lanci)
  lo elimina alla radice.
- I fill simulati sono ai prezzi dei trade registrati: nel mondo reale, latenza e
  slippage possono solo peggiorare il risultato. L'EV qui è un **limite superiore onesto**.
- Numerosità: sotto n≈30 per stratum, le differenze sono in gran parte rumore;
  i criteri di promozione richiedono n≥30 e conferma su un secondo periodo.

## Procedura consigliata sul PC dell'utente

```bat
python -m pumpradar label
python -m pumpradar analyze --json fase0.json
```

L'output (o il JSON) è l'input della Fase 2: le strategie ombra nascono dagli
strati con EV eseguibile positivo, non da intuizioni.
