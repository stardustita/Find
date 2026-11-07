# Playbook operativo

## Fase 0 — Diagnostica

```bash
python -m pumpradar doctor
```

Devono risultare trade decodificati sia sulla curva sia su PumpSwap. Se i reconnect sono frequenti, configura un RPC gratuito con chiave in `.env`.

Apri la dashboard e verifica:

- lanci visti in crescita;
- scartati molto maggiori dei promossi;
- almeno alcuni pool di graduation nel tempo;
- nessun crash ripetuto degli agenti.

## Fase 1 — Paper trading obbligatorio (2 settimane)

Non usare denaro. Ogni giorno:

```bash
python -m pumpradar label
python -m pumpradar report
```

Osserva in ordine:

1. EV netto per trade;
2. hit-rate ENTRY/STRONG contro tasso base;
3. percentuale di uscite in stop;
4. drawdown paper;
5. motivi di uscita più frequenti;
6. differenza tra segnali presi subito e segnali “inseguiti”.

Dopo dati sufficienti:

```bash
python -m pumpradar train
```

Procedi solo se nella coda selezionata dal modello l’EV out-of-sample è positivo.

## Fase 2 — Eventuale micro-capitale

Solo capitale perdibile interamente.

- size iniziale: 1% del bankroll;
- mai aumentare dopo una perdita;
- massimo giornaliero di perdita fissato prima;
- esecuzione manuale all’inizio;
- confronta slippage reale e slippage ipotizzato;
- un segnale ignorato costa meno di un’operazione presa per noia.

## Come leggere un alert

- **Tier**: WATCH = osserva; ENTRY = candidato; STRONG = migliore qualità relativa, non size doppia.
- **Età/mcap**: oltre gran parte della curva il payoff residuo spesso non compensa il rischio.
- **Buyers unici**: pochi wallet grandi non equivalgono a domanda distribuita.
- **Burst / wallet mono-token**: possibili bundle; cautela massima.
- **Piano**: non è decorativo. La scaletta esiste perché i movimenti vengono spesso restituiti.

## Errori da evitare

| Errore | Antidoto |
|---|---|
| Inseguire dopo minuti | finestra massima e gate curva |
| Raddoppiare dopo perdite | size fissa |
| Tenere “tanto torna” | trailing e stop |
| Tradare ogni segnale | soglie, rate-limit, max posizioni |
| Credere al backtest in-sample | split temporale |
| Usare modello addestrato in simulazione | guardia anti-SIM nel trainer |
| Confondere hit-rate ed EV | report e selezione per EV |

## Checklist giornaliera

- [ ] `label` eseguito
- [ ] EV e drawdown controllati
- [ ] reconnect/feed stabili
- [ ] segnali di ieri erano eseguibili per età/liquidità?
- [ ] deriva ultimi 3 giorni vs settimana

## Checklist settimanale

- [ ] riaddestrare solo con nuovi dati reali sufficienti
- [ ] confrontare prior e modello out-of-sample
- [ ] esaminare i 10 segnali peggiori
- [ ] `prune` del database
- [ ] aggiornare i test se pump.fun cambia layout/eventi
