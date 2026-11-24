#!/usr/bin/env python3
"""Verifie qu'aucune version figee ne traine dans la documentation.

Le README pointe sur `releases/latest` et sur le badge dynamique de version :
il n'a donc jamais besoin d'etre edite a chaque release. Ce script garde cette
invariant en refusant un nom d'artefact ou une version stable codee en dur.

Usage :
    python3 scripts/check_doc_versions.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Documents dont le contenu est affiche aux utilisateurs.
DOCS = [
    ROOT / "README.md",
    ROOT / "PRIVACY.md",
    ROOT / "SUPPORT.md",
    ROOT / "watcher" / "README.md",
] + sorted((ROOT / "watcher" / "docs").glob("*.md"))

# Un nom d'artefact ne doit jamais coder une version : on ecrit `<version>`.
ARTIFACT = re.compile(r"CheckMate-(?:Setup|linux)-\d+\.\d+\.\d+")
# L'etat du projet doit renvoyer au badge, pas figer un numero.
STABLE_STATE = re.compile(r"Version stable actuelle\s*:\s*\*{0,2}\d+\.\d+\.\d+")


def violations(path: Path) -> list[tuple[int, str, str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    found = []
    for number, line in enumerate(lines, start=1):
        for pattern in (ARTIFACT, STABLE_STATE):
            match = pattern.search(line)
            if match:
                found.append((number, match.group(0), line.strip()))
    return found


def report(results: list[tuple[Path, int, str, str]], doc_count: int) -> None:
    for relative, number, match, line in results:
        print(f"{relative}:{number}: version figee `{match}`", file=sys.stderr)
        print(f"  {line}", file=sys.stderr)

    if results:
        print(
            "\nRemplace la version par `<version>` et renvoie vers "
            "`releases/latest` : le README doit rester valable a chaque release.",
            file=sys.stderr,
        )
    else:
        print(f"Documentation a jour : {doc_count} fichiers verifies.")


def main() -> int:
    results: list[tuple[Path, int, str, str]] = []
    for path in DOCS:
        for number, match, line in violations(path):
            results.append((path.relative_to(ROOT), number, match, line))

    report(results, len(DOCS))
    return 1 if results else 0


if __name__ == "__main__":
    raise SystemExit(main())
