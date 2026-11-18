#!/usr/bin/env bash
# Installe le watcher en service utilisateur systemd (demarrage a la connexion).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="$HOME/.config/checkmate-watcher"
CONFIG="$CONFIG_DIR/config.toml"
UNIT_DIR="$HOME/.config/systemd/user"
BIN_DIR="$HOME/.local/bin"

if [ ! -x "$ROOT/.venv/bin/checkmate-watcher" ]; then
    echo "Dependances absentes. Lance d'abord :"
    echo "  cd $ROOT && uv sync"
    exit 1
fi

if [ ! -f "$CONFIG" ]; then
    echo "Configuration reelle absente : $CONFIG"
    echo "Copie config.example.toml, renseigne tes identifiants, puis relance :"
    echo "  mkdir -p $CONFIG_DIR"
    echo "  cp $ROOT/config.example.toml $CONFIG"
    echo "  chmod 600 $CONFIG"
    exit 1
fi

mkdir -p "$UNIT_DIR" "$BIN_DIR" "$CONFIG_DIR"
ln -sf "$ROOT/.venv/bin/checkmate-watcher" "$BIN_DIR/checkmate-watcher"
install -m 644 "$ROOT/systemd/checkmate-watcher.service" "$UNIT_DIR/checkmate-watcher.service"

if [ ! -f "$CONFIG_DIR/env" ]; then
    cat > "$CONFIG_DIR/env" <<'EOF'
# Variables d'environnement du service CheckMate.
# Renseigne le mot de passe si ta config utilise password_env.
# CHECKMATE_PASSWORD=motdepasse
EOF
    chmod 600 "$CONFIG_DIR/env"
    echo "Fichier cree : $CONFIG_DIR/env"
fi

systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable --now checkmate-watcher.service
systemctl --user --no-pager status checkmate-watcher.service || true

echo
echo "Service installe et demarre a chaque connexion."
echo "Logs     : journalctl --user -u checkmate-watcher -f"
echo "Arreter  : systemctl --user stop checkmate-watcher"
echo "Desactiver : systemctl --user disable checkmate-watcher"
