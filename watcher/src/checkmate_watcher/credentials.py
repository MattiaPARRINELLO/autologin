"""Stockage des identifiants dans le trousseau du systeme."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

DEFAULT_SERVICE = "checkmate-watcher"


def prefer_keyring() -> bool:
    """Le trousseau est fiable sur Windows et macOS ; Linux passe par le fichier env."""
    return sys.platform.startswith(("win", "darwin"))


def _keyring_module():
    try:
        import keyring
    except ImportError as exc:  # pragma: no cover - dependance toujours installee
        logger.warning("keyring indisponible : %s", exc)
        return None
    return keyring


def keyring_available() -> bool:
    return _keyring_module() is not None


def get_password(service: str, username: str) -> str | None:
    keyring = _keyring_module()
    if keyring is None:
        return None
    try:
        value = keyring.get_password(service, username)
    except Exception as exc:  # backend absent ou verrouille
        logger.warning("trousseau inaccessible : %s", exc)
        return None
    return value or None


def set_password(service: str, username: str, password: str) -> bool:
    keyring = _keyring_module()
    if keyring is None:
        return False
    try:
        keyring.set_password(service, username, password)
        return keyring.get_password(service, username) == password
    except Exception as exc:
        logger.warning("ecriture dans le trousseau impossible : %s", exc)
        return False
