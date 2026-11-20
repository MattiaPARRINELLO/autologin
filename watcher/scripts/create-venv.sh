#!/usr/bin/env bash
# Cree le venv de l'application.
#
# Quand PyGObject est installe pour le Python du systeme, le venv herite de ses
# paquets : pywebview peut alors ouvrir une vraie fenetre GTK/WebKit. Sinon on
# retombe sur le Python gere par uv, et le tableau de bord s'ouvre dans le
# navigateur.
set -euo pipefail

PROJECT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

UV_BIN="$(command -v uv || true)"
if [ -z "$UV_BIN" ]; then
    echo "uv est requis : https://docs.astral.sh/uv/"
    exit 1
fi

SYSTEM_PYTHON=""
if [ -x /usr/bin/python3 ] && /usr/bin/python3 -c 'import gi' >/dev/null 2>&1; then
    SYSTEM_PYTHON="/usr/bin/python3"
fi

if [ -n "$SYSTEM_PYTHON" ]; then
    rm -rf "$PROJECT/.venv"
    if ! "$UV_BIN" venv --system-site-packages --python "$SYSTEM_PYTHON" \
        "$PROJECT/.venv" >/dev/null 2>&1 ||
        ! "$UV_BIN" sync --no-dev --project "$PROJECT" >/dev/null 2>&1; then
        echo "PyGObject incompatible, installation avec le Python gere par uv."
        rm -rf "$PROJECT/.venv"
        "$UV_BIN" sync --no-dev --project "$PROJECT" >/dev/null
    fi
else
    "$UV_BIN" sync --no-dev --project "$PROJECT" >/dev/null
fi
