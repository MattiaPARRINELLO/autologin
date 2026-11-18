from __future__ import annotations

from checkmate_watcher import browser
from checkmate_watcher.browser import resolve_executable
from checkmate_watcher.config import WatcherConfig


class FakeBrowserType:
    def __init__(self, executable_path: str) -> None:
        self._executable_path = executable_path

    @property
    def executable_path(self) -> str:
        return self._executable_path


def make_config(executable_path: str | None = None):
    return type("C", (), {"watcher": WatcherConfig(executable_path=executable_path)})()


def test_la_config_a_la_priorite():
    config = make_config("/opt/chrome")
    assert resolve_executable(FakeBrowserType("/absent"), config) == "/opt/chrome"


def test_utilise_le_bundle_quand_il_existe(tmp_path):
    bundled = tmp_path / "chrome"
    bundled.write_text("")
    config = make_config()
    assert resolve_executable(FakeBrowserType(str(bundled)), config) is None


def test_bascule_sur_le_chromium_systeme(monkeypatch):
    monkeypatch.setattr(browser, "system_chromium", lambda: "/usr/bin/chromium")
    config = make_config()
    assert (
        resolve_executable(FakeBrowserType("/absent/chrome"), config)
        == "/usr/bin/chromium"
    )


def test_aucun_navigateur_disponible(monkeypatch):
    monkeypatch.setattr(browser, "system_chromium", lambda: None)
    config = make_config()
    assert resolve_executable(FakeBrowserType("/absent/chrome"), config) is None
