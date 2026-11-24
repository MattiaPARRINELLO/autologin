from __future__ import annotations

from checkmate_watcher import notifications
from checkmate_watcher.config import default_config
from checkmate_watcher.notifications import Notifier, _applescript_string, _gvariant


def test_notifier_reprend_la_configuration():
    notifier = Notifier.from_config(default_config())
    assert notifier.app_name == "CheckMate"
    assert notifier.icon == "dialog-information"


def test_gvariant_echappe_les_guillemets():
    assert _gvariant("l'emargement") == "'l\\'emargement'"
    assert _gvariant("a\\b") == "'a\\\\b'"


def test_applescript_echappe_les_guillemets():
    assert _applescript_string('a"b') == '"a\\"b"'


def _espionne_send(monkeypatch, nom="send_windows"):
    captured = {}

    def fake_send(title, message, *, app_name, **reste):
        captured.update(title=title, message=message, app_name=app_name, **reste)
        return True

    monkeypatch.setattr(notifications, nom, fake_send)
    return captured


def test_envoi_linux(monkeypatch):
    captured = _espionne_send(monkeypatch, "send_linux")
    notifier = Notifier(app_name="CheckMate", icon="info", platform="linux")
    assert notifier.send("titre", "message", urgency="normal") is True
    assert captured == {
        "title": "titre",
        "message": "message",
        "app_name": "CheckMate",
        "icon": "info",
        "urgency": "normal",
    }


def test_envoi_windows(monkeypatch):
    captured = _espionne_send(monkeypatch)
    notifier = Notifier(app_name="CheckMate", platform="win32")
    assert notifier.send("titre", "message") is True
    assert captured == {"title": "titre", "message": "message", "app_name": "CheckMate"}


def test_envoi_macos(monkeypatch):
    monkeypatch.setattr(notifications, "send_macos", lambda title, message: True)
    notifier = Notifier(platform="darwin")
    assert notifier.send("titre", "message") is True


def _fake_ask(monkeypatch, *, retour=True):
    captured = {}

    def fake_ask(text, **kwargs):
        captured.update(text=text, **kwargs)
        return retour

    monkeypatch.setattr(notifications, "ask_tkinter", fake_ask)
    return captured


def test_confirmation_windows_utilise_tkinter(monkeypatch):
    captured = _fake_ask(monkeypatch)
    notifier = Notifier(app_name="CheckMate", platform="win32")
    assert notifier.ask("present ?", timeout=42) is True
    assert captured["timeout"] == 42
    assert captured["ok_label"] == "Je suis present"


def test_confirmation_linux_bascule_sur_tkinter(monkeypatch):
    def unavailable(*args, **kwargs):
        raise notifications.DialogUnavailable("zenity introuvable")

    monkeypatch.setattr(notifications, "ask_zenity", unavailable)
    monkeypatch.setattr(notifications, "ask_tkinter", lambda *args, **kwargs: False)
    notifier = Notifier(platform="linux")
    assert notifier.ask("present ?") is False


def test_confirmation_expiree_ne_relance_pas_tkinter(monkeypatch):
    monkeypatch.setattr(notifications, "ask_zenity", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        notifications,
        "ask_tkinter",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("ne doit pas etre appele")
        ),
    )
    notifier = Notifier(platform="linux")
    assert notifier.ask("present ?", timeout=1) is None
