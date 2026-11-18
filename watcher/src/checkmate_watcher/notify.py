"""Notifications desktop via notify-send et confirmation via zenity."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

ZENITY_TIMEOUT_CODE = 5


def _clean_env() -> dict[str, str]:
    """Retire les bibliotheques injectees par l'environnement appelant.

    T3 Code (et d'autres apps Electron) exportent LD_LIBRARY_PATH vers leurs
    propres bibliotheques, ce qui casse notify-send et zenity du systeme.
    """
    env = os.environ.copy()
    env.pop("LD_LIBRARY_PATH", None)
    env.pop("LD_PRELOAD", None)
    return env


class NotificationError(Exception):
    """Outil de notification indisponible."""


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise NotificationError(f"{tool} est introuvable sur le systeme")
    return path


def _gvariant(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _send_notify_send(
    title: str,
    message: str,
    *,
    app_name: str,
    icon: str,
    urgency: str,
) -> bool:
    binary = shutil.which("notify-send")
    if not binary:
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
            command,
            check=False,
            timeout=15,
            capture_output=True,
            text=True,
            env=_clean_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("notify-send a echoue : %s", exc)
        return False

    if result.returncode != 0:
        logger.warning(
            "notify-send code %s : %s",
            result.returncode,
            (result.stderr or result.stdout).strip(),
        )
        return False
    return True


def _send_gdbus(
    title: str,
    message: str,
    *,
    app_name: str,
    icon: str,
) -> bool:
    """Fallback D-Bus quand notify-send est casse (libnotify incompatible)."""
    binary = shutil.which("gdbus")
    if not binary:
        return False

    command = [
        binary,
        "call",
        "--session",
        "--dest",
        "org.freedesktop.Notifications",
        "--object-path",
        "/org/freedesktop/Notifications",
        "--method",
        "org.freedesktop.Notifications.Notify",
        _gvariant(app_name),
        "0",
        _gvariant(icon),
        _gvariant(title),
        _gvariant(message),
        "[]",
        "{}",
        "5000",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            timeout=15,
            capture_output=True,
            text=True,
            env=_clean_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("gdbus a echoue : %s", exc)
        return False

    if result.returncode != 0:
        logger.warning("gdbus code %s : %s", result.returncode, result.stderr.strip())
        return False
    return True


def send(
    title: str,
    message: str,
    *,
    app_name: str = "CheckMate",
    icon: str = "dialog-information",
    urgency: str = "critical",
) -> bool:
    """Affiche une notification desktop. Renvoie False si l'envoi echoue."""
    if _send_notify_send(
        title,
        message,
        app_name=app_name,
        icon=icon,
        urgency=urgency,
    ):
        return True

    logger.info("notify-send indisponible, tentative via D-Bus")
    return _send_gdbus(title, message, app_name=app_name, icon=icon)


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
            env=_clean_env(),
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
