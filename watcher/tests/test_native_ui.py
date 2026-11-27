"""Tests du lancement de la coquille native GPUI."""

from __future__ import annotations

from pathlib import Path

import pytest

from checkmate_watcher import cli, native_ui


def _fake_binary(folder: Path) -> Path:
    binary = folder / native_ui.binary_name()
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    return binary


def _neutraliser_decouverte(monkeypatch, tmp_path):
    monkeypatch.setattr(native_ui.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        native_ui, "_repository_root", lambda: tmp_path / "repo"
    )
    monkeypatch.setattr(native_ui.sys, "executable", str(tmp_path / "python"))


def test_locate_prefere_la_variable_d_environnement(tmp_path, monkeypatch):
    binary = _fake_binary(tmp_path)
    monkeypatch.setenv(native_ui.BINARY_ENV, str(binary))
    _neutraliser_decouverte(monkeypatch, tmp_path)
    assert native_ui.locate() == binary
    assert native_ui.available()


def test_locate_ignore_un_chemin_absent(tmp_path, monkeypatch):
    monkeypatch.setenv(native_ui.BINARY_ENV, str(tmp_path / "absent"))
    _neutraliser_decouverte(monkeypatch, tmp_path)
    assert native_ui.locate() is None
    assert not native_ui.available()


def test_locate_trouve_le_binaire_a_cote_de_python(tmp_path, monkeypatch):
    monkeypatch.delenv(native_ui.BINARY_ENV, raising=False)
    binary = _fake_binary(tmp_path)
    monkeypatch.setattr(
        native_ui, "_repository_root", lambda: tmp_path / "repo"
    )
    monkeypatch.setattr(native_ui.shutil, "which", lambda name: None)
    monkeypatch.setattr(native_ui.sys, "executable", str(tmp_path / "python"))
    assert native_ui.locate() == binary


def test_launch_transmet_les_arguments(tmp_path, monkeypatch):
    binary = _fake_binary(tmp_path)
    monkeypatch.setenv(native_ui.BINARY_ENV, str(binary))
    appels = []

    class FauxProcess:
        def __init__(self, command, **options):
            appels.append((command, options))

    monkeypatch.setattr(native_ui.subprocess, "Popen", FauxProcess)
    assert native_ui.launch("--setup")
    assert appels[0][0] == [str(binary), "--setup"]
    assert appels[0][1]["close_fds"] is True


def test_launch_sans_binaire_ne_fait_rien(tmp_path, monkeypatch):
    monkeypatch.setenv(native_ui.BINARY_ENV, str(tmp_path / "absent"))
    _neutraliser_decouverte(monkeypatch, tmp_path)
    assert not native_ui.launch()


def test_une_erreur_de_lancement_est_absorbee(tmp_path, monkeypatch):
    binary = _fake_binary(tmp_path)
    monkeypatch.setenv(native_ui.BINARY_ENV, str(binary))

    def echouer(command, **options):
        raise OSError("permission refusee")

    monkeypatch.setattr(native_ui.subprocess, "Popen", echouer)
    assert not native_ui.launch()


def test_la_commande_status_prefere_la_fenetre_native(monkeypatch):
    monkeypatch.setattr(
        cli, "read_runtime", lambda: {"url": "http://127.0.0.1:1/"}
    )
    monkeypatch.setattr(cli, "status_alive", lambda runtime: True)
    monkeypatch.setattr(native_ui, "open_dashboard", lambda: True)
    monkeypatch.setattr(
        cli,
        "open_url",
        lambda url: pytest.fail("le navigateur ne doit pas servir"),
    )
    assert cli._ouvrir_si_pret() is True


def test_la_commande_status_replie_sur_le_navigateur(monkeypatch):
    monkeypatch.setattr(
        cli, "read_runtime", lambda: {"url": "http://127.0.0.1:1/"}
    )
    monkeypatch.setattr(cli, "status_alive", lambda runtime: True)
    monkeypatch.setattr(native_ui, "open_dashboard", lambda: False)
    ouverts = []
    monkeypatch.setattr(cli, "open_url", ouverts.append)
    assert cli._ouvrir_si_pret() is True
    assert ouverts == ["http://127.0.0.1:1/"]


def test_locate_trouve_le_binaire_dans_internal_pyinstaller(
    tmp_path, monkeypatch
):
    monkeypatch.delenv(native_ui.BINARY_ENV, raising=False)
    internal = tmp_path / "_internal"
    internal.mkdir()
    binary = _fake_binary(internal)
    monkeypatch.setattr(native_ui.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        native_ui, "_repository_root", lambda: tmp_path / "repo"
    )
    monkeypatch.setattr(
        native_ui.sys, "executable", str(tmp_path / "CheckMate")
    )
    assert native_ui.locate() == binary
