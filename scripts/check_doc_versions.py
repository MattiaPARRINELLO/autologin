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


def _matches(line: str) -> list[str]:
    found = []
    for pattern in (ARTIFACT, STABLE_STATE):
        match = pattern.search(line)
        if match:
            found.append(match.group(0))
    return found


def violations(path: Path) -> list[tuple[int, str, str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    return [
        (number, found, line.strip())
        for number, line in enumerate(lines, start=1)
        for found in _matches(line)
    ]


def _print_result(relative: Path, number: int, match: str, line: str) -> None:
    print(f"{relative}:{number}: version figee `{match}`", file=sys.stderr)
    print(f"  {line}", file=sys.stderr)


def _print_summary(results: list, doc_count: int) -> None:
    if results:
        print(
            "\nRemplace la version par `<version>` et renvoie vers "
            "`releases/latest` : le README doit rester valable a chaque release.",
            file=sys.stderr,
        )
        return
    print(f"Documentation a jour : {doc_count} fichiers verifies.")


def report(results: list[tuple[Path, int, str, str]], doc_count: int) -> None:
    for result in results:
        _print_result(*result)
    _print_summary(results, doc_count)


def main() -> int:
    results: list[tuple[Path, int, str, str]] = []
    for path in DOCS:
        for number, match, line in violations(path):
            results.append((path.relative_to(ROOT), number, match, line))

    report(results, len(DOCS))
    return 1 if results else 0


if __name__ == "__main__":
    raise SystemExit(main())
