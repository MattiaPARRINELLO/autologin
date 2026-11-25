"""Notifications et confirmations, portables Linux, macOS et Windows."""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

ZENITY_TIMEOUT_CODE = 5

START_MENU_LINK = "Microsoft\\Windows\\Start Menu\\Programs\\{name}.lnk"


class DialogUnavailable(Exception):
    """L'outil de dialogue n'est pas disponible ; un autre peut le remplacer."""


CHECKMATE_APP_ID = "CheckMate.Watcher"

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


def _notify_send_command(binary, title, message, *, app_name, icon, urgency):
    return [
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


def _run_notify_send(command):
    try:
        return subprocess.run(
            command,
            check=False,
            timeout=15,
            capture_output=True,
            text=True,
            env=_clean_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("notify-send a echoue : %s", exc)
        return None


def _log_notify_send_failure(result):
    logger.warning(
        "notify-send code %s : %s",
        result.returncode,
        (result.stderr or result.stdout).strip(),
    )


def _send_notify_send(title, message, *, app_name, icon, urgency):
    binary = shutil.which("notify-send")
    if not binary:
        return False
    result = _run_notify_send(
        _notify_send_command(
            binary, title, message, app_name=app_name, icon=icon, urgency=urgency
        )
    )
    if result is None or result.returncode != 0:
        if result is not None:
            _log_notify_send_failure(result)
        return False
    return True


def _gdbus_command(binary, app_name, icon, title, message):
    return [
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


def _run_gdbus(command):
    try:
        return subprocess.run(
            command,
            check=False,
            timeout=15,
            capture_output=True,
            text=True,
            env=_clean_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("gdbus a echoue : %s", exc)
        return None


def _send_gdbus(title, message, *, app_name, icon):
    binary = shutil.which("gdbus")
    if not binary:
        return False
    result = _run_gdbus(_gdbus_command(binary, app_name, icon, title, message))
    if result is None or result.returncode != 0:
        if result is not None:
            logger.warning(
                "gdbus code %s : %s", result.returncode, result.stderr.strip()
            )
        return False
    return True


def _start_menu_shortcut(app_name: str) -> Path | None:
    """Windows n'accepte un toast que si un raccourci porte son AUMID."""
    base = os.environ.get("APPDATA")
    if not base:
        return None
    return Path(base) / START_MENU_LINK.format(name=app_name)


def _windows_app_id(app_name: str) -> str:
    """AUMID CheckMate si son raccourci existe, sinon celui de PowerShell."""
    shortcut = _start_menu_shortcut(app_name)
    if shortcut is not None and shortcut.is_file():
        return CHECKMATE_APP_ID
    logger.info("raccourci CheckMate absent, toast sous PowerShell")
    return POWERSHELL_APP_ID


def _toast_env(title: str, message: str, app_id: str) -> dict:
    env = os.environ.copy()
    env["CHECKMATE_TITLE"] = title
    env["CHECKMATE_MESSAGE"] = message
    env["CHECKMATE_APP_ID"] = app_id
    return env


def _toast_command(powershell: str, encoded: str) -> list[str]:
    return [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]


def _run_toast(powershell, title, message, app_id):
    encoded = base64.b64encode(TOAST_SCRIPT.encode("utf-16-le")).decode("ascii")
    try:
        return subprocess.run(
            _toast_command(powershell, encoded),
            check=False,
            timeout=20,
            capture_output=True,
            text=True,
            env=_toast_env(title, message, app_id),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("notification Windows echouee : %s", exc)
        return None


def _log_toast_failure(result, app_id: str) -> None:
    logger.warning(
        "notification Windows code %s (AUMID %s) : %s",
        result.returncode,
        app_id,
        (result.stderr or result.stdout).strip(),
    )


def _show_toast(powershell: str, title: str, message: str, app_id: str) -> bool:
    result = _run_toast(powershell, title, message, app_id)
    if result is None:
        return False
    if result.returncode != 0:
        _log_toast_failure(result, app_id)
        return False
    return True


def _powershell_binary() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


def send_windows(title, message, *, app_name):
    powershell = _powershell_binary()
    if not powershell:
        logger.warning("PowerShell introuvable, notification impossible")
        return False
    app_id = _windows_app_id(app_name)
    if _show_toast(powershell, title, message, app_id):
        return True
    if app_id == POWERSHELL_APP_ID:
        return False
    logger.info("AUMID %s refuse, repli sur PowerShell", app_id)
    return _show_toast(powershell, title, message, POWERSHELL_APP_ID)


def _macos_script(title: str, message: str) -> str:
    return (
        "display notification "
        f"{_applescript_string(message)} with title {_applescript_string(title)}"
    )


def _run_osascript(binary, script):
    try:
        return subprocess.run(
            [binary, "-e", script],
            check=False,
            timeout=15,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("osascript a echoue : %s", exc)
        return None


def send_macos(title: str, message: str) -> bool:
    binary = shutil.which("osascript")
    if not binary:
        return False
    result = _run_osascript(binary, _macos_script(title, message))
    return result is not None and result.returncode == 0


def _applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _zenity_command(binary, title, text, timeout, ok_label, cancel_label):
    return [
        binary,
        "--question",
        f"--title={title}",
        f"--text={text}",
        f"--timeout={max(10, timeout)}",
        f"--ok-label={ok_label}",
        f"--cancel-label={cancel_label}",
        "--width=520",
    ]


def _run_zenity(command, timeout):
    try:
        return subprocess.run(
            command,
            check=False,
            timeout=timeout + 15,
            capture_output=True,
            text=True,
            env=_clean_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DialogUnavailable(f"zenity a echoue : {exc}") from exc


def _zenity_result(result, timeout):
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


def ask_zenity(text, *, timeout, title, ok_label, cancel_label):
    binary = shutil.which("zenity")
    if not binary:
        raise DialogUnavailable("zenity introuvable")
    result = _run_zenity(
        _zenity_command(binary, title, text, timeout, ok_label, cancel_label), timeout
    )
    return _zenity_result(result, timeout)


def _import_tkinter():
    try:
        import tkinter as tk
    except ImportError:
        logger.warning("tkinter indisponible, confirmation impossible")
        return None
    return tk


def _open_tk_root(tk):
    try:
        return tk.Tk()
    except tk.TclError as exc:
        logger.warning("fenetre tkinter impossible : %s", exc)
        return None


def _configure_tk_root(root, title, tk):
    root.title(title)
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass


def _make_close(root, answer):
    def close(value):
        answer["value"] = value
        root.destroy()

    return close


def _build_tk_dialog(root, text, ok_label, cancel_label, close, tk):
    tk.Label(root, text=text, wraplength=460, justify="left", padx=20, pady=16).pack()
    buttons = tk.Frame(root, padx=16, pady=12)
    buttons.pack()
    tk.Button(buttons, text=ok_label, width=18, command=lambda: close(True)).pack(
        side="left", padx=6
    )
    tk.Button(buttons, text=cancel_label, width=12, command=lambda: close(False)).pack(
        side="left", padx=6
    )


def _run_tk_dialog(root, timeout, close):
    root.protocol("WM_DELETE_WINDOW", lambda: close(None))
    root.after(max(1, timeout) * 1000, lambda: close(None))
    root.mainloop()


def ask_tkinter(text, *, timeout, title, ok_label, cancel_label):
    tk = _import_tkinter()
    if tk is None:
        return None
    root = _open_tk_root(tk)
    if root is None:
        return None
    _configure_tk_root(root, title, tk)
    answer = {"value": None}
    close = _make_close(root, answer)
    _build_tk_dialog(root, text, ok_label, cancel_label, close, tk)
    _run_tk_dialog(root, timeout, close)
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

    def send(self, title, message, *, urgency="critical"):
        if self.platform.startswith("win"):
            return send_windows(title, message, app_name=self.app_name)
        if self.platform == "darwin":
            return send_macos(title, message)
        return send_linux(
            title, message, app_name=self.app_name, icon=self.icon, urgency=urgency
        )

    def ask(
        self,
        text,
        *,
        timeout=180,
        title=None,
        ok_label="Je suis present",
        cancel_label="Absent",
    ):
        window_title = title or self.app_name
        kwargs = {
            "timeout": timeout,
            "title": window_title,
            "ok_label": ok_label,
            "cancel_label": cancel_label,
        }
        if self.platform.startswith("linux"):
            try:
                return ask_zenity(text, **kwargs)
            except DialogUnavailable as exc:
                logger.info("zenity indisponible, repli sur tkinter : %s", exc)
        return ask_tkinter(text, **kwargs)
