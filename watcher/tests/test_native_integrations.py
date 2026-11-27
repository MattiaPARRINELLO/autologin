"""Passerelle vers les integrations natives : delegation et repli."""

from __future__ import annotations

from pathlib import Path

from checkmate_watcher import native_integrations


class FakeProcess:
    def __init__(self, code: int | None) -> None:
        self.code = code
        self.pid = 4242
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.code

    def terminate(self) -> None:
        self.terminated = True
        self.code = 0

    def kill(self) -> None:
        self.killed = True
        self.code = -9

    def wait(self, timeout=None):
        return self.code


class FakeResult:
    def __init__(self, code: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = code
        self.stdout = stdout
        self.stderr = stderr


def test_start_tray_garde_un_processus_vivant(monkeypatch):
    process = FakeProcess(None)
    monkeypatch.setattr(
        native_integrations.native_ui, "spawn", lambda *args: process
    )
    monkeypatch.setattr(native_integrations.time, "sleep", lambda _: None)
    assert native_integrations.start_tray() is process


def test_start_tray_replie_si_le_binaire_meurt(monkeypatch):
    monkeypatch.setattr(
        native_integrations.native_ui,
        "spawn",
        lambda *args: FakeProcess(3),
    )
    monkeypatch.setattr(native_integrations.time, "sleep", lambda _: None)
    assert native_integrations.start_tray() is None


def test_notification_transmet_titre_corps_et_identifiant(monkeypatch):
    captured = {}

    def spawn(*args):
        captured["args"] = args
        return FakeProcess(0)

    monkeypatch.setattr(native_integrations.native_ui, "spawn", spawn)
    monkeypatch.setattr(native_integrations.time, "sleep", lambda _: None)
    assert native_integrations.notify("CheckMate", "Test") is True
    args = captured["args"]
    assert args[0] == "notify"
    assert "--replace-id" in args
    assert args[args.index("--body") + 1] == "Test"


def test_notification_indisponible_laisse_le_repli_python(monkeypatch):
    monkeypatch.setattr(
        native_integrations.native_ui,
        "spawn",
        lambda *args: FakeProcess(3),
    )
    monkeypatch.setattr(native_integrations.time, "sleep", lambda _: None)
    assert native_integrations.notify("CheckMate", "Test") is None


def test_autostart_active_avec_les_chemins(monkeypatch):
    captured = {}

    def run(*args, timeout=30):
        captured["args"] = args
        return FakeResult(0, "installed\n")

    monkeypatch.setattr(native_integrations.native_ui, "run", run)
    executable = Path("/opt/checkmate/checkmate-watcher")
    config = Path("/home/test/.config/checkmate-watcher/config.toml")
    assert native_integrations.autostart("enable", executable, config) is True
    assert captured["args"] == (
        "autostart",
        "enable",
        "--executable",
        str(executable),
        "--config",
        str(config),
    )


def test_autostart_etat_lu_dans_la_sortie(monkeypatch):
    monkeypatch.setattr(
        native_integrations.native_ui,
        "run",
        lambda *args, **kwargs: FakeResult(0, "enabled\n"),
    )
    assert native_integrations.autostart_enabled() is True


def test_autostart_echec_laisse_le_repli_python(monkeypatch):
    monkeypatch.setattr(
        native_integrations.native_ui,
        "run",
        lambda *args, **kwargs: FakeResult(1, stderr="systemctl introuvable"),
    )
    assert native_integrations.autostart("disable") is None
