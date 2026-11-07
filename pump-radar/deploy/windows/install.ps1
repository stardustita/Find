# PumpRadar — installazione H24 sul PC Windows 10/11 di casa.
# Esegui in PowerShell COME AMMINISTRATORE:
#   powershell -ExecutionPolicy Bypass -File deploy\windows\install.ps1
$ErrorActionPreference = 'Stop'

$admin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host "✖ Serve PowerShell come amministratore (tasto destro → Esegui come amministratore)." -ForegroundColor Red
    exit 1
}

$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent   # ...\pump-radar
Set-Location $root
Write-Host "▸ PumpRadar in: $root"

# --- ambiente Python -------------------------------------------------------
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "▸ creo l'ambiente virtuale"
    try { py -3 -m venv .venv } catch { python -m venv .venv }
}
Write-Host "▸ installo le dipendenze"
& .\.venv\Scripts\python.exe -m pip install -q -U pip
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
New-Item -ItemType Directory -Force -Path data, logs | Out-Null

# --- alimentazione: il PC non deve dormire (a corrente) --------------------
Write-Host "▸ alimentazione: mai sospensione/ibernazione a corrente (lo schermo puo' spegnersi)"
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 5

# --- attivita' pianificata: avvio al login + watchdog ----------------------
Write-Host "▸ registro l'attivita' pianificata 'PumpRadar' (avvio al login, nessun limite di durata)"
$bat       = Join-Path $PSScriptRoot 'start-pumpradar.bat'
$action    = New-ScheduledTaskAction -Execute $bat
$trigger   = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'PumpRadar' -Action $action -Trigger $trigger -Settings $taskSettings `
    -Description 'PumpRadar: raccolta dati pump.fun H24 (paper, nessun denaro reale)' -Force | Out-Null
Start-ScheduledTask -TaskName 'PumpRadar'

Write-Host ""
Write-Host "✔ Fatto: PumpRadar e' attivo e partira' da solo a ogni login." -ForegroundColor Green
Write-Host "  Stato attivita' : Get-ScheduledTask -TaskName PumpRadar"
Write-Host "  Log in diretta  : Get-Content logs\pumpradar.log -Tail 30 -Wait"
Write-Host "  Controllo dati  : .\.venv\Scripts\python.exe -m pumpradar dayreport"
Write-Host "  Per fermarlo    : Stop-ScheduledTask -TaskName PumpRadar (e chiudi la finestra del watchdog)"
