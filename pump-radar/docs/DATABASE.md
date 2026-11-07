# Database storico — una settimana di tutto

Obiettivo dichiarato: **almeno 7 giorni di storia completa** prima di qualsiasi
nuova conclusione strategica. Da questa fase la cattura è profonda di default
(`deep_capture`, disattivabile con `PR_DEEP_CAPTURE=0`).

## Cosa viene registrato ora

| Dato | Dove | Per chi |
|---|---|---|
| **Ogni trade dei primi 30 min di OGNI lancio** (wallet, SOL, prezzo, slot) | `trades` (+ `wallets`, `wallet_tokens` aggiornati per tutti) | Prima: solo token new/watch. Ora il grafo wallet e i percorsi sono completi sulla finestra che conta |
| Barre 5s di ogni lancio (30 min) | `launch_bars` | Censimento senza survivorship (già attivo) |
| **Scheda completa per lancio** | `launch_facts` | Una riga per token: picco e tempo-al-picco, vita, volumi, **compratori/venditori unici esatti**, quota del compratore n.1, **buy del creator nei primi 60s**, quota sniper (buy primi 5s), multipli finali, lanci precedenti del creator (point-in-time, niente leakage). Calcolata a morte/chiusura + backfill all'avvio |
| **Barre 30s di ogni pool graduato** (prime 6h: prezzo, liquidità, compratori) | `pool_bars` | Il percorso post-graduation completo, non solo dei pool tracciati dal runner: la base per studiare davvero il PG |
| Prezzo SOL ogni minuto | `sol_prices` | Benchmark "tieni SOL" vero, non stimato dai segnali |
| Regime orario | `regime_log` | Il meteo diventa serie storica interrogabile |
| Segnali, ombre, posizioni, esiti | `signals`, `shadow_signals`, `positions`, `outcomes` | Invariati: il livello di giudizio |

## Dimensioni attese e manutenzione

Ai ritmi osservati (migliaia di lanci/giorno): ~0,5–2 milioni di trade/settimana,
ordine di 1–3 GB/settimana con indici. Verifica con `dayreport` (copertura) e
`autopsy` (sezione Copertura: lanci per giorno, schede completate).

```powershell
python -m pumpradar prune   # potatura: trade 45gg, barre 30gg di default
```

Non potare durante la settimana di raccolta se il disco regge: la storia
grezza è il capitale del progetto.

## Il patto della settimana

1. `run` acceso 24/7 (il report dichiara le ore scoperte: niente buchi nascosti).
2. Ogni giorno: `dayreport` — copertura piena? anomalie di raccolta?
3. A fine settimana: `autopsy` + `verify` + censimento sulle schede
   (`launch_facts` è la tabella da interrogare per ogni nuova ipotesi:
   coorti per dev-buy, quota sniper, concentrazione, esperienza creator —
   con esiti completi e senza survivorship).

Cosa NON può contenere, onestamente: visualizzatori/engagement del sito
(non on-chain), holder distribution in tempo reale di ogni token (RPC a
pagamento di fatto, per volume), la storia *precedente* all'avvio della
raccolta (non esiste backfill gratuito del firehose: la settimana parte
da quando il sistema è acceso).
