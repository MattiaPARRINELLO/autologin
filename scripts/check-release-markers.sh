#!/usr/bin/env bash
# Verifie les marqueurs obligatoires de la prochaine release.
set -euo pipefail

FILE=".github/release-markers.txt"
if [ ! -f "$FILE" ]; then
    echo "::error::marqueurs de release absents : $FILE"
    exit 1
fi

read_value() {
    grep -E "^CHECKMATE-$1:" "$FILE" | head -1 | sed 's/^[^:]*:[[:space:]]*//'
}

migration="$(read_value MIGRATION)"
required="$(read_value REQUIRED)"
if [ -z "$migration" ] || [ -z "$required" ]; then
    echo "::error::CHECKMATE-MIGRATION et CHECKMATE-REQUIRED " \
        "sont obligatoires (0 si non applicable)"
    exit 1
fi

manual=false
if [ "$migration" != "0" ] || [ "$required" != "0" ]; then
    manual=true
    echo "::warning::marqueur non nul : verification manuelle " \
        "obligatoire avant publication"
fi

echo "manual=$manual" >> "$GITHUB_OUTPUT"
