"""Compteurs d'usage anonymes : installations et signatures reussies.

Aucune donnee CESAR, aucun identifiant de compte, aucune adresse IP stockee.
Seul un identifiant d'installation aleatoire permet de compter les utilisateurs
uniques. L'envoi est silencieux : une panne reseau ne doit jamais gener le
watcher.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import secrets
import threading
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__
from .paths import data_dir

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://main.mprnl.fr/cm-stats/api/event"

# La cle d'ingestion n'est pas un secret : elle evite seulement qu'un robot
# quelconque remplisse la base. Le code de l'application est public.
REQUEST_TAG = "checkmate-stats-public-ingest"
INGEST_HEADER = "X-CheckMate-Key"

TIMEOUT_SECONDS = 5

DISABLE_ENV = "CHECKMATE_ANALYTICS"

_install_lock = threading.Lock()
_install_id: str | None = None


def _platform_name() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "macos"
    if system == "linux":
        return "linux"
    return "other"


def _read_install_id(target: Path) -> str | None:
    """Valeur existante valide, sinon None."""
    try:
        existing = target.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if 8 <= len(existing) and len(existing) <= 64:
        return existing
    return None


def _write_install_id(target: Path, value: str) -> None:
    """Ecrit la valeur, sans jamais lever d'exception."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value + "\n", encoding="utf-8")
        try:
            target.chmod(0o600)
        except OSError:
            pass
    except OSError as exc:
        logger.debug("identifiant d'installation non ecrit : %s", exc)


def _resolve_install_id(target: Path) -> str:
    """Lit l'identifiant existant ou en cree un nouveau."""
    existing = _read_install_id(target)
    if existing is not None:
        return existing
    value = secrets.token_hex(16)
    _write_install_id(target, value)
    return value


def install_id(path: Path | None = None) -> str:
    """Identifiant aleatoire stable, cree au premier lancement."""
    global _install_id
    with _install_lock:
        if _install_id is not None:
            return _install_id
        target = path or (data_dir() / "install-id")
        _install_id = _resolve_install_id(target)
        return _install_id


def _enabled(config) -> bool:
    if os.environ.get(DISABLE_ENV, "").strip().lower() in {"0", "false", "non", "off"}:
        return False
    return bool(getattr(config.analytics, "enabled", True))


def _encode_payload(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "User-Agent": f"checkmate-watcher/{__version__}",
        INGEST_HEADER: REQUEST_TAG,
    }


def _build_request(endpoint: str, body: bytes) -> urllib.request.Request:
    return urllib.request.Request(
        endpoint, data=body, method="POST", headers=_headers()
    )


def _deliver(request: urllib.request.Request) -> None:
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
            pass
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug("statistique non envoyee : %s", exc)


def _post(endpoint: str, payload: dict) -> None:
    _deliver(_build_request(endpoint, _encode_payload(payload)))


def _endpoint(config) -> str:
    return getattr(config.analytics, "endpoint", DEFAULT_ENDPOINT)


def _payload(event: str) -> dict:
    return {
        "install": install_id(),
        "event": event,
        "version": __version__,
        "os": _platform_name(),
    }


def _spawn(endpoint: str, payload: dict) -> None:
    threading.Thread(
        target=_post,
        args=(endpoint, payload),
        name="checkmate-analytics",
        daemon=True,
    ).start()


def _send(config, event: str) -> None:
    """Envoi en tache de fond, sans jamais bloquer ni lever d'exception."""
    endpoint = _endpoint(config)
    _spawn(endpoint, _payload(event))


def record(config, event: str) -> None:
    if not _enabled(config):
        return
    try:
        _send(config, event)
    except Exception as exc:
        logger.debug("statistique ignoree : %s", exc)


def record_startup(config, state) -> None:
    """Signale une nouvelle installation, une seule fois par machine."""
    if not _enabled(config):
        return
    if state.get_meta("analytics.install_sent") != "1":
        state.set_meta("analytics.install_sent", "1")
        record(config, "install")
