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
from .config import Config, save_updates_channel
from .file_io import write_private_json
from .local_http import LocalError, LocalHandler
from .local_http import create_server as _create_server
from .notifications import Notifier
from .paths import data_dir, default_log_file
from .release_notes import (
    CELEBRATED_VERSION_KEY,
    dismiss_release_celebration,
)
from .self_update import update_now
from .status_data import build_snapshot
from .status_ui import STATUS_HTML
from .updates import (
    BETA_CHANNEL,
    STABLE_CHANNEL,
    UpdateError,
    check_for_update,
)

logger = logging.getLogger(__name__)

RUNTIME_NAME = "runtime.json"
BETA_MESSAGE = (
    "Canal beta active. Les mises a jour arrivent souvent et la "
    "stabilite du projet n'est pas garantie."
)
BETA_ON_STABLE_MESSAGE = (
    "Canal stable active. Tu restes sur cette version beta : les "
    "prochaines betas ne seront plus proposees, et la prochaine "
    "version stable te sera proposee."
)
STABLE_MESSAGE = "Canal stable active : mises a jour moins frequentes."


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
    Action("dismiss-release", "Fermer les nouveautes", "dismiss_release"),
    Action("open-logs", "Ouvrir les logs", "open_logs"),
    Action("set-channel", "Changer de canal", "set_channel"),
    Action("quit", "Quitter", "quit"),
)
ACTIONS_BY_NAME = {action.name: action for action in ACTIONS}


def _channel_message(channel: str) -> str:
    if channel == BETA_CHANNEL:
        return BETA_MESSAGE
    if "-beta" in __version__:
        return BETA_ON_STABLE_MESSAGE
    return STABLE_MESSAGE


def _update_payload(release, reason) -> dict:
    return {
        "tag": release.tag,
        "version": release.version_text,
        "reason": reason,
    }


def _blocked_payload(release) -> dict:
    return _update_payload(release, release.required_reason)


def _migration_payload(release) -> dict:
    return _update_payload(release, release.migration_reason)


def runtime_path() -> Path:
    return data_dir() / RUNTIME_NAME


