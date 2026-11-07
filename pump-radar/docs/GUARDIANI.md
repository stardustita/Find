# Fase 5 — Guardiani: smettere di segnalare ciò che i dati hanno falsificato

## Il problema, detto dai dati

I tier storici continuavano a emettere: curva 801 segnali con EV eseguibile
negativo in **ogni** sottogruppo, RUN post-graduation a pareggio (positivi
34%). Per l'utente questo significa notifiche su token scam o già in caduta.
La risposta non è un altro agente che *propone*: è un livello che **vieta**.

## I tre guardiani (aggiornati ogni 15 min dall'orchestratore)

| Guardiano | Mansione | Regole |
|---|---|---|
| 🛂 **Censore** | Ultimo controllo prima dell'emissione operativa (ENTRY/STRONG curva, SETUP/RUN PG) | <4 compratori unici negli ultimi 60s · già −30% dal picco · creator in blacklist · regime `toxic` (solo curva) · flag engineered/distribution |
| 🕵️ **Sentinella** | Pattern strutturali da scam | Creator con ≥10 lanci e ≥90% morti in <5 min → blacklist persistente (dal censimento completo) · acquisti del primo minuto dominati >60% da un wallet con <8 compratori |
| 📉 **Revisore** | Retrocessione automatica dei tier | EV eseguibile degli ultimi 100 segnali risolti per tier: se EV<0 con n≥50, il tier è retrocesso a **osservazione** — registrato e misurato, mai notificato né operato. Reversibile solo con finestra tornata positiva |
| 🔮 **Oracolo-Veto** | Secondo parere sui pool PG | Gemelli storici kNN del lancio: picco mediano <1,05x e p(2x) <8% → veto sull'operatività PG |

Un segnale censurato **non sparisce**: viene registrato come WATCH con i
motivi in `gates.censore`. Il sistema continua a misurare tutto, ma smette di
presentare come opportunità ciò che non ha dimostrato di esserlo. Nei log:
`🛡️ CENSORE … → osservazione: motivi`.

Stato atteso sul DB reale al primo avvio: il Revisore retrocederà con ogni
probabilità `curve:ENTRY` e `curve:STRONG` (EV storico −30%/−39%): da quel
momento la curva è osservazione pura, come i dati impongono da tempo.

## Comandi

```bash
python -m pumpradar guardian   # blacklist, regime, stato dei tier
python -m pumpradar autopsy    # include la sezione del Revisore
```

## Limiti dichiarati

- La Sentinella vede la concentrazione solo sui trade registrati (token
  tracciati): è un veto aggiuntivo, non una garanzia anti-scam.
- I Guardiani non creano edge: impediscono di operare senza edge. La prima
  emissione operativa futura sarà di una strategia promossa dai criteri
  pre-registrati (Fase 2), se mai esisterà.
