"""Notifications et confirmations, portables Linux, macOS et Windows."""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import sys

logger = logging.getLogger(__name__)

ZENITY_TIMEOUT_CODE = 5


class DialogUnavailable(Exception):
    """L'outil de dialogue n'est pas disponible ; un autre peut le remplacer."""


POWERSHELL_APP_ID = (
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"
)

TOAST_SCRIPT = """
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$title = [System.Security.SecurityElement]::Escape($env:CHECKMATE_TITLE)
$message = [System.Security.SecurityElement]::Escape($env:CHECKMATE_MESSAGE)
$template = "<toast><visual><binding template='ToastGeneric'><text>$title</text><text>$message</text></binding></visual></toast>"
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:CHECKMATE_APP_ID)
$notifier.Show($toast)
"""


def _clean_env() -> dict[str, str]:
    """Retire les bibliotheques injectees par l'environnement appelant.

    T3 Code et d'autres apps Electron exportent LD_LIBRARY_PATH vers leurs
    propres bibliotheques, ce qui casse notify-send et zenity du systeme.
    """
    env = os.environ.copy()
    env.pop("LD_LIBRARY_PATH", None)
    env.pop("LD_PRELOAD", None)
    return env


def _gvariant(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def send_linux(
    title: str, message: str, *, app_name: str, icon: str, urgency: str
) -> bool:
    if _send_notify_send(title, message, app_name=app_name, icon=icon, urgency=urgency):
        return True
    logger.info("notify-send indisponible, tentative via D-Bus")
    return _send_gdbus(title, message, app_name=app_name, icon=icon)


def _send_notify_send(
    title: str, message: str, *, app_name: str, icon: str, urgency: str
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


def _send_gdbus(title: str, message: str, *, app_name: str, icon: str) -> bool:
    """Fallback D-Bus quand notify-send est casse."""
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


def send_windows(title: str, message: str, *, app_name: str) -> bool:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        logger.warning("PowerShell introuvable, notification impossible")
        return False

    encoded = base64.b64encode(TOAST_SCRIPT.encode("utf-16-le")).decode("ascii")
    env = os.environ.copy()
    env["CHECKMATE_TITLE"] = title
    env["CHECKMATE_MESSAGE"] = message
    env["CHECKMATE_APP_ID"] = POWERSHELL_APP_ID
    try:
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                encoded,
            ],
            check=False,
            timeout=20,
            capture_output=True,
            text=True,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("notification Windows echouee : %s", exc)
        return False

    if result.returncode != 0:
        logger.warning(
            "notification Windows code %s : %s",
            result.returncode,
            (result.stderr or result.stdout).strip(),
        )
        return False
    return True


def send_macos(title: str, message: str) -> bool:
    binary = shutil.which("osascript")
    if not binary:
        return False
    script = (
        "display notification "
        f"{_applescript_string(message)} with title {_applescript_string(title)}"
    )
    try:
        result = subprocess.run(
            [binary, "-e", script],
            check=False,
            timeout=15,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("osascript a echoue : %s", exc)
        return False
    return result.returncode == 0


def _applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def ask_zenity(
    text: str,
    *,
    timeout: int,
    title: str,
    ok_label: str,
    cancel_label: str,
) -> bool | None:
    binary = shutil.which("zenity")
    if not binary:
        raise DialogUnavailable("zenity introuvable")

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
        raise DialogUnavailable(f"zenity a echoue : {exc}") from exc

    if result.returncode == 0:
        return True
    if result.returncode == ZENITY_TIMEOUT_CODE:
        logger.info("confirmation expiree apres %ss", timeout)
        return None

    stderr = (result.stderr or "").strip()
    if stderr:
        raise DialogUnavailable(
            f"zenity n'a pas pu afficher la confirmation : {stderr}"
        )
    return False


def ask_tkinter(
    text: str,
    *,
    timeout: int,
    title: str,
    ok_label: str,
    cancel_label: str,
) -> bool | None:
    """Dialogue cross-platform, utilise sur Windows ou si zenity manque."""
    try:
        import tkinter as tk
    except ImportError:
        logger.warning("tkinter indisponible, confirmation impossible")
        return None

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        logger.warning("fenetre tkinter impossible : %s", exc)
        return None

    root.title(title)
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass

    answer: dict[str, bool | None] = {"value": None}

    def close(value: bool | None) -> None:
        answer["value"] = value
        root.destroy()

    message = tk.Label(
        root, text=text, wraplength=460, justify="left", padx=20, pady=16
    )
    message.pack()

    buttons = tk.Frame(root, padx=16, pady=12)
    buttons.pack()
    tk.Button(buttons, text=ok_label, width=18, command=lambda: close(True)).pack(
        side="left", padx=6
    )
    tk.Button(buttons, text=cancel_label, width=12, command=lambda: close(False)).pack(
        side="left", padx=6
    )

    root.protocol("WM_DELETE_WINDOW", lambda: close(None))
    root.after(max(1, timeout) * 1000, lambda: close(None))
    root.mainloop()
    return answer["value"]


class Notifier:
    """Notifications et confirmations selon la plateforme."""

    @classmethod
    def from_config(cls, config) -> Notifier:
        return cls(
            app_name=config.notifications.app_name,
            icon=config.notifications.icon,
        )

    def __init__(
        self,
        app_name: str = "CheckMate",
        icon: str = "dialog-information",
        platform: str | None = None,
    ) -> None:
        self.app_name = app_name
        self.icon = icon
        self.platform = platform or sys.platform

    def send(
        self,
        title: str,
        message: str,
        *,
        urgency: str = "critical",
    ) -> bool:
        if self.platform.startswith("win"):
            return send_windows(title, message, app_name=self.app_name)
        if self.platform == "darwin":
            return send_macos(title, message)
        return send_linux(
            title,
            message,
            app_name=self.app_name,
            icon=self.icon,
            urgency=urgency,
        )

    def ask(
        self,
        text: str,
        *,
        timeout: int = 180,
        title: str | None = None,
        ok_label: str = "Je suis present",
        cancel_label: str = "Absent",
    ) -> bool | None:
        window_title = title or self.app_name
        if self.platform.startswith("linux"):
            try:
                return ask_zenity(
                    text,
                    timeout=timeout,
                    title=window_title,
                    ok_label=ok_label,
                    cancel_label=cancel_label,
                )
            except DialogUnavailable as exc:
                logger.info("zenity indisponible, repli sur tkinter : %s", exc)
        return ask_tkinter(
            text,
            timeout=timeout,
            title=window_title,
            ok_label=ok_label,
            cancel_label=cancel_label,
        )
