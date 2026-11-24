"""Serveur local d'onboarding, accessible uniquement en 127.0.0.1."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import sys
import tempfile
import threading
from collections.abc import Iterator
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .autostart import (
    current_executable,
    enable_autostart,
    restart_autostart,
)
from .cesar import CesarSession
from .config import (
    Config,
    ConfigError,
    default_config,
    load_config,
    save_config,
)
from .credentials import keyring_available, prefer_keyring, set_password
from .local_http import LocalError, LocalHandler
from .local_http import create_server as _create_server
from .notifications import Notifier
from .paths import default_env_path
from .schedule import (
    DAY_NAMES,
    DEFAULT_DAYS,
    DEFAULT_WINDOWS,
    Schedule,
    ScheduleError,
    parse_days,
    parse_windows,
)
from .setup_ui import SETUP_HTML
from .signature import SignatureError, load_signature, parse_points, save_signature
from .window import open_url

logger = logging.getLogger(__name__)

MAX_BODY = 1_000_000
MAX_TIMEOUT = 1800
DAY_LABELS = {
    "mon": "Lun",
    "tue": "Mar",
    "wed": "Mer",
    "thu": "Jeu",
    "fri": "Ven",
    "sat": "Sam",
    "sun": "Dim",
}


def _ordered_day_items() -> list[tuple[str, int]]:
    return sorted(DAY_NAMES.items(), key=lambda item: item[1])


def _days_html(days: tuple[int, ...]) -> str:
    return "\n".join(
        f'<label><input type="checkbox" value="{name}"'
        f"{' checked' if index in days else ''}>{DAY_LABELS[name]}</label>"
        for name, index in _ordered_day_items()
    )


def _escape_env_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


_AUTOSTART_DISABLED = (
    "Configuration enregistree. Le demarrage automatique est desactive."
)
_AUTOSTART_FAILED = (
    "Configuration enregistree, mais le demarrage automatique a echoue. "
    "Tu peux lancer CheckMate depuis le menu Demarrer."
)
_AUTOSTART_WINDOWS = (
    "Configuration enregistree. Le demarrage automatique prendra "
    "effet a la prochaine ouverture de session. Tu peux aussi "
    "lancer CheckMate depuis le menu Demarrer."
)
_AUTOSTART_INSTALLED = "Configuration enregistree et service redemarre."


def _autostart_outcome(requested: bool, ok: bool) -> tuple[str, str]:
    if not requested:
        return _AUTOSTART_DISABLED, "disabled"
    if not ok:
        return _AUTOSTART_FAILED, "failed"
    if sys.platform.startswith("win"):
        return _AUTOSTART_WINDOWS, "installed"
    return _AUTOSTART_INSTALLED, "installed"


class SetupError(LocalError):
    """Etape d'onboarding refusee."""


def _signature_payload(raw: object) -> object:
    try:
        return raw if isinstance(raw, dict) else json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SetupError("JSON de signature invalide") from exc


def _parse_signature_points(data: object) -> list:
    try:
        return parse_points(data)
    except SignatureError as exc:
        raise SetupError(str(exc)) from exc


