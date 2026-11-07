# H24 gratuito — dove far girare PumpRadar

Requisiti del prodotto: Python 3.11, solo connessioni **in uscita** (WebSocket
verso RPC Solana pubblici gratuiti), ~1–3 GB di disco a settimana, nessun
servizio in ascolto su porte pubbliche. È il profilo ideale per i piani
gratuiti "always free" — a patto di scegliere quelli veri.

## Il confronto onesto (novembre 2026)

| Servizio | Gratis per sempre? | Specifiche | Il trucco |
|---|---|---|---|
| **Oracle Cloud Always Free** ARM | ✅ sì | 2 core ARM / 12 GB RAM, 200 GB disco, 10 TB traffico/mese | Carta richiesta (verifica, nessun addebito entro i limiti); istanze **inattive** riassorbite |
| Google Cloud e2-micro | ✅ sì | 1 GB RAM, 30 GB disco | Solo region USA; RAM al limite per PumpRadar (serve swap) |
| AWS / Azure gratuiti | ❌ 6–12 mesi | micro 1 GB | Scadono: non è un H24, è un conto alla rovescia |
| Render / Railway / Fly.io | ❌ | — | I piani gratuiti **dormono** o sono crediti una tantum: un processo H24 non ci vive |

Note dalle fonti (novembre 2026): Oracle ha **dimezzato** la quota ARM gratuita
il 15 giugno 2026 — da 4 core/24 GB a 2 core/12 GB, senza annunci pubblici:
molte guide citano ancora i vecchi numeri ([InfoQ](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/),
[mrplanb](https://www.mrplanb.com/datacenter/free-vps-tiers)). 2 core e 12 GB
restano comunque larghi per PumpRadar, e la quota disco (200 GB) copre mesi di
raccolta ([confronto 2026](https://klymentiev.com/blog/free-vps)). Oracle
riassorbe le istanze con CPU <10% per 7 giorni
([guida](https://khimananda.com/blog/oracle-cloud-free-tier-for-learning)):
PumpRadar ingerisce il firehose Solana in continuo, quindi "inattivo" non lo
sarà mai. AWS ha chiuso il free tier annuale per i nuovi account, Azure dura
12 mesi ([mrplanb](https://www.mrplanb.com/datacenter/free-vps-tiers)); i
servizi PaaS gratuiti spengono i processi inattivi o danno solo crediti
([guida](https://www.keydal.net/blog/free-server-guide)). Google e2-micro è
gratis per sempre ma solo in region USA e con 1 GB di RAM e 1 GB di traffico
in uscita/mese ([dettagli](https://www.whatsthehost.com/free-vps-hosting/)):
il traffico Solana è quasi tutto in **ingresso** (gratuito), ma la RAM è
stretta — piano B, non piano A.

## Raccomandazione: Oracle Cloud Always Free (Frankfurt)

1. **Registrazione** su oracle.com/cloud/free — scegli come *home region*
   **EU Frankfurt** (vicina, e storicamente con più capacità libera delle
   region USA). Serve una carta per la verifica d'identità: eventuali
   "addebiti" di verifica (~1 €) vengono rimborsati; entro i limiti Always
   Free non si paga nulla. Imposta comunque un **budget alert a 0,01 €**.
2. **Crea l'istanza**: Compute → Instances → Create → shape
   **VM.Standard.A1.Flex** con **2 OCPU / 12 GB** (badge "Always Free
   eligible"), Ubuntu 24.04 ARM, chiave SSH salvata con cura.
   *Out of host capacity*? Normale sui piani gratuiti: riprova in un'altra
   Availability Domain o dopo qualche ora.
3. **Installa PumpRadar** (SSH nella VM):
   ```bash
   curl -fsSL https://raw.githubusercontent.com/stardustita/Find/main/pump-radar/deploy/install.sh | bash
   ```
   (oppure clona il repo e lancia `bash pump-radar/deploy/install.sh`).
   Il servizio `pumpradar` parte da solo, si riavvia da solo, riparte al boot.
4. **Verifica** dopo qualche minuto:
   ```bash
   journalctl -u pumpradar -f                                  # il flusso vive
   cd ~/Find/pump-radar && .venv/bin/python -m pumpradar dayreport   # la copertura cresce
   ```

## Gestione quotidiana (2 minuti)

- Salute: `dayreport` (copertura, lanci, schede). Dashboard via tunnel SSH,
  mai esposta: `ssh -L 8787:127.0.0.1:8787 ubuntu@<IP>` → http://localhost:8787.
- Disco: 200 GB bastano per mesi; dopo la settimana di raccolta, `prune`
  mensile (tiene 45 giorni di trade).
- Backup del database (il vero capitale): ogni tanto scarica una copia:
  ```bash
  cd ~/Find/pump-radar && .venv/bin/python -c "import sqlite3; sqlite3.connect('data/radar.db').backup(sqlite3.connect('data/backup.db'))"
  # poi, dal tuo PC:  scp ubuntu@<IP>:~/Find/pump-radar/data/backup.db .
  ```
- Aggiornamenti: `git -C ~/Find pull && sudo systemctl restart pumpradar`.

## Piano B: Google Cloud e2-micro

Console GCP → Compute Engine → e2-micro in **us-central1** (Always Free),
Ubuntu, poi lo stesso `install.sh`. Aggiungi swap (la RAM è 1 GB):
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
```
Se la raccolta deve essere europea e abbondante, però, resta Oracle.

## Cosa NON fare

- Niente Render/Railway/Fly "gratuiti" per il processo principale: sleep e
  crediti una tantum = buchi di copertura proprio nei dati che ci servono.
- Niente trial a scadenza (AWS/Azure): la settimana di raccolta non deve
  morire a metà per una scadenza amministrativa.
- La VM non tocca denaro reale (il prodotto è paper-only per costruzione):
  anche in cloud resta un osservatorio, non un operatore.
