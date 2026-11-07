# Verifica — autocritica e banco di prova per SLANCIO

## Autocritica (doverosa)

SLANCIO è stato presentato come "la soluzione" prima di essere misurato:
era un'ipotesi con kill-switch, non una soluzione verificata. Tre difetti
strutturali andavano detti subito:

1. **Selezione avversa identica a esplosivo60, solo anticipata.** Il p(2x)
   70,7% del pattern è calcolato dal prezzo di lancio; chi entra a +25% già
   avvenuto compra *dopo* la prima riprezzatura. La statistica rilevante —
   esiti condizionati all'ingresso reale — non era mai stata misurata.
2. **Latenza.** La letteratura di settore è brutale: nel primo minuto
   competono bot con riempimenti <1s; oltre ~3s "il prezzo si è già mosso
   2–5x". La nostra pipeline (logsSubscribe → tick) è dell'ordine dei
   secondi: strutturalmente non siamo snipers, e fingere il contrario nei
   riempimenti paper sarebbe disonesto.
3. **Compratori sibilla.** I conteggi di wallet sono manipolabili (bundle
   su più indirizzi): i veti di concentrazione aiutano, non bastano.

Contesto esterno coerente coi nostri dati: graduation storica ~1,4%
(0,89% nel 2025; il nostro censimento misura 1,6% sullo stesso periodo),
~84% dei token graduati sotto 1/3 del prezzo entro 20 min dalla migrazione,
fee piattaforma 1% a trade. Il campo è progettato perché il retail in
ritardo finanzi le uscite di chi è entrato prima.

## Il banco: `python -m pumpradar verify`

Valuta SLANCIO (costanti live, mai tarate sui dati) e varianti/controlli
sull'intero censimento `launch_bars`, con disciplina anti-ottimismo:

- features solo da barre ≤ t; **ingresso alla barra successiva**;
- variante stress: +1 barra di ritardo e prezzo d'ingresso +10%;
- split temporale 60/40 (conferma fuori campione);
- controlli che *devono* fallire (esplosivo60, ingresso base a +30s):
  se passassero, il banco stesso sarebbe rotto;
- limite superiore dichiarato: mancano i flag di rischio live.

Verdetto PROMETTENTE solo con: test EV>0, positivi ≥35%, n≥30, e EV>0
anche sotto stress. In simulazione (dati sintetici, valore indicativo)
SLANCIO risulta già NON VERIFICATA sotto stress: la sensibilità alla
latenza è la sua debolezza principale, prima ancora della selezione.

## Regola decisionale (pre-registrata)

1. L'utente esegue `verify` sul DB reale e incolla l'output.
2. Se `slancio (live)` è PROMETTENTE → resta operativo paper e si osserva
   la conferma dal vivo (Revisore, checkpoint n=30/100).
3. Se NON VERIFICATA → SLANCIO viene retrocesso a **strategia ombra**
   (stesso detector, nessuna posizione paper, nessuna notifica operativa)
   con una modifica motivata dal verdetto — non da una ritaratura: le
   soglie restano quelle, cambia solo lo status. Il giudice resta il
   percorso: dati nuovi, in ombra, senza look-ahead possibile.
4. Nessuna variante "strict" verrà promossa perché vince in verifica sullo
   stesso DB: servirebbe comunque conferma in ombra su dati successivi.

"Funzionante" per questo prodotto significa: ogni cosa che segnala ha
superato — o sta superando in diretta, con kill-switch automatico — la
stessa verifica che ha ucciso tutte le ipotesi precedenti.