class SetupSession:
    def __init__(self, config_path: Path, config: Config, token: str) -> None:
        self.config_path = config_path
        self.config = config
        self.token = token
        self.finished = threading.Event()
        self.lock = threading.Lock()
        self.password = config.cesar.password
        self.credentials_saved = bool(config.cesar.password)
        self.login_lock = threading.Lock()

    # --- etat ---

    def state(self) -> dict:
        return {
            "username": self.config.cesar.username,
            "base_url": self.config.cesar.base_url,
            "has_signature": self._has_signature(),
            "days": self._active_days(),
            "windows": [str(window) for window in self.config.schedule.windows],
            "notifications": self.config.notifications.enabled,
            "keyring": keyring_available(),
        }

    def _has_signature(self) -> bool:
        if not self.config.signature.file.is_file():
            return False
        try:
            return len(load_signature(self.config.signature.file)) > 0
        except SignatureError:
            return False

    def _active_days(self) -> list[str]:
        return [
            name
            for name, index in _ordered_day_items()
            if index in self.config.schedule.days
        ]

    # --- validation ---

    @staticmethod
    def _text(payload: dict, key: str, label: str, *, max_length: int = 300) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise SetupError(f"{label} obligatoire")
        value = value.strip()
        if "\n" in value or "\r" in value:
            raise SetupError(f"{label} invalide")
        if len(value) > max_length:
            raise SetupError(f"{label} trop long")
        return value

    @staticmethod
    def _required_password(payload: dict) -> str:
        password = payload.get("password")
        if not isinstance(password, str) or not password:
            raise SetupError("mot de passe obligatoire")
        return password

    def _login_inputs(self, payload: dict) -> tuple[str, str, str]:
        base_url = self._text(payload, "base_url", "adresse du site").rstrip("/")
        username = self._text(payload, "username", "identifiant")
        return base_url, username, self._required_password(payload)

    def _require_credentials(self) -> None:
        if not self.credentials_saved:
            raise SetupError("enregistre d'abord les identifiants")

    def _require_finish_ready(self) -> None:
        self._require_credentials()
        if not self.config.signature.file.is_file():
            raise SetupError("enregistre d'abord la signature")

    def _parse_schedule(self, payload: dict) -> Schedule:
        try:
            days = parse_days(payload.get("days"))
            windows = parse_windows(payload.get("windows"))
        except ScheduleError as exc:
            raise SetupError(str(exc)) from exc
        return Schedule(enabled=True, days=days, windows=windows)

    # --- actions ---

    @contextlib.contextmanager
    def _login_guard(self) -> Iterator[None]:
        if not self.login_lock.acquire(blocking=False):
            raise SetupError("un test de connexion est deja en cours", status=409)
        try:
            yield
        finally:
            self.login_lock.release()

    def test_login(self, payload: dict) -> dict:
        base_url, username, password = self._login_inputs(payload)
        with self._login_guard():
            message = _test_connection(self.config, base_url, username, password)
        return {"ok": True, "message": message}

    def save_credentials(self, payload: dict) -> dict:
        base_url, username, password = self._credential_fields(payload)
        stored = self._store_in_keyring(username, password)
        self._apply_credentials(base_url, username, password)
        return {"ok": True, "message": self._credential_message(stored)}

    def _credential_fields(self, payload: dict) -> tuple[str, str, str]:
        base_url = self._text(payload, "base_url", "adresse du site").rstrip("/")
        username = self._text(payload, "username", "identifiant")
        password = self._required_password(payload)
        if "\n" in password or "\r" in password:
            raise SetupError("mot de passe invalide")
        return base_url, username, password

    def _store_in_keyring(self, username: str, password: str) -> bool:
        if not prefer_keyring():
            return False
        return set_password(self.config.cesar.keyring_service, username, password)

    def _apply_credentials(self, base_url: str, username: str, password: str) -> None:
        with self.lock:
            self.password = password
            self.credentials_saved = True
            self.config = self._config_with_cesar(base_url, username)
            self._persist()

    def _config_with_cesar(self, base_url: str, username: str) -> Config:
        cesar = replace(self.config.cesar, base_url=base_url, username=username)
        return replace(self.config, cesar=cesar)

    @staticmethod
    def _credential_message(stored: bool) -> str:
        if stored:
            return "Identifiants enregistres dans le trousseau du systeme."
        if prefer_keyring():
            return "Identifiants enregistres dans un fichier prive."
        return "Identifiants enregistres pour le service."

    def import_signature(self, payload: dict) -> dict:
        data = _signature_payload(payload.get("raw"))
        parsed = _parse_signature_points(data)
        return self._store_signature(parsed, "importee")

    def _store_signature(self, parsed: list, adjective: str) -> dict:
        save_signature(self.config.signature.file, parsed)
        return {
            "ok": True,
            "message": f"Signature {adjective} ({len(parsed)} points).",
        }

    def save_signature(self, payload: dict) -> dict:
        points = payload.get("points")
        try:
            parsed = parse_points(points)
        except SignatureError as exc:
            raise SetupError(str(exc)) from exc
        save_signature(self.config.signature.file, parsed)
        return {
            "ok": True,
            "message": f"Signature enregistree ({len(parsed)} points).",
        }

    def save_schedule(self, payload: dict) -> dict:
        self._require_credentials()
        schedule = self._parse_schedule(payload)
        self._store_schedule(schedule)
        return {"ok": True, "message": "Planning enregistre."}

    def _store_schedule(self, schedule: Schedule) -> None:
        with self.lock:
            self.config = replace(self.config, schedule=schedule)
            self._persist()

    def test_notification(self) -> dict:
        notifier = Notifier.from_config(self.config)
        sent = notifier.send(
            "CheckMate",
            "Si tu vois cette notification, tout fonctionne.",
            urgency="normal",
        )
        if not sent:
            raise SetupError("notification impossible sur ce systeme")
        return {"ok": True, "message": "Notification envoyee."}

    def _install_autostart(self, payload: dict) -> tuple[bool, bool]:
        requested = bool(payload.get("autostart", True))
        if not requested:
            return requested, True
        ok = enable_autostart(current_executable(), self.config_path)
        if ok:
            restart_autostart()
        return requested, ok

    def finish(self, payload: dict) -> dict:
        self._require_finish_ready()
        with self.lock:
            self._persist()
        message, state = _autostart_outcome(*self._install_autostart(payload))
        return self._finish_result(message, state)

    def _finish_result(self, message: str, state: str) -> dict:
        return {
            "ok": True,
            "message": message,
            "username": self.config.cesar.username,
            "windows": [str(window) for window in self.config.schedule.windows],
            "autostart": state,
        }

    # --- persistance ---

    def _persist(self) -> None:
        if prefer_keyring():
            self._persist_keyring()
            return
        self._persist_env()

    def _persist_keyring(self) -> None:
        stored = self._store_keyring_password()
        save_config(
            self.config_path,
            self.config,
            password=None if stored else (self.password or None),
        )

    def _store_keyring_password(self) -> bool:
        if not self.password:
            return False
        return set_password(
            self.config.cesar.keyring_service,
            self.config.cesar.username,
            self.password,
        )

    def _persist_env(self) -> None:
        if self.password:
            self._write_password_env(self.password)
        save_config(
            self.config_path,
            self.config,
            password_env="CHECKMATE_PASSWORD" if self.password else None,
        )

    def _write_password_env(self, password: str) -> None:
        env_path = default_env_path()
        escaped = _escape_env_value(password)
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(f'CHECKMATE_PASSWORD="{escaped}"\n', encoding="utf-8")
        env_path.chmod(0o600)


