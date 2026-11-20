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


def test_envoi_linux(monkeypatch):
    captured = {}

    def fake_send(title, message, *, app_name, icon, urgency):
        captured.update(
            title=title,
            message=message,
            app_name=app_name,
            icon=icon,
            urgency=urgency,
        )
        return True

    monkeypatch.setattr(notifications, "send_linux", fake_send)
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
    captured = {}
    monkeypatch.setattr(
        notifications,
        "send_windows",
        lambda title, message, *, app_name: (
            captured.update(title=title, message=message, app_name=app_name) or True
        ),
    )
    notifier = Notifier(app_name="CheckMate", platform="win32")
    assert notifier.send("titre", "message") is True
    assert captured == {"title": "titre", "message": "message", "app_name": "CheckMate"}


def test_envoi_macos(monkeypatch):
    monkeypatch.setattr(notifications, "send_macos", lambda title, message: True)
    notifier = Notifier(platform="darwin")
    assert notifier.send("titre", "message") is True


def test_confirmation_windows_utilise_tkinter(monkeypatch):
    captured = {}

    def fake_ask(text, *, timeout, title, ok_label, cancel_label):
        captured.update(
            text=text,
            timeout=timeout,
            title=title,
            ok_label=ok_label,
            cancel_label=cancel_label,
        )
        return True

    monkeypatch.setattr(notifications, "ask_tkinter", fake_ask)
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
