#!/usr/bin/env python3
"""Aligne toutes les versions du depot sur `VERSION`.

`VERSION` est l'unique source de verite. Le script propage la version dans
`__init__.py`, `pyproject.toml`, `uv.lock`, `rust/Cargo.toml` et
`rust/Cargo.lock`, et met a jour `BUILD`.

    python3 scripts/set_version.py 0.7.2-beta.1
    python3 scripts/set_version.py 0.7.2-beta.1 --build 2026-12-01.1
    python3 scripts/set_version.py --check

`--check` ne modifie rien et sort en code 1 si un fichier diverge de `VERSION`.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = "VERSION"
INIT_FILE = "watcher/src/checkmate_watcher/__init__.py"
PYPROJECT = "watcher/pyproject.toml"
UV_LOCK = "watcher/uv.lock"
CARGO = "rust/Cargo.toml"
CARGO_LOCK = "rust/Cargo.lock"
CRATES = ("checkmate-cli", "checkmate-core", "checkmate-platform", "checkmate-ui")


def pep440(version: str) -> str:
    """Convertit une version semver beta en forme normalisee PEP 440."""
    if "-beta." in version:
        return version.replace("-beta.", "b")
    if "-beta" in version:
        return version.replace("-beta", "b0")
    return version


def next_build(current: str | None, today: datetime) -> str:
    prefix = f"{today:%Y-%m-%d}"
    if current and current.startswith(f"{prefix}."):
        suffix = current.removeprefix(f"{prefix}.")
        if suffix.isdigit():
            return f"{prefix}.{int(suffix) + 1}"
    return f"{prefix}.1"


def read_version(root: Path) -> str:
    path = root / VERSION_FILE
    if not path.is_file():
        raise SystemExit(f"{VERSION_FILE} absent dans {root}")
    value = path.read_text(encoding="utf-8").strip()
    if not value or any(char.isspace() for char in value):
        raise SystemExit(f"{VERSION_FILE} invalide : {value!r}")
    return value


def current_build(text: str) -> str | None:
    match = re.search(r'^BUILD = "([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else None


def replace_once(text: str, pattern: str, replacement: str, source: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"motif introuvable dans {source} : {pattern}")
    return updated


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def apply(root: Path, version: str, build: str) -> None:
    write(root / VERSION_FILE, f"{version}\n")

    init_path = root / INIT_FILE
    init_text = init_path.read_text(encoding="utf-8")
    init_text = replace_once(
        init_text,
        r'^__version__ = "[^"]+"',
        f'__version__ = "{version}"',
        INIT_FILE,
    )
    init_text = replace_once(
        init_text,
        r'^BUILD = "[^"]+"',
        f'BUILD = "{build}"',
        INIT_FILE,
    )
    write(init_path, init_text)

    pyproject_path = root / PYPROJECT
    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    pyproject_text = replace_once(
        pyproject_text,
        r'^version = "[^"]+"',
        f'version = "{version}"',
        PYPROJECT,
    )
    write(pyproject_path, pyproject_text)

    lock_path = root / UV_LOCK
    lock_text = lock_path.read_text(encoding="utf-8")
    lock_text = replace_once(
        lock_text,
        r'(name = "checkmate-watcher"\nversion = ")[^"]+(")',
        rf"\g<1>{pep440(version)}\g<2>",
        UV_LOCK,
    )
    write(lock_path, lock_text)

    cargo_path = root / CARGO
    cargo_text = cargo_path.read_text(encoding="utf-8")
    block = re.search(r"(\[workspace\.package\].*?)(\n\[|\Z)", cargo_text, re.DOTALL)
    if block is None:
        raise SystemExit(f"bloc [workspace.package] absent de {CARGO}")
    updated_block = replace_once(
        block.group(1),
        r'^version = "[^"]+"',
        f'version = "{version}"',
        CARGO,
    )
    cargo_text = (
        cargo_text[: block.start(1)] + updated_block + cargo_text[block.end(1) :]
    )
    write(cargo_path, cargo_text)

    cargo_lock_path = root / CARGO_LOCK
    cargo_lock_text = cargo_lock_path.read_text(encoding="utf-8")
    for crate in CRATES:
        cargo_lock_text = replace_once(
            cargo_lock_text,
            rf'(name = "{crate}"\nversion = ")[^"]+(")',
            rf"\g<1>{version}\g<2>",
            CARGO_LOCK,
        )
    write(cargo_lock_path, cargo_lock_text)


def check(root: Path) -> list[str]:
    version = read_version(root)
    errors = []
    expected = {
        INIT_FILE: rf'^__version__ = "{re.escape(version)}"',
        PYPROJECT: rf'^version = "{re.escape(version)}"',
        UV_LOCK: rf'name = "checkmate-watcher"\nversion = "{re.escape(pep440(version))}"',
    }
    for relative, pattern in expected.items():
        text = (root / relative).read_text(encoding="utf-8")
        if re.search(pattern, text, re.MULTILINE) is None:
            errors.append(f"{relative} ne porte pas {version}")
    cargo_text = (root / CARGO).read_text(encoding="utf-8")
    if (
        re.search(
            rf'\[workspace\.package\].*?^version = "{re.escape(version)}"',
            cargo_text,
            re.DOTALL | re.MULTILINE,
        )
        is None
    ):
        errors.append(f"{CARGO} ne porte pas {version}")
    cargo_lock_text = (root / CARGO_LOCK).read_text(encoding="utf-8")
    for crate in CRATES:
        if (
            re.search(
                rf'name = "{crate}"\nversion = "{re.escape(version)}"',
                cargo_lock_text,
            )
            is None
        ):
            errors.append(f"{CARGO_LOCK} ne porte pas {version} pour {crate}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?")
    parser.add_argument("--build")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()

    if args.check:
        errors = check(args.root)
        for error in errors:
            print(f"version desalignee : {error}", file=sys.stderr)
        if errors:
            return 1
        print(f"versions alignees sur {read_version(args.root)}")
        return 0

    if not args.version:
        parser.error("version requise sauf avec --check")
    init_text = (args.root / INIT_FILE).read_text(encoding="utf-8")
    build = args.build or next_build(current_build(init_text), datetime.now(UTC))
    apply(args.root, args.version, build)
    print(f"version {args.version}, build {build}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
