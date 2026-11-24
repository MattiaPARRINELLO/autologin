from __future__ import annotations

from checkmate_watcher.browser import (
    LaunchOptions,
    bundled_browser_present,
    bundled_chromium_path,
    platform_channel,
    resolve_launch_options,
)


class FakeBrowserType:
    def __init__(self, executable_path: str) -> None:
        self._executable_path = executable_path

    @property
    def executable_path(self) -> str:
        return self._executable_path


def test_la_config_a_la_priorite():
    options = resolve_launch_options(
        FakeBrowserType("/absent"), "/opt/chrome", platform="linux"
    )
    assert options == LaunchOptions(executable_path="/opt/chrome")


def test_utilise_le_bundle_quand_il_existe(tmp_path):
    bundled = tmp_path / "chrome"
    bundled.write_text("")
    options = resolve_launch_options(FakeBrowserType(str(bundled)), platform="linux")
    assert options == LaunchOptions()


def test_bascule_sur_le_chromium_systeme(monkeypatch):
    monkeypatch.setattr(
        "checkmate_watcher.browser.system_chromium", lambda: "/usr/bin/chromium"
    )
    options = resolve_launch_options(
        FakeBrowserType("/absent/chrome"), platform="linux"
    )
    assert options == LaunchOptions(executable_path="/usr/bin/chromium")


def test_aucun_navigateur_disponible(monkeypatch):
    monkeypatch.setattr("checkmate_watcher.browser.system_chromium", lambda: None)
    options = resolve_launch_options(
        FakeBrowserType("/absent/chrome"), platform="linux"
    )
    assert options == LaunchOptions()


def test_bundled_chromium_path_trouve_le_binaire(tmp_path):
    binary = tmp_path / "chromium-1234" / "chrome-linux" / "chrome"
    binary.parent.mkdir(parents=True)
    binary.write_text("")
    assert bundled_chromium_path("linux", tmp_path) == str(binary)
    assert bundled_browser_present("linux", tmp_path) is True


def test_bundled_chromium_path_absent(tmp_path):
    assert bundled_chromium_path("linux", tmp_path) is None
    assert bundled_browser_present("linux", tmp_path) is False


def test_windows_choisit_edge_ou_chrome():
    assert platform_channel("win32", lambda path: "Edge" in str(path)) == "msedge"
    assert platform_channel("win32", lambda path: "Chrome" in str(path)) == "chrome"
    assert platform_channel("win32", lambda path: False) is None


def test_macos_choisit_chrome():
    assert (
        platform_channel("darwin", lambda path: "Google Chrome" in str(path))
        == "chrome"
    )
    assert platform_channel("darwin", lambda path: False) is None


def test_launch_options_kwargs():
    assert LaunchOptions().as_kwargs() == {}
    assert LaunchOptions(channel="msedge").as_kwargs() == {"channel": "msedge"}
    assert LaunchOptions(executable_path="/x").as_kwargs() == {"executable_path": "/x"}
