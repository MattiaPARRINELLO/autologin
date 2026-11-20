"""Serveur local du tableau de bord et etat partage."""

from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import sys
import threading
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import __version__
from .autostart import current_executable
from .config import Config
from .local_http import LocalError, LocalHandler
from .local_http import create_server as _create_server
from .notifications import Notifier
from .paths import data_dir, default_log_file
from .self_update import update_now
from .status_data import build_snapshot
from .status_ui import STATUS_HTML
from .updates import UpdateError, check_for_update

logger = logging.getLogger(__name__)

RUNTIME_NAME = "runtime.json"


class StatusError(LocalError):
    """Action du tableau de bord refusee."""


@dataclass(frozen=True)
class Action:
    name: str
    label: str
    method: str
    in_tray: bool = False


ACTIONS = (
    Action("configure", "Reconfigurer", "configure", in_tray=True),
    Action(
        "test-notification",
        "Tester la notification",
        "test_notification",
        in_tray=True,
    ),
    Action(
        "check-update",
        "Verifier les mises a jour",
        "check_update",
        in_tray=True,
    ),
    Action("install-update", "Installer la mise a jour", "install_update"),
    Action("open-logs", "Ouvrir les logs", "open_logs"),
    Action("quit", "Quitter", "quit"),
)
ACTIONS_BY_NAME = {action.name: action for action in ACTIONS}


def runtime_path() -> Path:
    return data_dir() / RUNTIME_NAME


def read_runtime() -> dict | None:
    path = runtime_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    required = ("pid", "port", "token", "url")
    if not all(key in data for key in required):
        return None
    return data


def write_runtime(session: StatusSession) -> None:
    path = runtime_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "port": session.port,
        "token": session.token,
        "url": session.url,
        "started_at": session.started_at.isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)


def remove_runtime() -> None:
    path = runtime_path()
    data = read_runtime()
    if data and data.get("pid") == os.getpid():
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def status_alive(runtime: dict, timeout: float = 1.5) -> bool:
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{runtime['port']}/api/status",
            headers={"X-CheckMate-Token": str(runtime["token"])},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except Exception:  # noqa: BLE001
        return False


class StatusSession:
    def __init__(
        self,
        config: Config,
        config_path: Path,
        state,
        started_at: datetime,
    ) -> None:
        self.config = config
        self.config_path = config_path
        self.state = state
        self.started_at = started_at
        self.token = secrets.token_urlsafe(24)
        self.stop_event = threading.Event()
        self.port = 0
        self.url = ""

    def snapshot(self) -> dict:
        return build_snapshot(
            self.config,
            self.state,
            self.started_at,
            self.config_path,
        )

    def test_notification(self) -> dict:
        notifier = Notifier.from_config(self.config)
        sent = notifier.send(
            "CheckMate",
            "Test de notification. Si tu ne la vois pas, coupe le mode silencieux.",
            urgency="normal",
        )
        if not sent:
            raise StatusError("notification impossible sur ce systeme")
        return {
            "ok": True,
            "message": "Notification envoyée. Si tu ne la vois pas, coupe le mode silencieux.",
        }

    def check_update(self) -> dict:
        release = check_for_update(
            __version__,
            channel=self.config.updates.channel,
        )
        if release is None:
            return {
                "ok": True,
                "available": False,
                "channel": self.config.updates.channel,
                "message": f"CheckMate {__version__} est à jour.",
            }
        return {
            "ok": True,
            "available": True,
            "channel": self.config.updates.channel,
            "version": release.version_text,
            "tag": release.tag,
            "url": release.url,
            "message": f"Mise à jour disponible : {release.tag}",
        }

    def install_update(self) -> dict:
        try:
            version = update_now(self.config)
        except UpdateError as exc:
            raise StatusError(str(exc)) from exc
        except Exception as exc:
            raise StatusError(f"mise a jour impossible : {exc}") from exc
        return {
            "ok": True,
            "version": version,
            "message": (
                f"Mise a jour {version} en cours. CheckMate redemarre dans "
                "quelques secondes."
            ),
        }

    def configure(self) -> dict:
        executable = current_executable()
        command = [
            str(executable),
            "--config",
            str(self.config_path),
            "setup",
        ]
        try:
            subprocess.Popen(command, close_fds=True)
        except OSError as exc:
            raise StatusError(f"impossible de lancer l'assistant : {exc}") from exc
        return {
            "ok": True,
            "message": (
                "L'assistant s'ouvre dans un nouvel onglet. Termine-le puis "
                "relance CheckMate pour appliquer les changements."
            ),
        }

    def open_logs(self) -> dict:
        folder = default_log_file().parent
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            raise StatusError(f"impossible d'ouvrir le dossier : {exc}") from exc
        return {"ok": True, "message": f"Dossier ouvert : {folder}"}

    def quit(self) -> dict:
        self.stop_event.set()
        return {"ok": True, "message": "CheckMate est arrêté."}

    def action(self, name: str) -> dict:
        action = ACTIONS_BY_NAME.get(name)
        if action is None:
            raise StatusError("action inconnue")
        return getattr(self, action.method)()


class _Handler(LocalHandler):
    session: StatusSession

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._serve_page(STATUS_HTML)
            return
        if path == "/favicon.ico":
            self._favicon()
            return
        if path == "/api/status":
            if not self._authorized():
                self._json(403, {"error": "acces refuse"})
                return
            self._json(200, self.session.snapshot())
            return
        self._json(404, {"error": "route inconnue"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(403, {"error": "acces refuse"})
            return
        if urlparse(self.path).path != "/api/action":
            self._json(404, {"error": "route inconnue"})
            return

        try:
            payload = self._read_json()
            result = self.session.action(str(payload.get("action") or ""))
        except LocalError as exc:
            self._json(exc.status, {"error": str(exc)})
            return
        except Exception as exc:
            logger.exception("erreur dans le tableau de bord")
            self._json(500, {"error": f"erreur interne : {exc}"})
            return

        self._json(200, result)


def create_server(session: StatusSession) -> ThreadingHTTPServer:
    return _create_server(session, _Handler)


def start_status_server(session: StatusSession) -> ThreadingHTTPServer:
    server = create_server(session)
    session.port = server.server_address[1]
    session.url = f"http://127.0.0.1:{session.port}/?token={session.token}"
    write_runtime(session)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("tableau de bord disponible sur %s", session.url)
    return server


def stop_status_server(server: ThreadingHTTPServer) -> None:
    try:
        server.shutdown()
        server.server_close()
    finally:
        remove_runtime()
