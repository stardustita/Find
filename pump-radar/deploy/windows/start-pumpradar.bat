@echo off
rem PumpRadar watchdog — rilancia il raccoglitore se esce o crasha.
rem Non chiudere questa finestra: per fermarlo, termina l'attivita' PumpRadar
rem da Utilita' di pianificazione (o chiudi il processo python).
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
cd /d %~dp0..\..
if not exist logs mkdir logs
:loop
echo [%date% %time%] avvio PumpRadar >> logs\watchdog.log
.venv\Scripts\python.exe -m pumpradar run >> logs\pumpradar.log 2>&1
echo [%date% %time%] PumpRadar uscito (codice %errorlevel%), riavvio tra 15s >> logs\watchdog.log
timeout /t 15 /nobreak >nul
goto loop
