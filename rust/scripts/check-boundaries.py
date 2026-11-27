#!/usr/bin/env python3
"""Verifie les frontieres entre les crates du workspace Rust.

Regles :

- `checkmate-core` ne depend d'aucune autre crate du workspace et d'aucune
  crate liee a une plateforme ;
- `checkmate-platform` ne depend pas de `checkmate-ui` ni de `checkmate-cli` ;
- `checkmate-ui` ne depend pas de `checkmate-cli` ;
- les quatre crates existent et `checkmate-cli` depend bien de `checkmate-core`.

Le script s'appuie sur `cargo metadata`, donc il suit exactement le graphe que
Cargo construit, y compris les dependances de developpement.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRATES = {
    "checkmate-core",
    "checkmate-platform",
    "checkmate-ui",
    "checkmate-cli",
}
FORBIDDEN = {
    "checkmate-core": {"checkmate-platform", "checkmate-ui", "checkmate-cli"},
    "checkmate-platform": {"checkmate-ui", "checkmate-cli"},
    "checkmate-ui": {"checkmate-cli"},
    "checkmate-cli": set(),
}
PLATFORM_CRATES = {
    "dbus",
    "gtk",
    "gtk4",
    "ksni",
    "notify-rust",
    "objc2",
    "tray-icon",
    "webview2-com",
    "winapi",
    "windows",
    "windows-sys",
    "zbus",
}


def metadata() -> dict:
    output = subprocess.run(
        ["cargo", "metadata", "--no-deps", "--format-version", "1"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(output)


def dependencies(package: dict) -> set[str]:
    return {dep["name"] for dep in package["dependencies"]}


def check(payload: dict) -> list[str]:
    packages = {package["name"]: package for package in payload["packages"]}
    errors = []

    missing = CRATES - packages.keys()
    if missing:
        errors.append(f"crates manquantes : {', '.join(sorted(missing))}")

    for name, package in packages.items():
        deps = dependencies(package)
        forbidden = FORBIDDEN.get(name, set()) & deps
        if forbidden:
            errors.append(f"{name} depend de {', '.join(sorted(forbidden))}, interdit")
        if name == "checkmate-core":
            platform = deps & PLATFORM_CRATES
            if platform:
                errors.append(
                    "checkmate-core depend d'une crate plateforme : "
                    + ", ".join(sorted(platform))
                )
            if deps & CRATES:
                errors.append(
                    "checkmate-core ne doit dependre d'aucune crate du workspace"
                )

    cli = packages.get("checkmate-cli")
    if cli is not None and "checkmate-core" not in dependencies(cli):
        errors.append("checkmate-cli doit dependre de checkmate-core")

    return errors


def main() -> int:
    errors = check(metadata())
    if errors:
        for error in errors:
            print(f"frontiere invalide : {error}", file=sys.stderr)
        return 1
    print("frontieres des crates : ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
