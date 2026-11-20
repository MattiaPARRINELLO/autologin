from __future__ import annotations

import threading

import pytest

from checkmate_watcher import window


class FakeWindow:
    def __init__(self) -> None:
        self.destroyed = threading.Event()

    def destroy(self) -> None:
        self.destroyed.set()


class FakeBackend:
    def __init__(self, *, start_error: Exception | None = None) -> None:
        self.windows: list[dict] = []
        self.started = 0
        self.start_error = start_error

    def create_window(self, title: str, url: str, **options) -> FakeWindow:
        handle = FakeWindow()
        self.windows.append(
            {"title": title, "url": url, "options": options, "handle": handle}
        )
        return handle

    def start(self) -> None:
        self.started += 1
        if self.start_error is not None:
            raise self.start_error


def test_fenetre_native_absente(monkeypatch):
    monkeypatch.setattr(window, "_load_backend", lambda: None)
    assert window.available() is False
    assert window.show("http://127.0.0.1:8080/?token=x") is False


def test_fenetre_native_ouverte(monkeypatch):
    backend = FakeBackend()
    monkeypatch.setattr(window, "_load_backend", lambda: backend)
    assert window.available() is True
    assert window.show("http://127.0.0.1:8080/?token=x") is True
    assert backend.started == 1
    opened = backend.windows[0]
    assert opened["title"] == "CheckMate"
    assert opened["url"].endswith("token=x")


def test_repli_si_le_moteur_echoue(monkeypatch):
    backend = FakeBackend(start_error=RuntimeError("WebView2 absent"))
    monkeypatch.setattr(window, "_load_backend", lambda: backend)
    assert window.show("http://127.0.0.1:8080/?token=x") is False


def test_repli_navigateur(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(window, "_load_backend", lambda: None)
    monkeypatch.setattr(window.webbrowser, "open", opened.append)
    assert window.open_url("http://127.0.0.1:8080/?token=x") is False
    assert opened == ["http://127.0.0.1:8080/?token=x"]


def test_navigateur_force(monkeypatch):
    backend = FakeBackend()
    opened: list[str] = []
    monkeypatch.setattr(window, "_load_backend", lambda: backend)
    monkeypatch.setattr(window.webbrowser, "open", opened.append)
    monkeypatch.setenv(window.BROWSER_ENV, "1")
    assert window.open_url("http://127.0.0.1:8080/") is False
    assert backend.started == 0
    assert opened == ["http://127.0.0.1:8080/"]


def test_fermeture_automatique():
    handle = FakeWindow()
    done = threading.Event()
    done.set()
    window._close_when_done(handle, done)
    assert handle.destroyed.is_set()


def test_fermeture_ignore_les_erreurs():
    class Broken(FakeWindow):
        def destroy(self) -> None:
            raise RuntimeError("fenetre deja fermee")

    done = threading.Event()
    done.set()
    window._close_when_done(Broken(), done)


def test_backend_reel_disponible():
    pytest.importorskip("webview")
    if not window._platform_ready():
        pytest.skip("aucun moteur web de bureau sur cette machine")
    assert window.available() is True


def test_plateforme_sans_moteur_web(monkeypatch):
    monkeypatch.setattr(window, "_platform_ready", lambda: False)
    assert window._load_backend() is None
