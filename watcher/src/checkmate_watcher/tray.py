"""Icone de statut dans la zone de notification."""

from __future__ import annotations

import logging
import os
import threading

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:  # noqa: BLE001 - optionnel selon la plateforme
    pystray = None
    Image = None
    ImageDraw = None

from . import sni
from .status_server import ACTIONS, StatusSession
from .window import open_url

logger = logging.getLogger(__name__)

COLORS = {
    "active": (47, 111, 79, 255),
    "outside": (154, 107, 47, 255),
    "signed": (31, 27, 22, 255),
    "error": (179, 38, 30, 255),
}

TRAY_ENV = "CHECKMATE_TRAY"


def status_image(mode: str):
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (4, 4, 60, 60), radius=16, fill=COLORS.get(mode, COLORS["active"])
    )
    draw.line(
        [(18, 33), (28, 43), (46, 21)],
        fill=(247, 244, 238, 255),
        width=6,
        joint="curve",
    )
    return image


def status_pixmaps(mode: str) -> list:
    return sni.pixmaps(status_image(mode))


def status_level(mode: str) -> str:
    return "NeedsAttention" if mode == "error" else "Active"


def menu_handler(action):
    """Adapte une action sans argument au callback attendu par pystray.

    pystray inspecte le nombre d'arguments du callback : zero, un ou deux.
    Trois arguments, meme avec une valeur par defaut, levent une ValueError.
    """

    def handler(icon, item):
        action()

    return handler


class TrayController:
    def __init__(self, session: StatusSession) -> None:
        self.session = session
        self.icon = None
        self.sni: sni.SniTray | None = None
        self._thread: threading.Thread | None = None
        self._watcher: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._start_sni():
            self._start_watcher()
            return
        if pystray is None or Image is None:
            logger.info("icone de notification indisponible sur cette plateforme")
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._start_watcher()

    def _start_watcher(self) -> None:
        self._watcher = threading.Thread(target=self._watch, daemon=True)
        self._watcher.start()

    def _start_sni(self) -> bool:
        backend = os.environ.get(TRAY_ENV, "").lower()
        if backend == "xorg" or not sni.available():
            return False
        tray = sni.SniTray(self._menu_items(), activate=self._open_status)
        if not tray.start():
            logger.info("repli sur l'icone XEmbed")
            return False
        self.sni = tray
        tray.update("CheckMate", status_pixmaps("active"), "Active", "")
        return True

    def _menu_items(self) -> list:
        return [
            ("Ouvrir le statut", self._open_status),
            *[
                (action.label, self._action(action.name))
                for action in ACTIONS
                if action.in_tray
            ],
            None,
            ("Quitter", self._quit),
        ]

    def _run(self) -> None:
        try:
            items = []
            for entry in self._menu_items():
                if entry is None:
                    items.append(pystray.Menu.SEPARATOR)
                    continue
                label, action = entry
                items.append(
                    pystray.MenuItem(
                        label,
                        menu_handler(action),
                        default=label == "Ouvrir le statut",
                    )
                )
            self.icon = pystray.Icon(
                "CheckMate",
                status_image("active"),
                "CheckMate",
                pystray.Menu(*items),
            )
            self.icon.run()
        except Exception:
            logger.exception("icone de notification indisponible")

    def _open_status(self) -> None:
        if self.session.url:
            open_url(self.session.url)

    def _action(self, name: str):
        return lambda: self._safe(lambda: self.session.action(name))

    def _safe(self, action) -> None:
        try:
            result = action()
            message = result.get("message") if isinstance(result, dict) else None
            if message:
                self._notify(message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("action de l'icone echouee : %s", exc)
            self._notify(str(exc))

    def _notify(self, message: str) -> None:
        if self.sni is not None:
            logger.info("%s", message)
            return
        if self.icon is not None:
            self.icon.notify(message, "CheckMate")

    def _quit(self, icon=None, item=None) -> None:
        self._stop.set()
        if self.sni is not None:
            self.sni.stop()
            self.sni = None
        self.session.quit()
        if self.icon:
            self.icon.stop()

    def _watch(self) -> None:
        while not self._stop.is_set():
            self._refresh_icon()
            self._stop.wait(60)

    def _refresh_icon(self) -> None:
        try:
            snapshot = self.session.snapshot()
        except Exception:
            logger.debug("lecture du statut impossible", exc_info=True)
            return
        label = snapshot.get("label", "")
        mode = snapshot.get("mode", "active")
        title = f"CheckMate - {label}" if label else "CheckMate"
        if self.sni is not None:
            try:
                self.sni.update(title, status_pixmaps(mode), status_level(mode), label)
            except Exception:
                logger.debug("mise a jour de l'icone impossible", exc_info=True)
        elif self.icon is not None:
            try:
                self.icon.title = title
                self.icon.icon = status_image(mode)
            except Exception:
                logger.debug("mise a jour de l'icone impossible", exc_info=True)

    def stop(self) -> None:
        self._stop.set()
        if self.sni is not None:
            try:
                self.sni.stop()
            except Exception:
                logger.debug("arret de l'icone impossible", exc_info=True)
            self.sni = None
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                logger.debug("arret de l'icone impossible", exc_info=True)
