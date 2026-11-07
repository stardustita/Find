# H24 — dove far girare PumpRadar (aggiornato dopo il fallimento Oracle)

Requisiti del prodotto: Python 3.11, solo connessioni **in uscita** (WebSocket
verso RPC Solana pubblici gratuiti), ~1–3 GB di disco a settimana, nessuna
porta pubblica in ascolto. Il profilo è ideale per i piani gratuiti — a patto
di scegliere quelli *ottenibili davvero*.

## Perché NON Oracle (nonostante sia il più generoso sulla carta)

Oracle Always Free (2 core ARM / 12 GB dopo il dimezzamento di giugno 2026)
è in pratica **inutilizzabile per molti nuovi utenti**: registrazioni
rifiutate alla verifica della carta, oppure istanze che non nascono mai per
"out of host capacity" nelle region richieste. È il piano migliore del mondo
per chi ce l'ha già; per chi parte oggi è un terno al lotto. Scartato.

## Piano A (gratis vero, attivabile oggi): Google Cloud e2-micro

Always Free permanente, creazione immediata senza lotteria di capacità:
**1 e2-micro, 1 GB RAM, 30 GB di disco standard** — ma solo nelle region
**us-west1 / us-central1 / us-east1** e solo col disco *Standard* (il default
"Balanced" si paga). Trappole note, tutte aggirabili:

- **RAM 1 GB** → lo script `install.sh` crea automaticamente 2 GB di swap
  sulle macchine piccole e abbassa il tetto dei pool tracciati.
- **IPv4 esterno ≈ $3,65/mese** (gratis solo 1 ora/mese): senza IP esterno la
  VM non esce su internet (il Cloud NAT costa di più). Onestà: il totale
  realistico è **~3–4 €/mese per l'IP**, il resto è 0 €. Budget alert a 1 $.
- **Egress incluso: 1 GB/mese** — PumpRadar invia quasi nulla (iscrizioni
  RPC e richieste piccole; il firehose è traffico in *ingresso*, gratuito).
  Niente dashboard pubblica, solo tunnel SSH.
- **Disco 30 GB** → dopo la prima settimana scarica il DB sul tuo PC
  (vedi sotto) e pota i trade grezzi più vecchi: le schede `launch_facts`
  sono piccole e restano per sempre.

### Creazione (console Google Cloud)

1. cloud.google.com → crea progetto → **Compute Engine → Crea istanza**:
   - Regione: **us-central1 (Iowa)** — Zona qualsiasi
   - Tipo macchina: **e2-micro** (serie E2)
   - Disco di avvio: Ubuntu 24.04 LTS, tipo **Standard persistent disk**, 30 GB
   - Lascia l'IP esterno effimero (è la voce da ~$3,65/mese, inevitabile)
2. Crea → attendi 1 minuto → pulsante **SSH** nella console (si apre nel browser).
3. Nella shell della VM:
   ```bash
   git clone https://github.com/stardustita/Find.git ~/Find 2>/dev/null || echo "repo privato? vedi nota deploy key sotto"
   cd ~/Find && bash pump-radar/deploy/install.sh
   ```
4. Verifica dopo qualche minuto:
   ```bash
   journalctl -u pumpradar -f
   cd ~/Find/pump-radar && .venv/bin/python -m pumpradar dayreport
   ```

**Se la e2-micro satura** (log in ritardo, riavvii per memoria): è il suo
limite fisico col firehose, non un bug. Si passa al Piano B senza perdere
niente: il DB si copia con un comando (sotto).

## Piano B (consigliato se 4–8 €/mese sono accettabili): Hetzner Cloud

Niente lotterie, creazione in 1 minuto, datacenter in Germania (vicini e
veloci). **CAX11** (ARM, 2 vCPU / 4 GB / 40 GB) o **CX23** (x86, stessa
taglia): a listino post-giugno 2026 circa **5–6 €/mese + IVA e IPv4**, tutto
compreso sotto gli ~8 €. 4 GB di RAM = PumpRadar gira largo, 20 TB di
traffico inclusi. Procedura: hetzner.com/cloud → crea server (Falkenstein,
Ubuntu 24.04, chiave SSH) → stesso `install.sh` di sopra.

## Note operative (entrambi i piani)

- **Repo privato?** Su GitHub: repo → Settings → Deploy keys → aggiungi la
  chiave pubblica della VM (`cat ~/.ssh/id_ed25519.pub` dopo `ssh-keygen`).
  Lo script lo ricorda da solo se il clone HTTPS fallisce.
- **Porta la storia già raccolta**: dal PC Windows, copia il DB esistente:
  ```powershell
  scp pump-radar\data\radar.db <utente>@<IP-VM>:~/Find/pump-radar/data/radar.db
  ```
  (a servizio fermo: `sudo systemctl stop pumpradar` prima, `start` dopo).
  Così la settimana non riparte da zero: i lanci già censiti restano.
- **Backup settimanale** (il DB è il capitale): `scp` inverso sul tuo PC,
  poi eventualmente `python -m pumpradar prune`.
- **Dashboard**: mai esporla. Tunnel: `ssh -L 8787:127.0.0.1:8787 <utente>@<IP>`
  → http://localhost:8787.
- **Controllo quotidiano** (30 secondi, via SSH): `dayreport` — copertura
  continua? disco ok (`df -h`)? Se la copertura ha buchi, il report lo dice.

## Scartati, con motivo

| Servizio | Perché no |
|---|---|
| Oracle Always Free | Mai ottenibile in pratica (verifiche/capacità) |
| Render / Railway / Fly.io gratuiti | Sleep o crediti una tantum: un processo H24 non ci vive |
| AWS / Azure "free" | Scadono in 6–12 mesi: la raccolta muore a metà |
| PythonAnywhere gratuito | Solo HTTP in whitelist e task schedulati: niente firehose WebSocket |

Fonti (nov. 2026): specifiche e trappole e2-micro
([yangworks](https://yangworks.dev/guides/google-cloud-free-tier-e2-micro),
[agentdeals](https://agentdeals.dev/vendor/google-compute-engine));
prezzi Hetzner post-aumento giugno 2026
([creacosas](https://www.creacosas.com/en/blogs/technology/best-cheap-vps-2026),
[shattered.io](https://shattered.io/cheapest-cloud-vps-2026-provider-comparison/)).
