# H24 sul tuo PC Windows 10 — il piano definitivo

I servizi "gratuiti per sempre" si sono rivelati inaccendibili (Oracle:
verifiche e capacità mai disponibili) o gratuiti solo di nome (Google: l'IP
esterno si paga). Decisione: **il raccoglitore gira sul PC di casa**, che è
già lì. Con tre accorgimenti diventa affidabile quanto un server:

1. **Avvio automatico al login** + **watchdog** che lo rilancia se cade
   (attività pianificata `PumpRadar`, nessun limite di durata).
2. **Il PC non dorme mai** a corrente (lo schermo sì, si spegne dopo 5 min).
3. **Riavvii di Windows Update** assorbiti: al login successivo riparte da
   solo, e `run` all'avvio completa da solo le schede rimaste in sospeso.

## Installazione (5 minuti, una volta sola)

```powershell
cd C:\Work\git\Find
git pull
cd pump-radar
powershell -ExecutionPolicy Bypass -File deploy\windows\install.ps1   # PowerShell COME AMMINISTRATORE
```

Lo script: crea/aggiorna `.venv`, imposta l'alimentazione (mai sospendere),
registra e avvia l'attività `PumpRadar`. Da quel momento **non devi più
lanciare `run` a mano**: è già attivo, e riparte da solo.

Verifica:

```powershell
Get-ScheduledTask -TaskName PumpRadar                       # Running
Get-Content logs\pumpradar.log -Tail 30 -Wait               # il flusso vive
.\.venv\Scripts\python.exe -m pumpradar dayreport           # la copertura cresce
```

## I tre ritocchi manuali che contano

- **Orario di attività** (Impostazioni → Windows Update → Orario di
  attività): allargalo al massimo (es. 06:00–24:00), così gli aggiornamenti
  non riavviano il PC in piena raccolta notturna.
- **Se il PC si riavvia e resta alla schermata di login**, il raccoglitore
  non parte finché non accedi. Se vuoi l'autonomia totale: installa
  *Autologon* di Microsoft Sysinternals (gratuito, cifra la password) e
  imposta l'accesso automatico del tuo utente.
- **Blackout**: nel BIOS, "Restore on AC Power Loss → Power On" (se
  presente): al ritorno della corrente il PC si riaccende da solo e, con
  Autologon, la raccolta riprende senza toccare nulla.
- Se è un **portatile**: chiusura coperchio → "Non fare nulla" (a corrente).

## Routine della settimana

- Ogni giorno, 30 secondi: `dayreport` — copertura continua? Il report
  dichiara da sé eventuali buchi (riavvii, blackout).
- A fine settimana: copia di `data\radar.db` su un altro disco/pennetta
  (è il capitale del progetto), poi `python -m pumpradar autopsy`.
- Log: `logs\pumpradar.log` cresce; svuotalo a fine settimana (a servizio
  fermo: `Stop-ScheduledTask -TaskName PumpRadar`, svuota, `Start-…`).

## Costi onesti

Luce: un desktop acceso H24 con carico leggero consuma ~50–90 W → 1,2–2,2
kWh/giorno → per la settimana di raccolta siamo a pochi euro. Se un domani
il PC restasse acceso *solo* per PumpRadar in permanenza, una VPS da ~5
€/mese (es. Hetzner, Germania) costerebbe meno della corrente: il kit è già
pronto anche per quella (`deploy/install.sh`), ma per ora il PC vince:
zero euro, zero lotterie, dati sotto il tuo controllo.

## Perché gli altri piani sono stati scartati

| Servizio | Esito |
|---|---|
| Oracle Always Free | Mai ottenibile in pratica (verifica carta / "out of capacity" perpetua) |
| Google e2-micro | Gratis il calcolo, ma IP esterno ~3,65 $/mese, 1 GB RAM, solo USA: non è "gratis" |
| Render / Railway / Fly.io free | Sleep o crediti una tantum: un processo H24 non ci vive |
| AWS / Azure free | Scadono in 6–12 mesi |
