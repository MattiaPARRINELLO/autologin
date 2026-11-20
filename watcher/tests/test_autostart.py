from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from checkmate_watcher import autostart
from checkmate_watcher.autostart import (
    RUN_KEY,
    RUN_VALUE,
    _linux_unit,
    autostart_enabled,
    current_executable,
    disable_autostart,
    enable_autostart,
)


@pytest.mark.skipif(sys.platform == "win32", reason="unite systemd Linux")
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


class FakeKey:
    def __init__(self, store: dict, path: str) -> None:
        self.store = store
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeWinreg:
    HKEY_CURRENT_USER = object()
    KEY_SET_VALUE = 1
    KEY_READ = 2
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def OpenKey(self, root, path, reserved=0, access=0):
        return FakeKey(self.values, path)

    def SetValueEx(self, key, name, reserved, value_type, value):
        key.store[(key.path, name)] = value

    def QueryValueEx(self, key, name):
        try:
            value = key.store[(key.path, name)]
        except KeyError as exc:
            raise FileNotFoundError(name) from exc
        return value, self.REG_SZ

    def DeleteValue(self, key, name):
        try:
            del key.store[(key.path, name)]
        except KeyError as exc:
            raise FileNotFoundError(name) from exc


def windows_env(monkeypatch):
    fake = FakeWinreg()
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(autostart, "_winreg", lambda: fake)
    monkeypatch.setattr(autostart, "_remove_legacy_windows_task", lambda: None)
    return fake


def test_activation_windows(monkeypatch):
    fake = windows_env(monkeypatch)
    assert enable_autostart(
        Path("C:\\Program Files\\CheckMate\\CheckMate.exe"),
        Path("C:\\Users\\eleve\\AppData\\Roaming\\checkmate-watcher\\config.toml"),
    )
    value = fake.values[(RUN_KEY, RUN_VALUE)]
    assert "CheckMate.exe" in value
    assert "--config" in value
    assert "config.toml" in value
    assert autostart_enabled() is True


def test_desactivation_windows(monkeypatch):
    fake = windows_env(monkeypatch)
    enable_autostart(Path("C:\\CheckMate.exe"), Path("C:\\config.toml"))
    assert disable_autostart() is True
    assert (RUN_KEY, RUN_VALUE) not in fake.values
    assert autostart_enabled() is False


def test_etat_windows_sans_valeur(monkeypatch):
    windows_env(monkeypatch)
    assert autostart_enabled() is False


def test_redemarrage_windows_ne_fait_rien(monkeypatch):
    monkeypatch.setattr(autostart, "sys", SimpleNamespace(platform="win32"))
    assert autostart.restart_autostart() is True


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


def test_commande_courante(monkeypatch, tmp_path):
    candidate = tmp_path / "checkmate-watcher"
    monkeypatch.setattr(
        autostart,
        "sys",
        SimpleNamespace(platform="linux", argv=[str(candidate)]),
    )
    assert current_executable() == candidate.resolve()
