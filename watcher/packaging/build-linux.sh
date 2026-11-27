#!/usr/bin/env bash
# Construit une archive Linux autonome (source + installateur).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-0.1.0}"
STAGE="$ROOT/dist/CheckMate-linux-$VERSION"
NATIVE="$ROOT/../rust/target/release/checkmate-ui"

if [ ! -x "$NATIVE" ]; then
    echo "checkmate-ui absent : $NATIVE" >&2
    echo "Compile-le avant l'archive :" >&2
    echo "  cargo build --release -p checkmate-cli --bin checkmate-ui" >&2
    exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"

cp "$ROOT/pyproject.toml" "$ROOT/uv.lock" "$ROOT/README.md" \
    "$ROOT/config.example.toml" "$STAGE/"
cp -a "$ROOT/src" "$ROOT/systemd" "$ROOT/scripts" \
    "$ROOT/docs" "$ROOT/assets" "$STAGE/"
cp "$NATIVE" "$STAGE/checkmate-ui"

cat > "$STAGE/install.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv est requis :" \
        "https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

"$ROOT/scripts/create-venv.sh" "$ROOT"
install -m 755 "$ROOT/checkmate-ui" "$ROOT/.venv/bin/checkmate-ui"

CONFIG="$HOME/.config/checkmate-watcher/config.toml"
if [ ! -f "$CONFIG" ]; then
    "$ROOT/.venv/bin/checkmate-watcher" setup
fi

"$ROOT/scripts/install-service.sh"
EOF
chmod +x "$STAGE/install.sh"

tar -C "$ROOT/dist" -czf \
    "$ROOT/dist/CheckMate-linux-$VERSION.tar.gz" \
    "CheckMate-linux-$VERSION"
echo "Archive creee : $ROOT/dist/CheckMate-linux-$VERSION.tar.gz"
