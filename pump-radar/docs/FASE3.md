# Fase 3 — Ottimizzazione controfattuale (ingressi × uscite)

Strumento: `python -m pumpradar optimize`

## Perché

Fase 0 sui dati reali (244 segnali curva): EV eseguibile negativo in **ogni**
sottogruppo, 130/244 uscite in stop con media −62%, uscite "horizon" a +5,5% e
trailing a +45,9%. Prima di inventare nuove strategie di selezione, va stabilito
se il problema è *quando entriamo*, *come usciamo*, o entrambi.

## Cosa fa

Per ogni segnale storico con percorso registrato, simula la combinazione di:

- **Ingresso**: immediato · ritardato +30/+60/+120s · pullback −15%/−30% dal prezzo
  del segnale (entro 5 minuti, altrimenti il segnale è scartato);
- **Uscita**: 4 livelli di stop × 3 scalette × 3 trailing = 36 piani.

216 varianti per corsia (curva e post-graduation), valutate con **split temporale
60/40**: una variante è "candidata" solo se l'EV è positivo su entrambe le metà
(n_test ≥ 10, n_train ≥ 15). Include la **gara stop-vs-target** dopo l'ingresso
immediato: la statistica che distingue "stop troppo stretto" da "ingressi sbagliati".

## Lettura

| Esito | Significato |
|---|---|
| Gara dominata da `stop_prima` e varianti con stop largo positive | Il piano respirava troppo poco: allargare stop/trailing |
| Pullback/ritardi battono l'immediato su train e test | L'ingresso sul segnale è inseguimento: spostare l'ingresso |
| Nessuna candidata | Selezione da rifare (Fase 2/attori): nessuna taratura salva questi ingressi |
| Candidate solo sul PG | Concentrare il capitale paper lì, curva solo sensore |

## Antidoto all'auto-inganno

La griglia esplora 216 ipotesi sugli stessi dati: la migliore può essere fortunata.
Per questo: split temporale, soglie minime, obbligo di doppio segno positivo e —
regola non negoziabile — **conferma in ombra su dati nuovi** prima che qualsiasi
variante tocchi posizioni (anche paper "ufficiali") o soglie di produzione.
