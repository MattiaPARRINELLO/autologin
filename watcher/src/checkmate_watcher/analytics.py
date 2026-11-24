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


def install_id(path: Path | None = None) -> str:
    """Identifiant aleatoire stable, cree au premier lancement."""
    global _install_id
    with _install_lock:
        if _install_id is not None:
            return _install_id
        target = path or (data_dir() / "install-id")
        try:
            existing = target.read_text(encoding="utf-8").strip()
            if 8 <= len(existing) <= 64:
                _install_id = existing
                return existing
        except OSError:
            pass
        value = secrets.token_hex(16)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value + "\n", encoding="utf-8")
            try:
                target.chmod(0o600)
            except OSError:
                pass
        except OSError as exc:
            logger.debug("identifiant d'installation non ecrit : %s", exc)
        _install_id = value
        return value


def _enabled(config) -> bool:
    if os.environ.get(DISABLE_ENV, "").strip().lower() in {"0", "false", "non", "off"}:
        return False
    return bool(getattr(config.analytics, "enabled", True))


def _post(endpoint: str, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"checkmate-watcher/{__version__}",
            INGEST_HEADER: REQUEST_TAG,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
            pass
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug("statistique non envoyee : %s", exc)


def _send(config, event: str) -> None:
    """Envoi en tache de fond, sans jamais bloquer ni lever d'exception."""
    endpoint = getattr(config.analytics, "endpoint", DEFAULT_ENDPOINT)
    payload = {
        "install": install_id(),
        "event": event,
        "version": __version__,
        "os": _platform_name(),
    }
    thread = threading.Thread(
        target=_post,
        args=(endpoint, payload),
        name="checkmate-analytics",
        daemon=True,
    )
    thread.start()


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
