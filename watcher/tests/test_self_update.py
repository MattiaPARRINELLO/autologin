from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from checkmate_watcher import self_update
from checkmate_watcher.updates import UpdateError


def test_install_refuse_une_archive_absente(tmp_path):
    with pytest.raises(UpdateError):
        self_update.install(tmp_path / "absent.tar.gz")


def _archive(tmp_path, nom="CheckMate-linux-0.4.2.tar.gz") -> Path:
    archive = tmp_path / nom
    archive.write_bytes(b"x")
    return archive


def _capturer_popen(
    monkeypatch, *, unite_active=True, which="/usr/bin/systemd-run"
) -> list:
    appels: list = []

    def fake_popen(argv, **kwargs):
        appels.append((argv, kwargs))
        return object()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(self_update.shutil, "which", lambda _nom: which)
    monkeypatch.setattr(self_update, "_transient_unit_active", lambda _u: unite_active)
    return appels


def test_script_linux_echappe_les_chemins(tmp_path, monkeypatch):
    archive = _archive(tmp_path, nom="CheckMate linux-0.4.2.tar.gz")
    appels = _capturer_popen(monkeypatch, which=None)
    self_update._install_linux(archive, archive.parent)
    script = Path(appels[0][0][1]).read_text(encoding="utf-8")
    assert "'" + str(archive) + "'" in script
    assert "tar -xzf" in script
    assert "systemctl --user stop checkmate-watcher.service" in script
    assert "CHECKMATE_UPDATE_DETACHED" in script
    assert "systemctl --user start checkmate-watcher.service" in script
    assert appels[0][1]["start_new_session"] is True


def test_installation_linux_passe_par_une_unite_systemd(tmp_path, monkeypatch):
    archive = _archive(tmp_path)
    calls = _capturer_popen(monkeypatch)
    self_update._install_linux(archive, archive.parent)
    assert len(calls) == 1
    argv = calls[0][0]
    assert argv[0] == "/usr/bin/systemd-run"
    assert any(arg.startswith("--unit=") for arg in argv)
    assert "--setenv=CHECKMATE_UPDATE_DETACHED=1" in argv
    assert argv[-2:] == ["/bin/bash", argv[-1]]


def test_installation_linux_replie_si_unite_inactive(tmp_path, monkeypatch):
    archive = _archive(tmp_path)
    calls = _capturer_popen(
        monkeypatch, unite_active=False, which="/usr/bin/systemd-run"
    )
    self_update._install_linux(archive, archive.parent)
    assert len(calls) == 2
    assert calls[1][0][0] == "/bin/bash"
    assert calls[1][1]["start_new_session"] is True


def test_install_windows_utilise_les_options_silencieuses(tmp_path, monkeypatch):
    archive = tmp_path / "CheckMate-Setup.exe"
    archive.write_bytes(b"x")
    calls = _capturer_popen(monkeypatch)
    self_update._install_windows(archive)
    argv = calls[0][0]
    assert argv[0] == str(archive)
    assert "/VERYSILENT" in argv
    assert "/NORESTART" in argv


def test_prepare_signale_deja_a_jour(monkeypatch):
    class Config:
        class updates:
            channel = "beta"

    monkeypatch.setattr(self_update, "check_for_update", lambda *a, **k: None)
    with pytest.raises(UpdateError, match="deja a jour"):
        self_update.prepare(Config())
