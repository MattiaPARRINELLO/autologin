#!/usr/bin/env bash
# Deploie le collecteur de statistiques sur le VPS qui heberge deja Caddy.
#
#   Exemple : CHECKMATE_STATS_KEY=~/.ssh/id_ed25519
#   ./stats/deploy.sh
#
# Variables d'environnement acceptees :
#   CHECKMATE_STATS_HOST  cible SSH (defaut ubuntu@main.mprnl.fr)
#   CHECKMATE_STATS_KEY   cle SSH privee (defaut ~/.ssh/id_ed25519)
#   CHECKMATE_STATS_DOMAIN nom public (defaut stats.mprnl.fr)
set -euo pipefail

HOST="${CHECKMATE_STATS_HOST:-ubuntu@main.mprnl.fr}"
KEY="${CHECKMATE_STATS_KEY:-$HOME/.ssh/id_ed25519}"
DIR="/opt/checkmate-stats"
COLLECTOR_TAG=checkmate-stats-public-ingest

ssh_opts=(-i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
ssh_target="$HOST"
run() { ssh "${ssh_opts[@]}" "$ssh_target" "$@"; }

echo "==> Preparation de $DIR"
run "sudo -n mkdir -p '$DIR/data' && sudo -n chown -R ubuntu:ubuntu '$DIR'"

echo "==> Envoi des fichiers"
tar -czf - -C "$(dirname "$0")" collector.py Dockerfile docker-compose.yml \
  | run "tar -xzf - -C '$DIR'"

echo "==> Configuration"
run "cd '$DIR' && if [ ! -f .env ]; then
  password=\$(openssl rand -hex 24)
  cat > .env <<EOF
CHECKMATE_INGEST_KEY=$COLLECTOR_TAG
CHECKMATE_DASHBOARD_USER=checkmate
CHECKMATE_DASHBOARD_PASSWORD=\$password
EOF
  chmod 600 .env
  printf '%s\n' \"\$password\" > dashboard-password.txt
  chmod 600 dashboard-password.txt
  echo 'mot de passe du tableau de bord : $DIR/dashboard-password.txt'
fi"
run "cd '$DIR' && " \
    "sed -i " \
    "'s/^CHECKMATE_INGEST_KEY=.*/CHECKMATE_INGEST_KEY=$COLLECTOR_TAG/' .env"

echo "==> Demarrage du conteneur"
run "cd '$DIR' && sudo -n chown -R 10001:10001 '$DIR/data' " \
    "&& sudo -n docker compose up -d --build --force-recreate"

echo "==> Route Caddy"
if ! run "sudo -n grep -q 'cm-stats' /opt/homarr/Caddyfile"; then
  run 'sudo -n python3 - <<"PY"
from pathlib import Path
path = Path("/opt/homarr/Caddyfile")
text = path.read_text()
old = "main.mprnl.fr {\n    reverse_proxy homarr:7575\n}"
new = ("main.mprnl.fr {\n"
       "    # Statistiques CheckMate, servies sous le meme certificat "
       "que Homarr.\n"
       "    handle_path /cm-stats/* {\n"
       "        reverse_proxy checkmate-stats:8099\n"
       "    }\n"
       "    reverse_proxy homarr:7575\n}")
if old in text:
    path.write_text(text.replace(old, new))
    print("route ajoutee")
else:
    raise SystemExit("bloc main.mprnl.fr introuvable")
PY'
  run "sudo -n docker exec caddy caddy reload --config /etc/caddy/Caddyfile"
else
  echo "route deja presente"
fi

echo "==> Verification"
if run "curl -fsS https://main.mprnl.fr/cm-stats/health"; then
  echo
  echo "OK : https://main.mprnl.fr/cm-stats/ (utilisateur checkmate)"
  echo "Mot de passe : ssh $HOST 'sudo -n cat $DIR/dashboard-password.txt'"
else
  echo "ECHEC : le collecteur ne repond pas" >&2
  exit 1
fi
