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
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import BUILD, __version__
from .autostart import current_executable
from .config import Config
from .notifications import Notifier
from .paths import data_dir, default_log_file
from .status_data import build_snapshot
from .status_ui import STATUS_HTML
from .updates import check_for_update

logger = logging.getLogger(__name__)

MAX_BODY = 100_000
RUNTIME_NAME = "runtime.json"


class StatusError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


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
        notifier = Notifier(
            app_name=self.config.notifications.app_name,
            icon=self.config.notifications.icon,
        )
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
            include_prerelease=self.config.updates.include_prerelease,
        )
        if release is None:
            return {
                "ok": True,
                "available": False,
                "message": f"CheckMate {__version__} est à jour.",
            }
        return {
            "ok": True,
            "available": True,
            "version": release.version_text,
            "tag": release.tag,
            "url": release.url,
            "message": f"Mise à jour disponible : {release.tag}",
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


class _Handler(BaseHTTPRequestHandler):
    session: StatusSession

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, data: dict) -> None:
        self._send(
            status,
            json.dumps(data, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _authorized(self) -> bool:
        return self.headers.get("X-CheckMate-Token") == self.session.token

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StatusError("corps JSON invalide") from exc
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            token = (parse_qs(parsed.query).get("token") or [""])[0]
            if token != self.session.token:
                self._send(403, b"Jeton invalide", "text/plain; charset=utf-8")
                return
            html = STATUS_HTML.replace("__TOKEN__", self.session.token).replace(
                "__VERSION__", f"{__version__} - build {BUILD}"
            )
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if parsed.path == "/api/status":
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
        path = urlparse(self.path).path
        if path != "/api/action":
            self._json(404, {"error": "route inconnue"})
            return

        action = ""
        try:
            payload = self._read_json()
            action = str(payload.get("action") or "")
            if action == "configure":
                result = self.session.configure()
            elif action == "test-notification":
                result = self.session.test_notification()
            elif action == "check-update":
                result = self.session.check_update()
            elif action == "open-logs":
                result = self.session.open_logs()
            elif action == "quit":
                result = self.session.quit()
            else:
                raise StatusError("action inconnue")
        except StatusError as exc:
            self._json(exc.status, {"error": str(exc)})
            return
        except Exception as exc:
            logger.exception("erreur dans le tableau de bord")
            self._json(500, {"error": f"erreur interne : {exc}"})
            return

        self._json(200, result)
        if action == "quit":
            # La reponse est envoyee ; la boucle verra l'evenement et fermera tout.
            self.session.stop_event.set()


def create_server(session: StatusSession) -> ThreadingHTTPServer:
    handler = type("StatusHandler", (_Handler,), {"session": session})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    return server


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
