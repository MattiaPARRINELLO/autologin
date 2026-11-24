"""Fenetre native optionnelle, sans navigateur.

Utilise pywebview, qui s'appuie sur WebView2 sous Windows. Si le moteur web
n'est pas disponible (pywebview absent, WebView2 manquant, Linux sans GTK),
on retombe sur le navigateur pour ne jamais bloquer l'utilisateur.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import threading
import webbrowser
from typing import Any

logger = logging.getLogger(__name__)

TITLE = "CheckMate"
WIDTH = 1000
HEIGHT = 880
MIN_SIZE = (720, 620)

# Variable d'environnement pour forcer le navigateur.
BROWSER_ENV = "CHECKMATE_BROWSER"


def _require(namespace: str, versions: tuple[str, ...]) -> bool:
    """Verifie qu'une version d'un namespace GObject est disponible."""
    import gi

    for version in versions:
        try:
            gi.require_version(namespace, version)
        except ValueError:
            continue
        return True
    return False


def _linux_ready() -> bool:
    """Verifie GTK 3 et WebKit2, les deux moteurs du backend pywebview."""
    try:
        import gi
    except Exception:  # PyGObject absent
        return False
    return _require("Gtk", ("3.0",)) and _require("WebKit2", ("4.1", "4.0"))


def _platform_ready() -> bool:
    """Verifie qu'un moteur web de bureau existe pour cette plateforme."""
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return True
    if importlib.util.find_spec("gi") is not None:
        return _linux_ready()
    return any(
        importlib.util.find_spec(name) is not None
        for name in ("qtpy", "PyQt6", "PyQt5", "PySide6")
    )


def _load_backend() -> Any | None:
    if not _platform_ready():
        logger.debug("aucun moteur web de bureau disponible")
        return None
    try:
        import webview
    except Exception:
        logger.debug("pywebview indisponible", exc_info=True)
        return None
    return webview


def show(url: str, *, close_event: threading.Event | None = None) -> bool:
    """Ouvre une fenetre native et bloque jusqu'a sa fermeture.

    Rend True si la fenetre a ete ouverte, False si le moteur web est
    indisponible. Si ``close_event`` est fourni, la fenetre se ferme d'elle-meme
    quand l'evenement est arme.
    """
    backend = _load_backend()
    if backend is None:
        return False

    try:
        window = backend.create_window(
            TITLE,
            url,
            width=WIDTH,
            height=HEIGHT,
            min_size=MIN_SIZE,
        )
        if close_event is not None:
            threading.Thread(
                target=_close_when_done,
                args=(window, close_event),
                daemon=True,
            ).start()
        options: dict[str, Any] = {}
        if sys.platform.startswith("linux"):
            # Force GTK : evite la sonde Qt de pywebview et ses traces au demarrage.
            options["gui"] = "gtk"
        backend.start(**options)
    except Exception as error:  # moteur web absent ou casse
        logger.info("fenetre native indisponible : %s", error)
        return False
    return True


def _close_when_done(window: Any, close_event: threading.Event) -> None:
    close_event.wait()
    try:
        window.destroy()
    except Exception:
        logger.debug("fermeture de la fenetre impossible", exc_info=True)


def open_url(url: str, *, close_event: threading.Event | None = None) -> bool:
    """Ouvre l'URL dans une fenetre native, sinon dans le navigateur.

    Rend True si une fenetre native a ete utilisee.
    """
    if os.environ.get(BROWSER_ENV) != "1" and show(url, close_event=close_event):
        return True
    webbrowser.open(url)
    return False
