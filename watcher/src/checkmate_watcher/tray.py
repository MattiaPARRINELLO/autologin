"""Icone de statut dans la zone de notification."""

from __future__ import annotations

import logging
import os
import threading

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:  # optionnel selon la plateforme
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
    "blocked": (179, 38, 30, 255),
}

TRAY_ENV = "CHECKMATE_TRAY"

# Assez court pour que l'icone repasse au vert des la reprise, assez long
# pour ne pas reveiller l'interface de bureau inutilement.
REFRESH_SECONDS = 10


def _canvas():
    return Image.new("RGBA", (64, 64), (0, 0, 0, 0))


def _draw_rounded_rectangle(draw, mode: str) -> None:
    draw.rounded_rectangle(
        (4, 4, 60, 60), radius=16, fill=COLORS.get(mode, COLORS["active"])
    )


def _draw_check(draw) -> None:
    draw.line(
        [(18, 33), (28, 43), (46, 21)],
        fill=(247, 244, 238, 255),
        width=6,
        joint="curve",
    )


def status_image(mode: str):
    image = _canvas()
    draw = ImageDraw.Draw(image)
    _draw_rounded_rectangle(draw, mode)
    _draw_check(draw)
    return image


def status_pixmaps(mode: str) -> list:
    return sni.pixmaps(status_image(mode))


def status_level(mode: str) -> str:
    return "NeedsAttention" if mode in {"error", "blocked"} else "Active"


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
        self._shown: tuple[str, str] | None = None

    def _start_xembed(self) -> bool:
        if pystray is None or Image is None:
            logger.info(
                "icone de notification indisponible sur cette plateforme"
            )
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def start(self) -> None:
        if self._start_sni():
            self._start_watcher()
            return
        if self._start_xembed():
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
            items = self._build_menu_items()
            self.icon = self._create_icon(items)
            self.icon.run()
        except Exception:
            logger.exception("icone de notification indisponible")

    def _build_menu_items(self) -> list:
        return [self._menu_item(entry) for entry in self._menu_items()]

    def _menu_item(self, entry):
        if entry is None:
            return pystray.Menu.SEPARATOR
        label, action = entry
        return pystray.MenuItem(
            label,
            menu_handler(action),
            default=label == "Ouvrir le statut",
        )

    def _create_icon(self, items: list):
        return pystray.Icon(
            "CheckMate",
            status_image("active"),
            "CheckMate",
            pystray.Menu(*items),
        )

    def _open_status(self) -> None:
        if self.session.url:
            open_url(self.session.url)

    def _action(self, name: str):
        return lambda: self._safe(lambda: self.session.action(name))

    def _safe(self, action) -> None:
        try:
            result = action()
            message = (
                result.get("message") if isinstance(result, dict) else None
            )
            if message:
                self._notify(message)
        except Exception as exc:
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
            self._stop.wait(REFRESH_SECONDS)

    def _snapshot(self) -> dict | None:
        try:
            return self.session.snapshot()
        except Exception:
            logger.debug("lecture du statut impossible", exc_info=True)
            return None

    @staticmethod
    def _icon_title(label: str) -> str:
        return f"CheckMate - {label}" if label else "CheckMate"

    def _refresh_sni(self, title: str, mode: str, label: str) -> bool:
        try:
            self.sni.update(
                title, status_pixmaps(mode), status_level(mode), label
            )
            self._shown = (mode, label)
            return True
        except Exception:
            logger.debug("mise a jour de l'icone impossible", exc_info=True)
            return False

    def _refresh_xembed(self, title: str, mode: str, label: str) -> bool:
        try:
            self.icon.title = title
            self.icon.icon = status_image(mode)
            self._shown = (mode, label)
            return True
        except Exception:
            logger.debug("mise a jour de l'icone impossible", exc_info=True)
            return False

    def _refresh_target(self, title: str, mode: str, label: str) -> None:
        if self.sni is not None:
            self._refresh_sni(title, mode, label)
        elif self.icon is not None:
            self._refresh_xembed(title, mode, label)

    def _refresh_icon(self) -> None:
        snapshot = self._snapshot()
        if snapshot is None:
            return
        mode, label = snapshot.get("mode", "active"), snapshot.get("label", "")
        if (mode, label) == self._shown:
            return
        title = self._icon_title(label)
        self._refresh_target(title, mode, label)

    def stop(self) -> None:
        self._stop.set()
        self._stop_sni()
        self._stop_icon()

    def _stop_sni(self) -> None:
        if self.sni is None:
            return
        try:
            self.sni.stop()
        except Exception:
            logger.debug("arret de l'icone impossible", exc_info=True)
        self.sni = None

    def _stop_icon(self) -> None:
        if not self.icon:
            return
        try:
            self.icon.stop()
        except Exception:
            logger.debug("arret de l'icone impossible", exc_info=True)
