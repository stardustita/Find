#!/usr/bin/env bash
# PumpRadar — installazione H24 su VM Ubuntu/Debian (Oracle Always Free ARM,
# Google e2-micro o qualsiasi VPS). Idempotente: rilanciarlo non rompe nulla.
set -euo pipefail

echo "▸ pacchetti di sistema"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git

if [ ! -d "$HOME/Find" ]; then
  echo "▸ clono il repository"
  git clone https://github.com/stardustita/Find.git "$HOME/Find"
else
  echo "▸ aggiorno il repository"
  git -C "$HOME/Find" pull --ff-only || true
fi

cd "$HOME/Find/pump-radar"
echo "▸ ambiente Python"
python3 -m venv .venv
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt
mkdir -p data logs

echo "▸ servizio systemd (riavvio automatico, attivo al boot)"
sed -e "s|__USER__|$(whoami)|g" -e "s|__HOME__|$HOME|g" \
    deploy/pumpradar.service | sudo tee /etc/systemd/system/pumpradar.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now pumpradar

echo
echo "✔ PumpRadar attivo. Comandi utili:"
echo "  sudo systemctl status pumpradar      # stato"
echo "  journalctl -u pumpradar -f           # log in diretta"
echo "  cd ~/Find/pump-radar && .venv/bin/python -m pumpradar dayreport   # controllo copertura"
