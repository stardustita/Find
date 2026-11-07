#!/usr/bin/env bash
# PumpRadar - installazione H24 su VM Ubuntu/Debian (Google e2-micro,
# Hetzner o qualsiasi VPS). Idempotente: rilanciarlo non rompe nulla.
set -euo pipefail

echo "> pacchetti di sistema"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git

# Macchine minuscole (es. e2-micro da 1 GB): swap di sicurezza + tetto pool.
mem_kb=$(awk '/MemTotal/{print $2}' /proc/meminfo)
if [ "${mem_kb:-0}" -lt 2600000 ]; then
  if ! swapon --show | grep -q .; then
    echo "> creo uno swap da 2 GB (macchina piccola)"
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile || true
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  fi
fi

if [ ! -d "$HOME/Find" ]; then
  echo "> clono il repository"
  if ! git clone https://github.com/stardustita/Find.git "$HOME/Find"; then
    echo "X Clone HTTPS fallito: se il repo e privato, crea una deploy key:"
    echo "    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ''"
    echo "    cat ~/.ssh/id_ed25519.pub   # <- aggiungila su GitHub: repo -> Settings -> Deploy keys"
    echo "    git clone git@github.com:stardustita/Find.git ~/Find"
    echo "  poi rilancia questo script."
    exit 1
  fi
else
  echo "> aggiorno il repository"
  git -C "$HOME/Find" pull --ff-only || true
fi

cd "$HOME/Find/pump-radar"
echo "> ambiente Python"
python3 -m venv .venv
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt
mkdir -p data logs

echo "> servizio systemd (riavvio automatico, attivo al boot)"
sed -e "s|__USER__|$(whoami)|g" -e "s|__HOME__|$HOME|g" \
    deploy/pumpradar.service | sudo tee /etc/systemd/system/pumpradar.service >/dev/null
if [ "${mem_kb:-0}" -lt 2600000 ]; then
  sudo mkdir -p /etc/systemd/system/pumpradar.service.d
  printf '[Service]\nEnvironment=PR_RUNNER_MAX_TRACKED_POOLS=200\n' \
    | sudo tee /etc/systemd/system/pumpradar.service.d/small.conf >/dev/null
fi
sudo systemctl daemon-reload
sudo systemctl enable --now pumpradar

echo
echo "OK PumpRadar attivo. Comandi utili:"
echo "  sudo systemctl status pumpradar      # stato"
echo "  journalctl -u pumpradar -f           # log in diretta"
echo "  cd ~/Find/pump-radar && .venv/bin/python -m pumpradar dayreport   # controllo copertura"
