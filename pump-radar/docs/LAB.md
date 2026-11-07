# Fase 4 — Il Laboratorio: cinque agenti nuovi sopra il censimento

Con `launch_bars` il sistema registra **tutti** i lanci. La Fase 4 ci costruisce
sopra un laboratorio che propone, giudica e archivia ipotesi da solo — sotto la
stessa disciplina delle Fasi 0–3: niente diventa operativo senza verdetto in
ombra su dati nuovi, ogni numero affiancato alla mediana e al benchmark SOL.

| Comando | Agente | Cosa fa |
|---|---|---|
| `python -m pumpradar census` | 📊 Censimento | Tassi base per coorte (corsia, ora UTC, esperienza creator, forma/compratori/dimensione dei primi 60s, creator seriali ≥30 lanci): graduation, sopravvivenza 15m, p(2x), p(5x), picco mediano. Segnala le **anomalie** (z≥3 vs resto dell'universo). |
| `python -m pumpradar regime` | 🌦️ Meteorologo | Regime orario dal tasso di graduation (risk_on ≥1,4× baseline storica, toxic ≤0,6×). In `analyze` i verdetti ombra sono letti anche **per regime** al momento del segnale. |
| `python -m pumpradar factory` | 🏭 Fabbrica | Ogni anomalia diventa una regola pre-registrata e viene giudicata con EV eseguibile sui percorsi a barre di tutta la coorte (ingresso stilizzato +15s, ladder curva, costi) contro la baseline dell'universo. Verdetto nel registro immutabile `hypotheses`: **CANDIDATE** (EV>0, positivi ≥35%, EV ≥ baseline+5pp, n≥100) o **DEAD**. Mai operativa: CANDIDATE = merita un detector ombra. |
| `python -m pumpradar actors` | 🕸️ Cartografo | Reputazione persistente: `creator_stats` (lanci, graduation, picco mediano, morti <5m — serial-rugger vs builder) e `wallet_flags` (wallet che comprano entro 120s in ≥3 lanci dello stesso creator: firma delle crew organizzate). La vista creator usa il censimento intero; quella wallet i trade dei token tracciati (bias dichiarato). |
| `python -m pumpradar knn <mint>` | 🔮 Oracolo | Impronta dei primi 6 minuti (12×30s: prezzo, flusso acquisti, compratori — forme normalizzate), k=25 gemelli storici iniziati ≥1h prima (niente leakage), distribuzione dei loro esiti. Strumento di lettura e sorgente di ipotesi, non un segnale. |
| `python -m pumpradar autopsy [--send]` | 🩺 Reporter | Report markdown auto-scritto (salvato in `reports/`, Telegram con `--send`): meteo, benchmark SOL 30g, stato dei criteri di promozione per ogni strategia ombra, anomalie, registro Fabbrica. |

Inoltre: ogni segnale ora registra `creator_prior_launches` (quanti lanci aveva
già fatto il creator) nelle feature — la materia prima per le coorti future.

## Decisioni di onestà incorporate

- **Ingresso fabbrica a +15s, non +60s**: a +60s i lanci morti in un minuto
  sparirebbero dalla valutazione e la fabbrica erediterebbe survivorship al suo
  interno (trovato dai test, corretto).
- **z≥3 come soglia anomalie**: con ~100 celle di coorte testate, i falsi
  positivi attesi sono ~0,1 — la correzione per confronti multipli è nel disegno.
- **Registro immutabile**: una regola giudicata non viene ri-giudicata sugli
  stessi dati (INSERT OR IGNORE su `rule_key`). Per ri-testarla servono dati nuovi.
- **Benchmark obbligatorio**: `analyze` e `autopsy` stampano la variazione di
  SOL negli ultimi 30 giorni. Sotto quel numero, una strategia è morta anche se
  il suo EV è positivo.

## Stato atteso delle prime settimane

Il censimento si popola a ~migliaia di lanci/giorno di `run` acceso. Le prime
anomalie credibili (n≥150 per coorte) arrivano in giorni; i primi verdetti
Fabbrica subito dopo. Se nessuna regola supera le soglie in modo stabile,
il registro lo dirà — ed è una risposta, non un fallimento del processo.

## Primo giro reale (2026-11-07, DB utente: 6.351 lanci censiti)

Tassi base dell'universo: graduation **1,6%**, sopravvivenza 15m **10%**,
vita mediana **80s**, picco mediano **1,01x**. Baseline Fabbrica (ingresso
+15s su lanci a caso): **EV −24,9%**, mediana −31,8%, positivi 16,1% (n=4.262).
Questo e' lo zero del mercato.

Esiti della Fabbrica:
- 🟢 **CANDIDATE `forma_primi_60s:esplosivo`** (+50% nei primi 60s): p(2x) 70,7%
  vs 13,7% (z=44,9); sui percorsi EV **+34,9%**, mediana **+2,1%**, positivi
  50,8% (n=490). Avvertenza registrata: la valutazione entra a +15s conoscendo
  la forma a +60s (**look-ahead**) — il numero e' un limite ottimistico.
  Risposta: detector ombra `esplosivo60` (scatta a +60s, ingresso al prezzo di
  quel momento) + controllo anti-leakage in Fabbrica (colonna +60s).
- ⚫ **DEAD tutte le altre anomalie**, comprese quelle con z altissimi:
  compratori_60s 10+ (z=19,8 → EV −27,6%), miglior creator seriale (p(2x) 34%
  → EV −33,8%), buy 20+ SOL nel primo minuto (graduation 5,7% → EV −25,8%).
  Lezione permanente: **tasso di esito anomalo ≠ EV eseguibile**.

Altre letture dal censimento: 1–3 compratori nei primi 60s = p(2x) 1% (mai
toccare); creator al primo lancio graduano piu' dei seriali (2,4% vs 1,2%)
ma spiccano meno; identificata per indirizzo una farm da 154 lanci con 0%
di esiti e vita mediana 10s.

Prossimo checkpoint: `esplosivo60` in ombra verso n=30 segnali risolti,
letto in `analyze` (sezione OMBRA, anche per regime).

## Anti-leakage su `esplosivo` — esito (2026-11-07, giro reale n=6.401)

Il controllo ha dato il verdetto piu' netto possibile:

| Valutazione | EV | Mediana | Positivi | n |
|---|---|---|---|---|
| Ingresso +15s (con look-ahead) | **+34,4%** | +1,9% | 50,8% | 494 |
| Ingresso +60s (primo istante onesto) | **−28,1%** | −53,3% | 23,4% | 286 |

Il fenomeno e' reale (p(2x) 70,7% vs 13,7%: l'esplosione del primo minuto
predice davvero il picco), ma **non e' monetizzabile a +60s**: il picco avviene
dentro il primo minuto e a +60s il prezzo incorpora gia' la mossa — chi entra
allora finanzia l'uscita di chi era dentro. Lezione gemella di Fase 0: picco
prevedibile ≠ percorso tradabile.

Da questo giro la Fabbrica include la **griglia onesta** per ogni CANDIDATE:
ingressi +60/+120/+300s × 5 piani di uscita (standard, take-profit-2x, runner,
stop-stretto, trailing-only), e il verdetto CANDIDATE richiede che la migliore
cella onesta abbia EV>0 con positivi ≥35%. Il detector ombra `esplosivo60`
resta attivo dal vivo (giudice finale, riempimenti su trade reali): se anche
li' fallira' il checkpoint n=30, la regola verra' dichiarata morta del tutto.