def _with_credentials(
    config: Config, base_url: str, username: str, password: str
) -> Config:
    cesar = replace(
        config.cesar, base_url=base_url, username=username, password=password
    )
    return replace(config, cesar=cesar)


def _with_profile(config: Config, profile_dir: Path) -> Config:
    watcher = replace(config.watcher, profile_dir=profile_dir)
    return replace(config, watcher=watcher)


async def _login_in_profile(config: Config, profile: Path) -> None:
    session = CesarSession(_with_profile(config, profile))
    try:
        await session.open(headless=True)
        await session.login()
    finally:
        await session.close()


async def _login_attempt(candidate: Config) -> None:
    with tempfile.TemporaryDirectory(prefix="checkmate-login-") as profile:
        await _login_in_profile(candidate, Path(profile))


def _run_login(candidate: Config) -> None:
    try:
        asyncio.run(asyncio.wait_for(_login_attempt(candidate), timeout=90))
    except Exception as exc:
        message = str(exc).splitlines()[0] or exc.__class__.__name__
        raise SetupError(f"connexion echouee : {message}") from exc


def _test_connection(
    config: Config, base_url: str, username: str, password: str
) -> str:
    """Reproduit la connexion reelle, avec les selecteurs et le flux du watcher."""
    candidate = _with_credentials(config, base_url, username, password)
    _run_login(candidate)
    return "Connexion reussie."


class _Handler(LocalHandler):
    session: SetupSession
    max_body = MAX_BODY

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._serve_page(
                SETUP_HTML,
                {
                    "DAYS": _days_html(parse_days(DEFAULT_DAYS)),
                    "WINDOWS": ", ".join(DEFAULT_WINDOWS),
                },
            )
            return
        if path == "/favicon.ico":
            self._favicon()
            return
        if path == "/api/state":
            if not self._authorized():
                self._json(403, {"error": "acces refuse"})
                return
            self._json(200, self.session.state())
            return
        self._json(404, {"error": "route inconnue"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(403, {"error": "acces refuse"})
            return
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            handler = self._routes().get(path)
            if handler is None:
                self._json(404, {"error": "route inconnue"})
                return
            result = handler(payload)
        except LocalError as exc:
            self._json(exc.status, {"error": str(exc)})
            return
        except Exception as exc:
            logger.exception("erreur pendant l'onboarding")
            self._json(500, {"error": f"erreur interne : {exc}"})
            return
        self._json(200, result)
        if path == "/api/finish":
            self.session.finished.set()

    def _routes(self) -> dict[str, Any]:
        return {
            "/api/test-login": self.session.test_login,
            "/api/credentials": self.session.save_credentials,
            "/api/signature": self.session.save_signature,
            "/api/import-signature": self.session.import_signature,
            "/api/schedule": self.session.save_schedule,
            "/api/test-notification": lambda _: self.session.test_notification(),
            "/api/finish": self.session.finish,
        }


def create_server(session: SetupSession) -> ThreadingHTTPServer:
    return _create_server(session, _Handler)


def _afficher_config_invalide(exc: Exception) -> None:
    print(f"Configuration invalide : {exc}")


def _afficher_url(url: str) -> None:
    print("Configuration CheckMate", flush=True)
    print(
        f"Ouvre cette adresse si le navigateur ne s'ouvre pas : {url}",
        flush=True,
    )


def _afficher_fenetre_fermee() -> None:
    print("Fenetre fermee avant la fin de la configuration.")


def _afficher_configuration_terminee() -> None:
    print("Configuration terminee.")


def _afficher_configuration_interrompue() -> None:
    print("Configuration interrompue (delai depasse).")


def run_setup(
    config_path: Path,
    *,
    open_browser: bool = True,
    timeout: int = MAX_TIMEOUT,
) -> int:
    try:
        config = load_config(config_path, require_password=False)
    except ConfigError as exc:
        if config_path.is_file():
            _afficher_config_invalide(exc)
            return 2
        config = default_config()

    token = secrets.token_urlsafe(24)
    session = SetupSession(config_path, config, token)
    server = create_server(session)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/?token={token}"
    _afficher_url(url)
    if open_browser:
        native = open_url(url, close_event=session.finished)
        if native and not session.finished.is_set():
            _afficher_fenetre_fermee()
            server.shutdown()
            server.server_close()
            return 1

    try:
        session.finished.wait(timeout)
    finally:
        server.shutdown()
        server.server_close()

    if session.finished.is_set():
        _afficher_configuration_terminee()
        return 0
    _afficher_configuration_interrompue()
    return 1
