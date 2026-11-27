"""Verifie le script d'alignement des versions."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "set_version.py"


def _module():
    spec = importlib.util.spec_from_file_location(
        "checkmate_set_version", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


set_version = _module()


def _tree(
    root: Path, version: str = "0.7.1-beta.1", build: str = "2026-11-27.1"
):
    (root / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    init = root / "watcher/src/checkmate_watcher/__init__.py"
    init.parent.mkdir(parents=True)
    init.write_text(
        f'"""Doc."""\n\n__version__ = "{version}"\n\nBUILD = "{build}"\n',
        encoding="utf-8",
    )
    (root / "watcher/pyproject.toml").write_text(
        f'[project]\nname = "checkmate-watcher"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (root / "watcher/uv.lock").write_text(
        '[[package]]\nname = "checkmate-watcher"\n'
        f'version = "{set_version.pep440(version)}"\n',
        encoding="utf-8",
    )
    (root / "rust").mkdir()
    (root / "rust/Cargo.toml").write_text(
        "[workspace]\nmembers = []\n\n[workspace.package]\n"
        f'version = "{version}"\nedition = "2024"\n',
        encoding="utf-8",
    )
    locked = "".join(
        f'[[package]]\nname = "{crate}"\nversion = "{version}"\n\n'
        for crate in set_version.CRATES
    )
    (root / "rust/Cargo.lock").write_text(locked, encoding="utf-8")


def test_pep440_normalise_les_betas():
    assert set_version.pep440("0.7.1-beta.1") == "0.7.1b1"
    assert set_version.pep440("0.7.1-beta") == "0.7.1b0"
    assert set_version.pep440("0.7.1") == "0.7.1"


def test_next_build_incremente_le_meme_jour():
    from datetime import UTC, datetime

    today = datetime(2026, 11, 27, tzinfo=UTC)

    assert set_version.next_build("2026-11-27.1", today) == "2026-11-27.2"
    assert set_version.next_build("2026-11-26.4", today) == "2026-11-27.1"
    assert set_version.next_build(None, today) == "2026-11-27.1"
    assert set_version.next_build("2026-11-27.x", today) == "2026-11-27.1"


def test_apply_propage_la_version(tmp_path):
    _tree(tmp_path)

    set_version.apply(tmp_path, "0.8.0", "2026-12-01.1")

    assert (tmp_path / "VERSION").read_text().strip() == "0.8.0"
    init = (tmp_path / set_version.INIT_FILE).read_text()
    assert '__version__ = "0.8.0"' in init
    assert 'BUILD = "2026-12-01.1"' in init
    assert (
        'version = "0.8.0"' in (tmp_path / set_version.PYPROJECT).read_text()
    )
    assert 'version = "0.8.0"' in (tmp_path / set_version.UV_LOCK).read_text()
    assert 'version = "0.8.0"' in (tmp_path / set_version.CARGO).read_text()
    lock = (tmp_path / set_version.CARGO_LOCK).read_text()
    assert lock.count('version = "0.8.0"') == len(set_version.CRATES)


def test_apply_normalise_la_beta_dans_uv_lock(tmp_path):
    _tree(tmp_path)

    set_version.apply(tmp_path, "0.8.0-beta.2", "2026-12-01.1")

    assert (
        'version = "0.8.0b2"' in (tmp_path / set_version.UV_LOCK).read_text()
    )
    assert (
        'version = "0.8.0-beta.2"'
        in (tmp_path / set_version.CARGO).read_text()
    )


def test_check_accepte_un_arbre_aligne(tmp_path):
    _tree(tmp_path)

    assert set_version.check(tmp_path) == []


def test_check_signale_une_divergence(tmp_path):
    _tree(tmp_path)
    (tmp_path / "VERSION").write_text("0.9.0\n")
    path = tmp_path / set_version.PYPROJECT
    path.write_text('[project]\nversion = "0.8.0"\n')

    errors = set_version.check(tmp_path)

    assert any(set_version.PYPROJECT in error for error in errors)
    assert any(set_version.UV_LOCK in error for error in errors)
    assert any(set_version.CARGO in error for error in errors)


def test_apply_refuse_un_motif_absent(tmp_path):
    _tree(tmp_path)
    (tmp_path / set_version.PYPROJECT).write_text('[project]\nname = "x"\n')

    try:
        set_version.apply(tmp_path, "0.8.0", "2026-12-01.1")
    except SystemExit as error:
        assert "pyproject" in str(error)
    else:
        raise AssertionError("le script aurait du echouer")
