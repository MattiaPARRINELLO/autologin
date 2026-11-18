"""Notifications desktop via notify-send et confirmation via zenity."""

from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

ZENITY_TIMEOUT_CODE = 5


class NotificationError(Exception):
    """Outil de notification indisponible."""


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise NotificationError(f"{tool} est introuvable sur le systeme")
    return path


def send(
    title: str,
    message: str,
    *,
    app_name: str = "CheckMate",
    icon: str = "dialog-information",
    urgency: str = "critical",
) -> bool:
    """Affiche une notification desktop. Renvoie False si l'envoi echoue."""
    try:
        binary = _require("notify-send")
    except NotificationError as exc:
        logger.warning("notification impossible : %s", exc)
        return False

    command = [
        binary,
        "--app-name",
        app_name,
        "--urgency",
        urgency,
        "--icon",
        icon,
        title,
        message,
    ]
    try:
        result = subprocess.run(
            command, check=False, timeout=15, capture_output=True, text=True
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("notify-send a echoue : %s", exc)
        return False

    if result.returncode != 0:
        logger.warning(
            "notify-send code %s : %s", result.returncode, result.stderr.strip()
        )
        return False
    return True


def ask(
    text: str,
    *,
    timeout: int = 180,
    title: str = "CheckMate",
    ok_label: str = "Je suis present",
    cancel_label: str = "Absent",
) -> bool | None:
    """Demande une confirmation.

    Renvoie True (present), False (absent) ou None si timeout ou erreur.
    """
    try:
        binary = _require("zenity")
    except NotificationError as exc:
        logger.warning("confirmation impossible : %s", exc)
        return None

    command = [
        binary,
        "--question",
        f"--title={title}",
        f"--text={text}",
        f"--timeout={max(10, timeout)}",
        f"--ok-label={ok_label}",
        f"--cancel-label={cancel_label}",
        "--width=520",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            timeout=timeout + 15,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("zenity a echoue : %s", exc)
        return None

    if result.returncode == 0:
        return True
    if result.returncode == ZENITY_TIMEOUT_CODE:
        logger.info("confirmation expiree apres %ss", timeout)
        return None

    stderr = (result.stderr or "").strip()
    if stderr:
        logger.warning("zenity n'a pas pu afficher la confirmation : %s", stderr)
        return None
    return False
