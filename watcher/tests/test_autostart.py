from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from checkmate_watcher import autostart
from checkmate_watcher.autostart import (
    _linux_unit,
    autostart_enabled,
    current_executable,
    disable_autostart,
    enable_autostart,
)


def ok_result():
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_unite_systemd_generee():
    unit = _linux_unit(
        Path("/opt/check mate/checkmate-watcher"),
        Path("/home/eleve/.config/checkmate-watcher/config.toml"),
    )
    assert 'ExecStart="/opt/check mate/checkmate-watcher"' in unit
    assert "--config /home/eleve/.config/checkmate-watcher/config.toml run" in unit
    assert "EnvironmentFile=-%h/.config/checkmate-watcher/env" in unit
    assert "Restart=always" in unit
    assert "WantedBy=graphical-session.target" in unit


def test_activation_windows(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(
        autostart.shutil, "which", lambda name: "C:\\Windows\\schtasks.exe"
    )
    monkeypatch.setattr(
        autostart,
        "_run",
        lambda command, timeout=30: calls.append(command) or ok_result(),
    )

    assert enable_autostart(
        Path("C:\\Program Files\\CheckMate\\CheckMate.exe"),
        Path("C:\\Users\\eleve\\AppData\\Roaming\\checkmate-watcher\\config.toml"),
    )
    command = calls[-1]
    assert command[0].endswith("schtasks.exe")
    assert "/Create" in command and "/F" in command
    assert "ONLOGON" in command
    assert any("CheckMate.exe" in part for part in command)
    assert any("config.toml" in part for part in command)


def test_desactivation_windows(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(autostart.shutil, "which", lambda name: "schtasks")
    monkeypatch.setattr(
        autostart,
        "_run",
        lambda command, timeout=30: calls.append(command) or ok_result(),
    )
    assert disable_autostart()
    assert calls[-1][1:4] == ["/Delete", "/F", "/TN"]
    assert calls[-1][-1] == "CheckMate"


def test_etat_windows(monkeypatch):
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(autostart.shutil, "which", lambda name: "schtasks")
    monkeypatch.setattr(autostart, "_run", lambda command, timeout=30: ok_result())
    assert autostart_enabled()


def test_dispatch_linux(monkeypatch):
    called = {}
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(
        autostart,
        "_enable_linux",
        lambda executable, config: called.update(path=config) or True,
    )
    assert enable_autostart(Path("/x"), Path("/config.toml"))
    assert called["path"] == Path("/config.toml")


def test_commande_courante(monkeypatch):
    monkeypatch.setattr(
        autostart,
        "sys",
        SimpleNamespace(platform="linux", argv=["/opt/checkmate/checkmate-watcher"]),
    )
    assert current_executable() == Path("/opt/checkmate/checkmate-watcher")
