from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from checkmate_watcher import self_update
from checkmate_watcher.updates import UpdateError


def test_install_refuse_une_archive_absente(tmp_path):
    with pytest.raises(UpdateError):
        self_update.install(tmp_path / "absent.tar.gz")


def test_script_linux_echappe_les_chemins(tmp_path):
    archive = tmp_path / "avec espace" / "CheckMate-linux-0.4.2.tar.gz"
    archive.parent.mkdir()
    archive.write_bytes(b"x")
    captured: dict = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return object()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    try:
        self_update._install_linux(archive, archive.parent)
    finally:
        monkeypatch.undo()

    script_path = Path(captured["argv"][1])
    script = script_path.read_text(encoding="utf-8")
    assert "'" + str(archive) + "'" in script
    assert "tar -xzf" in script
    assert captured["kwargs"]["start_new_session"] is True


def test_install_windows_utilise_les_options_silencieuses(tmp_path):
    archive = tmp_path / "CheckMate-Setup.exe"
    archive.write_bytes(b"x")
    captured: dict = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return object()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    try:
        self_update._install_windows(archive)
    finally:
        monkeypatch.undo()

    assert captured["argv"][0] == str(archive)
    assert "/VERYSILENT" in captured["argv"]
    assert "/NORESTART" in captured["argv"]


def test_prepare_signale_deja_a_jour(monkeypatch):
    class Config:
        class updates:
            include_prerelease = True

    monkeypatch.setattr(self_update, "check_for_update", lambda *a, **k: None)
    with pytest.raises(UpdateError, match="deja a jour"):
        self_update.prepare(Config())