def _read_runtime_file(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _has_required_runtime_keys(data):
    required = ("pid", "port", "token", "url")
    return all(key in data for key in required)


def _is_valid_runtime(data):
    return isinstance(data, dict) and _has_required_runtime_keys(data)


def read_runtime() -> dict | None:
    path = runtime_path()
    if not path.is_file():
        return None
    data = _read_runtime_file(path)
    return data if _is_valid_runtime(data) else None


def _runtime_payload(session: StatusSession) -> dict:
    return {
        "pid": os.getpid(),
        "port": session.port,
        "token": session.token,
        "url": session.url,
        "started_at": session.started_at.isoformat(timespec="seconds"),
    }


def _ensure_runtime_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_runtime_file(path: Path, payload: dict) -> None:
    write_private_json(path, payload)


def write_runtime(session: StatusSession) -> None:
    path = runtime_path()
    _ensure_runtime_dir(path)
    payload = _runtime_payload(session)
    _write_runtime_file(path, payload)


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
    except Exception:
        return False


class StatusSession:
    def __init__(
        self,
        config: Config,
        config_path: Path,
        state,
        started_at: datetime,
    ) -> None:
        self._store_inputs(config, config_path, state, started_at)
        self._init_token()
        self._init_runtime()

    def _store_inputs(
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

    def _init_token(self) -> None:
        self.token = secrets.token_urlsafe(24)

    def _init_runtime(self) -> None:
        self.stop_event = threading.Event()
        self.port = 0
        self.url = ""
        self.blocked: dict | None = None
        self.migration: dict | None = None
        self.release_note: dict | None = None

    def snapshot(self) -> dict:
        note = self.release_note
        if note and self.state.get_meta(CELEBRATED_VERSION_KEY) == note.get(
            "version"
        ):
            note = None
        return build_snapshot(
            self.config,
            self.state,
            self.started_at,
            self.config_path,
            blocked=self.blocked,
            migration=self.migration,
            release_note=note,
        )

    def set_release_note(self, note: dict | None) -> None:
        self.release_note = note

    def dismiss_release(self) -> dict:
        if self.release_note is not None:
            dismiss_release_celebration(
                self.state, str(self.release_note.get("version") or "")
            )
        self.release_note = None
        return {"ok": True, "message": "Nouveautes fermees."}

    def set_blocked(self, release, migration=None) -> None:
        self.blocked = _blocked_payload(release)
        if migration is not None:
            self.migration = _migration_payload(migration)

    def set_migration(self, release) -> None:
        self.migration = _migration_payload(release)

    def _create_notifier(self) -> Notifier:
        return Notifier.from_config(self.config)

    def _send_test_notification(self, notifier: Notifier) -> bool:
        return notifier.send(
            "CheckMate",
            "Test de notification. Si tu ne la vois pas, "
            "coupe le mode silencieux.",
            urgency="normal",
        )

    def _test_notification_result(self) -> dict:
        return {
            "ok": True,
            "message": (
                "Notification envoyée. Si tu ne la vois pas, "
                "coupe le mode silencieux."
            ),
        }

    def test_notification(self) -> dict:
        sent = self._send_test_notification(self._create_notifier())
        if not sent:
            raise StatusError("notification impossible sur ce systeme")
        return self._test_notification_result()

    def check_update(self) -> dict:
        release = check_for_update(
            __version__,
            channel=self.config.updates.channel,
        )
        if release is None:
            return self._up_to_date_response()
        return self._update_available_response(release)

    def _up_to_date_response(self) -> dict:
        return {
            "ok": True,
            "available": False,
            "channel": self.config.updates.channel,
            "message": f"CheckMate {__version__} est à jour.",
        }

    def _update_available_response(self, release) -> dict:
        message = f"Mise à jour disponible : {release.tag}"
        if release.teaser:
            message += f"\n{release.teaser}"
        return {
            "ok": True,
            "available": True,
            "channel": self.config.updates.channel,
            "version": release.version_text,
            "tag": release.tag,
            "url": release.url,
            "teaser": release.teaser,
            "message": message,
        }

    def install_update(self) -> dict:
        version = self._run_self_update()
        return self._build_install_update_result(version)

    def _run_self_update(self):
        try:
            return update_now(self.config)
        except UpdateError as exc:
            raise StatusError(str(exc)) from exc
        except Exception as exc:
            raise StatusError(f"mise a jour impossible : {exc}") from exc

    def _build_install_update_result(self, version) -> dict:
        return {
            "ok": True,
            "version": version,
            "message": self._install_update_message(version),
        }

    def _install_update_message(self, version) -> str:
        return (
            f"Mise a jour {version} en cours. CheckMate redemarre dans "
            "quelques secondes."
        )

    def configure(self) -> dict:
        self._start_assistant()
        return self._assistant_started_response()

    def _build_assistant_command(self) -> list[str]:
        executable = current_executable()
        return [str(executable), "--config", str(self.config_path), "setup"]

    def _start_assistant(self) -> None:
        try:
            subprocess.Popen(self._build_assistant_command(), close_fds=True)
        except OSError as exc:
            raise StatusError(
                f"impossible de lancer l'assistant : {exc}"
            ) from exc

    def _assistant_started_response(self) -> dict:
        return {
            "ok": True,
            "message": (
                "L'assistant s'ouvre dans un nouvel onglet. Termine-le puis "
                "relance CheckMate pour appliquer les changements."
            ),
        }

    def open_logs(self) -> dict:
        folder = self._log_folder()
        self._ensure_log_folder(folder)
        try:
            self._launch_log_folder(folder)
        except OSError as exc:
            raise StatusError(
                f"impossible d'ouvrir le dossier : {exc}"
            ) from exc
        return {"ok": True, "message": f"Dossier ouvert : {folder}"}

    def _log_folder(self):
        return default_log_file().parent

    def _ensure_log_folder(self, folder) -> None:
        folder.mkdir(parents=True, exist_ok=True)

    def _launch_log_folder(self, folder) -> None:
        if sys.platform.startswith("win"):
            getattr(os, "startfile")(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def quit(self) -> dict:
        self.stop_event.set()
        return {"ok": True, "message": "CheckMate est arrêté."}

    def set_channel(self, channel: str) -> dict:
        desired = channel.strip().lower()
        if desired not in {STABLE_CHANNEL, BETA_CHANNEL}:
            raise StatusError("canal inconnu")
        self.config = save_updates_channel(self.config_path, desired)
        return {
            "ok": True,
            "channel": desired,
            "message": _channel_message(desired),
        }

    def action(self, name: str, payload: dict | None = None) -> dict:
        action = ACTIONS_BY_NAME.get(name)
        if action is None:
            raise StatusError("action inconnue")
        if action.method == "set_channel":
            return self.set_channel(str((payload or {}).get("channel") or ""))
        return getattr(self, action.method)()


class _Handler(LocalHandler):
    session: StatusSession

    def do_GET(self) -> None:
        path = self._request_path()
        if path == "/":
            self._serve_page(STATUS_HTML)
        elif path == "/favicon.ico":
            self._favicon()
        elif path == "/api/status":
            self._serve_status()
        else:
            self._json(404, {"error": "route inconnue"})

    def _request_path(self) -> str:
        return urlparse(self.path).path

    def _serve_status(self) -> None:
        if not self._authorized():
            self._json(403, {"error": "acces refuse"})
            return
        self._json(200, self.session.snapshot())

    def do_POST(self) -> None:
        if self._reject_unauthorized():
            return
        if self._reject_unknown_route():
            return
        self._execute_action()

    def _reject_unauthorized(self) -> bool:
        if self._authorized():
            return False
        self._json(403, {"error": "acces refuse"})
        return True

    def _reject_unknown_route(self) -> bool:
        if urlparse(self.path).path == "/api/action":
            return False
        self._json(404, {"error": "route inconnue"})
        return True

    def _execute_action(self) -> None:
        try:
            result = self._perform_action()
        except Exception as exc:
            self._report_action_error(exc)
            return
        self._json(200, result)

    def _perform_action(self):
        payload = self._read_json()
        return self.session.action(str(payload.get("action") or ""), payload)

    def _report_action_error(self, exc) -> None:
        if isinstance(exc, LocalError):
            self._json(exc.status, {"error": str(exc)})
            return
        logger.exception("erreur dans le tableau de bord")
        self._json(500, {"error": f"erreur interne : {exc}"})


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
