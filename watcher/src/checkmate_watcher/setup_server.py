"""Serveur local d'onboarding, accessible uniquement en 127.0.0.1."""

from __future__ import annotations

import json
import logging
import secrets
import sys
import threading
import webbrowser
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import BUILD, __version__
from .autostart import (
    current_executable,
    enable_autostart,
    restart_autostart,
)
from .browser import resolve_launch_options
from .config import (
    Config,
    ConfigError,
    default_config,
    load_config,
    save_config,
)
from .credentials import keyring_available, set_password
from .notifications import Notifier
from .paths import default_env_path
from .schedule import Schedule, ScheduleError, parse_days, parse_windows
from .setup_ui import SETUP_HTML
from .signature import SignatureError, load_signature, parse_points, save_signature

logger = logging.getLogger(__name__)

MAX_BODY = 1_000_000
MAX_TIMEOUT = 1800


class SetupError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


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
                for name, index in (
                    ("mon", 0),
                    ("tue", 1),
                    ("wed", 2),
                    ("thu", 3),
                    ("fri", 4),
                    ("sat", 5),
                    ("sun", 6),
                )
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

        prefer_keyring = sys.platform.startswith(("win", "darwin"))
        stored = (
            set_password(self.config.cesar.keyring_service, username, password)
            if prefer_keyring
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
        elif sys.platform.startswith(("win", "darwin")):
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
        notifier = Notifier(
            app_name=self.config.notifications.app_name,
            icon=self.config.notifications.icon,
        )
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

        autostart_requested = bool(payload.get("autostart", True))
        autostart_ok = True
        if autostart_requested:
            autostart_ok = enable_autostart(current_executable(), self.config_path)
            if autostart_ok:
                restart_autostart()

        with self.lock:
            self._persist()

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
        if sys.platform.startswith(("win", "darwin")):
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
    from playwright.sync_api import sync_playwright

    candidate = replace(
        config,
        cesar=replace(
            config.cesar,
            base_url=base_url,
            username=username,
            password=password,
        ),
    )
    selectors = candidate.selectors

    with sync_playwright() as playwright:
        options = resolve_launch_options(playwright.chromium, candidate).as_kwargs()
        browser = playwright.chromium.launch(headless=True, **options)
        try:
            page = browser.new_page()
            page.set_default_timeout(20000)
            page.goto(
                candidate.cesar.login_url,
                wait_until="domcontentloaded",
                timeout=45000,
            )
            page.locator(selectors.login_username[0]).first.fill(username)
            page.locator(selectors.login_password[0]).first.fill(password)
            page.locator(selectors.login_submit[0]).first.click()
            page.wait_for_url(
                lambda url: candidate.cesar.login_path not in url,
                timeout=45000,
            )
            page.wait_for_timeout(1200)
        except Exception as exc:
            message = str(exc).splitlines()[0]
            raise SetupError(f"connexion echouee : {message}") from exc
        finally:
            browser.close()
    return "Connexion reussie."


class _Handler(BaseHTTPRequestHandler):
    session: SetupSession

    def log_message(self, format: str, *args: object) -> None:
        return

    # --- helpers ---

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
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SetupError("corps JSON invalide") from exc
        if not isinstance(data, dict):
            raise SetupError("corps JSON invalide")
        return data

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            token = (parse_qs(parsed.query).get("token") or [""])[0]
            if token != self.session.token:
                self._send(403, b"Jeton invalide", "text/plain; charset=utf-8")
                return
            html = SETUP_HTML.replace("__TOKEN__", self.session.token).replace(
                "__VERSION__", f"{__version__} - build {BUILD}"
            )
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if parsed.path == "/api/state":
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
            if path == "/api/test-login":
                result = self.session.test_login(payload)
            elif path == "/api/credentials":
                result = self.session.save_credentials(payload)
            elif path == "/api/signature":
                result = self.session.save_signature(payload)
            elif path == "/api/import-signature":
                result = self.session.import_signature(payload)
            elif path == "/api/schedule":
                result = self.session.save_schedule(payload)
            elif path == "/api/test-notification":
                result = self.session.test_notification()
            elif path == "/api/finish":
                result = self.session.finish(payload)
            else:
                self._json(404, {"error": "route inconnue"})
                return
        except SetupError as exc:
            self._json(exc.status, {"error": str(exc)})
            return
        except Exception as exc:
            logger.exception("erreur pendant l'onboarding")
            self._json(500, {"error": f"erreur interne : {exc}"})
            return
        self._json(200, result)
        if path == "/api/finish":
            self.session.finished.set()


def create_server(session: SetupSession) -> ThreadingHTTPServer:
    handler = type("SetupHandler", (_Handler,), {"session": session})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    return server


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
            print(f"Configuration invalide : {exc}")
            return 2
        config = default_config()

    token = secrets.token_urlsafe(24)
    session = SetupSession(config_path, config, token)
    server = create_server(session)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/?token={token}"
    print("Configuration CheckMate", flush=True)
    print(
        f"Ouvre cette adresse si le navigateur ne s'ouvre pas : {url}",
        flush=True,
    )
    if open_browser:
        webbrowser.open(url)

    try:
        session.finished.wait(timeout)
    finally:
        server.shutdown()
        server.server_close()

    if session.finished.is_set():
        print("Configuration terminee.")
        return 0
    print("Configuration interrompue (delai depasse).")
    return 1
