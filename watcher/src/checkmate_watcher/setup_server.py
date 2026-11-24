"""Serveur local d'onboarding, accessible uniquement en 127.0.0.1."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import sys
import tempfile
import threading
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


def _days_html(days: tuple[int, ...]) -> str:
    ordered = sorted(DAY_NAMES.items(), key=lambda item: item[1])
    return "\n".join(
        f'<label><input type="checkbox" value="{name}"'
        f"{' checked' if index in days else ''}>{DAY_LABELS[name]}</label>"
        for name, index in ordered
    )


class SetupError(LocalError):
    """Etape d'onboarding refusee."""


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
        has_signature = False
        if self.config.signature.file.is_file():
            try:
                has_signature = len(load_signature(self.config.signature.file)) > 0
            except SignatureError:
                has_signature = False
        return {
            "username": self.config.cesar.username,
            "base_url": self.config.cesar.base_url,
            "has_signature": has_signature,
            "days": [
                name
                for name, index in sorted(DAY_NAMES.items(), key=lambda item: item[1])
                if index in self.config.schedule.days
            ],
            "windows": [str(window) for window in self.config.schedule.windows],
            "notifications": self.config.notifications.enabled,
            "keyring": keyring_available(),
        }

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

    # --- actions ---

    def test_login(self, payload: dict) -> dict:
        base_url = self._text(payload, "base_url", "adresse du site").rstrip("/")
        username = self._text(payload, "username", "identifiant")
        password = payload.get("password")
        if not isinstance(password, str) or not password:
            raise SetupError("mot de passe obligatoire")

        if not self.login_lock.acquire(blocking=False):
            raise SetupError("un test de connexion est deja en cours", status=409)
        try:
            message = _test_connection(self.config, base_url, username, password)
        finally:
            self.login_lock.release()
        return {"ok": True, "message": message}

    def save_credentials(self, payload: dict) -> dict:
        base_url = self._text(payload, "base_url", "adresse du site").rstrip("/")
        username = self._text(payload, "username", "identifiant")
        password = payload.get("password")
        if not isinstance(password, str) or not password:
            raise SetupError("mot de passe obligatoire")
        if "\n" in password or "\r" in password:
            raise SetupError("mot de passe invalide")

        stored = (
            set_password(self.config.cesar.keyring_service, username, password)
            if prefer_keyring()
            else False
        )
        with self.lock:
            self.password = password
            self.credentials_saved = True
            self.config = replace(
                self.config,
                cesar=replace(
                    self.config.cesar,
                    base_url=base_url,
                    username=username,
                ),
            )
            self._persist()

        if stored:
            message = "Identifiants enregistres dans le trousseau du systeme."
        elif prefer_keyring():
            message = "Identifiants enregistres dans un fichier prive."
        else:
            message = "Identifiants enregistres pour le service."
        return {"ok": True, "message": message}

    def import_signature(self, payload: dict) -> dict:
        raw = payload.get("raw")
        try:
            data = raw if isinstance(raw, dict) else json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise SetupError("JSON de signature invalide") from exc
        try:
            parsed = parse_points(data)
        except SignatureError as exc:
            raise SetupError(str(exc)) from exc
        save_signature(self.config.signature.file, parsed)
        return {
            "ok": True,
            "message": f"Signature importee ({len(parsed)} points).",
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
        if not self.credentials_saved:
            raise SetupError("enregistre d'abord les identifiants")
        try:
            days = parse_days(payload.get("days"))
            windows = parse_windows(payload.get("windows"))
        except ScheduleError as exc:
            raise SetupError(str(exc)) from exc

        with self.lock:
            self.config = replace(
                self.config,
                schedule=Schedule(enabled=True, days=days, windows=windows),
            )
            self._persist()
        return {"ok": True, "message": "Planning enregistre."}

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

    def finish(self, payload: dict) -> dict:
        if not self.credentials_saved:
            raise SetupError("enregistre d'abord les identifiants")
        if not self.config.signature.file.is_file():
            raise SetupError("enregistre d'abord la signature")

        with self.lock:
            self._persist()

        autostart_requested = bool(payload.get("autostart", True))
        autostart_ok = True
        if autostart_requested:
            autostart_ok = enable_autostart(current_executable(), self.config_path)
            if autostart_ok:
                restart_autostart()

        if not autostart_requested:
            message = (
                "Configuration enregistree. Le demarrage automatique est desactive."
            )
        elif autostart_ok:
            if sys.platform.startswith("win"):
                message = (
                    "Configuration enregistree. Le demarrage automatique prendra "
                    "effet a la prochaine ouverture de session. Tu peux aussi "
                    "lancer CheckMate depuis le menu Demarrer."
                )
            else:
                message = "Configuration enregistree et service redemarre."
        else:
            message = (
                "Configuration enregistree, mais le demarrage automatique a echoue. "
                "Tu peux lancer CheckMate depuis le menu Demarrer."
            )

        if not autostart_requested:
            autostart_state = "disabled"
        elif autostart_ok:
            autostart_state = "installed"
        else:
            autostart_state = "failed"
        return {
            "ok": True,
            "message": message,
            "username": self.config.cesar.username,
            "windows": [str(window) for window in self.config.schedule.windows],
            "autostart": autostart_state,
        }

    # --- persistance ---

    def _persist(self) -> None:
        if prefer_keyring():
            stored = False
            if self.password:
                stored = set_password(
                    self.config.cesar.keyring_service,
                    self.config.cesar.username,
                    self.password,
                )
            save_config(
                self.config_path,
                self.config,
                password=None if stored else (self.password or None),
            )
            return

        if self.password:
            env_path = default_env_path()
            escaped = self.password.replace("\\", "\\\\").replace('"', '\\"')
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.write_text(f'CHECKMATE_PASSWORD="{escaped}"\n', encoding="utf-8")
            env_path.chmod(0o600)
        save_config(
            self.config_path,
            self.config,
            password_env="CHECKMATE_PASSWORD" if self.password else None,
        )


def _test_connection(
    config: Config, base_url: str, username: str, password: str
) -> str:
    """Reproduit la connexion reelle, avec les selecteurs et le flux du watcher."""
    candidate = replace(
        config,
        cesar=replace(
            config.cesar,
            base_url=base_url,
            username=username,
            password=password,
        ),
    )

    async def attempt() -> None:
        with tempfile.TemporaryDirectory(prefix="checkmate-login-") as profile:
            accessible = replace(
                candidate,
                watcher=replace(candidate.watcher, profile_dir=Path(profile)),
            )
            session = CesarSession(accessible)
            try:
                await session.open(headless=True)
                await session.login()
            finally:
                await session.close()

    try:
        asyncio.run(asyncio.wait_for(attempt(), timeout=90))
    except Exception as exc:
        message = str(exc).splitlines()[0] or exc.__class__.__name__
        raise SetupError(f"connexion echouee : {message}") from exc
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
