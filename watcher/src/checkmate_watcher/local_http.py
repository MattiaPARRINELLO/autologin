"""Serveur HTTP local commun au tableau de bord et a l'onboarding.

Les deux interfaces partagent la meme frontiere de securite : ecoute sur
127.0.0.1, jeton dans l'en-tete ou dans l'URL, et memes en-tetes de reponse.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import BUILD, __version__

MAX_BODY = 100_000


class LocalError(Exception):
    """Requete refusee, avec le code HTTP a renvoyer."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def version_label() -> str:
    return f"{__version__} - build {BUILD}"


class LocalHandler(BaseHTTPRequestHandler):
    session: Any
    max_body = MAX_BODY

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

    def _query_authorized(self) -> bool:
        parsed = urlparse(self.path)
        token = (parse_qs(parsed.query).get("token") or [""])[0]
        return token == self.session.token

    def _serve_page(
        self, template: str, values: dict[str, str] | None = None
    ) -> None:
        if not self._query_authorized():
            self._send(403, b"Jeton invalide", "text/plain; charset=utf-8")
            return
        html = template.replace("__TOKEN__", self.session.token).replace(
            "__VERSION__", version_label()
        )
        for key, value in (values or {}).items():
            html = html.replace(f"__{key}__", value)
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _favicon(self) -> None:
        self.send_response(204)
        self.end_headers()

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > self.max_body:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalError("corps JSON invalide") from exc
        if not isinstance(data, dict):
            raise LocalError("corps JSON invalide")
        return data


def create_server(
    session: Any, handler: type[LocalHandler]
) -> ThreadingHTTPServer:
    bound = type("LocalSessionHandler", (handler,), {"session": session})
    server = ThreadingHTTPServer(("127.0.0.1", 0), bound)
    server.daemon_threads = True
    return server
