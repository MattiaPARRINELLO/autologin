"""Demarrage automatique selon la plateforme."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

TASK_NAME = "CheckMate"
UNIT_NAME = "checkmate-watcher.service"


def _run(command: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=False,
        timeout=timeout,
        capture_output=True,
        text=True,
    )


def _quote(value: str) -> str:
    return f'"{value}"' if " " in value else value


def _linux_unit(executable: Path, config_path: Path) -> str:
    command = " ".join(
        [
            _quote(str(executable)),
            "--config",
            _quote(str(config_path)),
            "run",
        ]
    )
    return (
        "[Unit]\n"
        "Description=CheckMate watcher (surveillance emargement CESAR)\n"
        "After=graphical-session.target\n"
        "PartOf=graphical-session.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        "WorkingDirectory=%h\n"
        "EnvironmentFile=-%h/.config/checkmate-watcher/env\n"
        f"ExecStart={command}\n"
        "Restart=always\n"
        "RestartSec=10\n"
        "\n"
        "[Install]\n"
        "WantedBy=graphical-session.target\n"
    )


def _enable_linux(executable: Path, config_path: Path) -> bool:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        logger.error("systemctl introuvable, demarrage automatique impossible")
        return False

    unit_path = Path.home() / ".config/systemd/user" / UNIT_NAME
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(_linux_unit(executable, config_path), encoding="utf-8")

    _run([systemctl, "--user", "daemon-reload"])
    result = _run([systemctl, "--user", "enable", "--now", UNIT_NAME])
    if result.returncode != 0:
        logger.error("activation systemd echouee : %s", result.stderr.strip())
        return False
    return True


def _enable_windows(executable: Path, config_path: Path) -> bool:
    schtasks = shutil.which("schtasks")
    if not schtasks:
        logger.error("schtasks introuvable, demarrage automatique impossible")
        return False

    command = " ".join(
        [
            f'"{executable}"',
            "--config",
            f'"{config_path}"',
            "run",
        ]
    )
    result = _run(
        [
            schtasks,
            "/Create",
            "/F",
            "/SC",
            "ONLOGON",
            "/TN",
            TASK_NAME,
            "/TR",
            command,
            "/RL",
            "LIMITED",
            "/DELAY",
            "0000:10",
        ]
    )
    if result.returncode != 0:
        logger.error("creation de la tache echouee : %s", result.stderr.strip())
        return False
    return True


def enable_autostart(executable: Path, config_path: Path) -> bool:
    if sys.platform.startswith("win"):
        return _enable_windows(executable, config_path)
    if sys.platform == "linux":
        return _enable_linux(executable, config_path)
    logger.error("demarrage automatique non pris en charge sur %s", sys.platform)
    return False


def _disable_linux() -> bool:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return False
    result = _run([systemctl, "--user", "disable", "--now", UNIT_NAME])
    return result.returncode == 0


def _disable_windows() -> bool:
    schtasks = shutil.which("schtasks")
    if not schtasks:
        return False
    result = _run([schtasks, "/Delete", "/F", "/TN", TASK_NAME])
    return result.returncode == 0


def disable_autostart() -> bool:
    if sys.platform.startswith("win"):
        return _disable_windows()
    if sys.platform == "linux":
        return _disable_linux()
    return False


def _status_linux() -> bool:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return False
    result = _run([systemctl, "--user", "is-enabled", UNIT_NAME])
    return result.returncode == 0 and result.stdout.strip() == "enabled"


def _status_windows() -> bool:
    schtasks = shutil.which("schtasks")
    if not schtasks:
        return False
    result = _run([schtasks, "/Query", "/TN", TASK_NAME])
    return result.returncode == 0


def autostart_enabled() -> bool:
    if sys.platform.startswith("win"):
        return _status_windows()
    if sys.platform == "linux":
        return _status_linux()
    return False


def current_executable() -> Path:
    """Chemin de la commande a relancer au demarrage."""
    candidate = Path(sys.argv[0]).resolve()
    if candidate.name.lower().startswith("python"):
        found = shutil.which("checkmate-watcher")
        if found:
            return Path(found).resolve()
    return candidate
