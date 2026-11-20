"""Icone de statut dans la zone de notification."""

from __future__ import annotations

import logging
import threading
import webbrowser

try:
    import pystray
    from PIL import Image, ImageDraw
except Exception:  # noqa: BLE001 - optionnel selon la plateforme
    pystray = None
    Image = None
    ImageDraw = None

from .status_server import StatusSession

logger = logging.getLogger(__name__)

COLORS = {
    "active": (47, 111, 79, 255),
    "outside": (154, 107, 47, 255),
    "signed": (31, 27, 22, 255),
    "error": (179, 38, 30, 255),
}


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


class TrayController:
    def __init__(self, session: StatusSession) -> None:
        self.session = session
        self.icon = None
        self._thread: threading.Thread | None = None
        self._watcher: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if pystray is None or Image is None:
            logger.info("icone de notification indisponible sur cette plateforme")
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._watcher = threading.Thread(target=self._watch, daemon=True)
        self._watcher.start()

    def _run(self) -> None:
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Ouvrir le statut", self._open_status, default=True),
                pystray.MenuItem(
                    "Reconfigurer",
                    lambda icon, item: self._safe(self.session.configure),
                ),
                pystray.MenuItem(
                    "Tester la notification",
                    lambda icon, item: self._safe(self.session.test_notification),
                ),
                pystray.MenuItem(
                    "Verifier les mises a jour",
                    lambda icon, item: self._check_update(),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quitter", self._quit),
            )
            self.icon = pystray.Icon(
                "CheckMate",
                status_image("active"),
                "CheckMate",
                menu,
            )
            self.icon.run()
        except Exception:
            logger.exception("icone de notification indisponible")

    def _open_status(self, icon=None, item=None) -> None:
        if self.session.url:
            webbrowser.open(self.session.url)

    def _safe(self, action) -> None:
        try:
            result = action()
            message = result.get("message") if isinstance(result, dict) else None
            if self.icon and message:
                self.icon.notify(message, "CheckMate")
        except Exception as exc:  # noqa: BLE001
            logger.warning("action de l'icone echouee : %s", exc)
            if self.icon:
                self.icon.notify(str(exc), "CheckMate")

    def _check_update(self) -> None:
        try:
            result = self.session.check_update()
            if self.icon:
                self.icon.notify(
                    result.get("message", "Verification terminee."), "CheckMate"
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("verification de mise a jour echouee : %s", exc)

    def _quit(self, icon=None, item=None) -> None:
        self.session.quit()
        self._stop.set()
        if self.icon:
            self.icon.stop()

    def _watch(self) -> None:
        while not self._stop.wait(60):
            if not self.icon:
                continue
            try:
                snapshot = self.session.snapshot()
                self.icon.title = f"CheckMate - {snapshot['label']}"
                self.icon.icon = status_image(snapshot["mode"])
            except Exception:
                logger.debug("mise a jour de l'icone impossible", exc_info=True)

    def stop(self) -> None:
        self._stop.set()
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                logger.debug("arret de l'icone impossible", exc_info=True)
