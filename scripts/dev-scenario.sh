#!/usr/bin/env bash
# Boucle de developpement : sert un scenario capture, fait un cycle du watcher,
# s'arrete, et renvoie le code de sortie du watcher.
#
#   ./scripts/dev-scenario.sh chemins/vers/capture [port]
#   ./scripts/dev-scenario.sh capture --visible
#   affiche le navigateur du watcher
#   ./scripts/dev-scenario.sh capture --keep     laisse l'emulateur tourner
#
# Sans capture, l'emulateur genere ses pages :
#
#   ./scripts/dev-scenario.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCENARIO=""
PORT="8787"
KEEP="0"
HEADLESS="true"
VISIBLE_ON_SIGN="false"

for arg in "$@"; do
    case "$arg" in
        --keep) KEEP="1" ;;
        --visible)
            HEADLESS="false"
            VISIBLE_ON_SIGN="false"
            ;;
        [0-9]*) PORT="$arg" ;;
        *) SCENARIO="$arg" ;;
    esac
done

if ! command -v uv >/dev/null 2>&1; then
    echo "uv est requis :" \
        "https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

TMP="$(mktemp -d)"
EMULATOR_PID=""
cleanup() {
    if [ -n "$EMULATOR_PID" ] && [ "$KEEP" != "1" ]; then
        kill "$EMULATOR_PID" 2>/dev/null || true
        wait "$EMULATOR_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

EMULATOR_ARGS=(--port "$PORT" --open)
if [ -n "$SCENARIO" ]; then
    if [ ! -f "$SCENARIO/scenario.json" ]; then
        echo "scenario.json introuvable dans $SCENARIO" >&2
        exit 2
    fi
    SCENARIO="$(cd "$SCENARIO" && pwd)"
    EMULATOR_ARGS+=(--scenario "$SCENARIO")
    echo "scenario  : $SCENARIO"
else
    echo "scenario  : pages generees par l'emulateur"
fi

python3 "$ROOT/emulator/server.py" "${EMULATOR_ARGS[@]}" \
    >"$TMP/emulator.log" 2>&1 &
EMULATOR_PID=$!

BASE="http://127.0.0.1:$PORT"
for _ in $(seq 1 50); do
    if curl -sf "$BASE/api/state" >/dev/null 2>&1; then
        break
    fi
    sleep 0.2
done
if ! curl -sf "$BASE/api/state" >/dev/null 2>&1; then
    echo "l'emulateur n'a pas demarre, voir $TMP/emulator.log" >&2
    cat "$TMP/emulator.log" >&2
    exit 3
fi

SIGNATURE="$HOME/.config/checkmate-watcher/signature.json"
if [ ! -f "$SIGNATURE" ]; then
    SIGNATURE="$TMP/signature.json"
    (cd "$ROOT/watcher" && uv run python - "$SIGNATURE" <<'PY'
import sys
from pathlib import Path
from checkmate_watcher.signature import Point, save_signature

save_signature(
    Path(sys.argv[1]),
    [Point(10, 10, "start"), Point(80, 45, "move"), Point(160, 30, "end")],
)
PY
    )
fi

cat >"$TMP/config.toml" <<EOF
[cesar]
base_url = "$BASE"
login_path = "/connexion"
dashboard_path = "/"
username = "demo"
password = "demo"

[schedule]
enabled = false

[watcher]
poll_interval = 15
auto_sign = true
auto_sign_delay = 0
headless = $HEADLESS
visible_on_sign = $VISIBLE_ON_SIGN
profile_dir = "$TMP/profile"
state_file = "$TMP/state.json"

[signature]
file = "$SIGNATURE"

[updates]
enabled = false

[analytics]
enabled = false

[notifications]
enabled = false
EOF

echo "watcher   : $BASE"
if [ "$HEADLESS" = "false" ]; then
    echo "navigateur: visible pendant le cycle"
fi
echo
set +e
(cd "$ROOT/watcher" && \
    uv run checkmate-watcher --config "$TMP/config.toml" run --once -v)
CODE=$?
set -e

echo
echo "etat      : $(curl -sf "$BASE/api/state" || echo 'indisponible')"
if [ "$KEEP" = "1" ]; then
    echo "emulateur laisse sur $BASE, connexion demo / demo," \
        "Ctrl-C pour l'arreter"
    wait "$EMULATOR_PID"
fi
exit "$CODE"
