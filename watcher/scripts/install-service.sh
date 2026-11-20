#!/usr/bin/env bash
# Installe le watcher dans ~/.local/share/checkmate-watcher/app et l'active
# comme service utilisateur systemd. Re-executable pour mettre a jour.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$HOME/.local/share/checkmate-watcher/app"
CONFIG_DIR="$HOME/.config/checkmate-watcher"
CONFIG="$CONFIG_DIR/config.toml"
UNIT_DIR="$HOME/.config/systemd/user"
BIN="$HOME/.local/bin/checkmate-watcher"

UV_BIN="$(command -v uv || true)"
if [ -z "$UV_BIN" ]; then
    echo "uv est requis : https://docs.astral.sh/uv/"
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

mkdir -p "$APP_DIR" "$UNIT_DIR" "$CONFIG_DIR" "$HOME/.local/bin"

if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete-excluded \
        --exclude .venv \
        --exclude .git \
        --exclude build \
        --exclude dist \
        --exclude dist-installer \
        --exclude __pycache__ \
        --exclude .pytest_cache \
        --exclude .ruff_cache \
        "$ROOT/" "$APP_DIR/"
else
    find "$APP_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    cp -a "$ROOT/pyproject.toml" "$ROOT/uv.lock" "$ROOT/src" "$APP_DIR/"
fi

"$UV_BIN" sync --no-dev --project "$APP_DIR" >/dev/null
echo "Application installee dans $APP_DIR"

rm -f "$BIN"
cat > "$BIN" <<EOF
#!/usr/bin/env bash
# Reconstruit le venv automatiquement s'il a disparu.
if [ -x "$APP_DIR/.venv/bin/checkmate-watcher" ]; then
    exec "$APP_DIR/.venv/bin/checkmate-watcher" "\$@"
fi
exec "$UV_BIN" run --project "$APP_DIR" checkmate-watcher "\$@"
EOF
chmod +x "$BIN"

install -m 644 "$ROOT/systemd/checkmate-watcher.service" "$UNIT_DIR/checkmate-watcher.service"
install -m 644 "$ROOT/systemd/checkmate-watchdog.service" "$UNIT_DIR/checkmate-watchdog.service"
install -m 644 "$ROOT/systemd/checkmate-watchdog.timer" "$UNIT_DIR/checkmate-watchdog.timer"

if [ ! -f "$CONFIG_DIR/env" ]; then
    cat > "$CONFIG_DIR/env" <<'EOF'
# Variables d'environnement du service CheckMate.
# Renseigne le mot de passe si ta config utilise password_env.
# CHECKMATE_PASSWORD=motdepasse
EOF
    chmod 600 "$CONFIG_DIR/env"
    echo "Fichier cree : $CONFIG_DIR/env (renseigne CHECKMATE_PASSWORD)"
fi

systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable checkmate-watcher.service
systemctl --user enable --now checkmate-watchdog.timer
systemctl --user restart checkmate-watcher.service
systemctl --user --no-pager status checkmate-watcher.service || true

echo
echo "Service installe et demarre a chaque connexion."
echo "Logs     : journalctl --user -u checkmate-watcher -f"
echo "Arreter  : systemctl --user stop checkmate-watcher"
echo "Desactiver : systemctl --user disable checkmate-watcher"
