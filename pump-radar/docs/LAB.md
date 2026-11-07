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
