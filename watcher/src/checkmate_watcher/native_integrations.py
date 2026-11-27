"""Passerelle Python vers les integrations systeme Rust de la tranche T2.

L'icone, les notifications et le demarrage automatique appartiennent a
`checkmate-platform`. Python reste le moteur : il lance l'icone, demande une
notification et delegue l'autostart. Chaque fonction rend `None` quand le
binaire natif manque ou echoue, pour que l'appelant garde le repli Python.
"""

from __future__ import annotations

import logging
import subprocess
import time
import zlib

from . import native_ui

logger = logging.getLogger(__name__)

# Les notifications natives sont des processus courts. On garde leurs
# handles pour les moissonner, sinon chaque envoi laisse un zombie.
_CHILDREN: list[subprocess.Popen] = []


def _reap() -> None:
    _CHILDREN[:] = [child for child in _CHILDREN if child.poll() is None]


def _track(process: subprocess.Popen | None) -> subprocess.Popen | None:
    if process is not None:
        _CHILDREN.append(process)
    return process


def start_tray() -> subprocess.Popen | None:
    """Lance `checkmate-ui --tray` et verifie qu'il reste en vie."""
    process = native_ui.spawn("--tray")
    if process is None:
        return None
    time.sleep(0.4)
    code = process.poll()
    if code is None:
        logger.info("icone native demarree (pid %s)", process.pid)
        return process
    logger.warning(
        "icone native indisponible (code %s), repli sur l'icone Python", code
    )
    return None


def stop_tray(process: subprocess.Popen | None) -> None:
    """Arrete l'icone native, sans bloquer l'arret du moteur."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def _notification_id(title: str) -> int:
    return zlib.crc32(title.encode("utf-8")) & 0x7FFFFFFF


def notify(
    title: str,
    message: str,
    *,
    urgency: str = "critical",
    replace_id: int | None = None,
) -> bool | None:
    """Envoie via Rust, ou rend None pour laisser le repli Python."""
    if replace_id is None:
        replace_id = _notification_id(title)
    process = _track(
        native_ui.spawn(
            "notify",
            "--title",
            title,
            "--body",
            message,
            "--urgency",
            urgency,
            "--replace-id",
            str(replace_id),
        )
    )
    if process is None:
        return None
    # Laisse au helper le temps de signaler un service absent. Sous Windows,
    # il reste vivant pour capter le clic sur le toast.
    time.sleep(0.2)
    code = process.poll()
    if code is None or code == 0:
        return True
    logger.warning("notification native indisponible (code %s)", code)
    return None


def autostart(
    action: str,
    executable=None,
    config_path=None,
) -> bool | None:
    """Delegue enable, disable ou restart, ou rend None pour le repli Python."""
    command = ["autostart", action]
    if action == "enable":
        if executable is None or config_path is None:
            return None
        command.extend(
            ["--executable", str(executable), "--config", str(config_path)]
        )
    result = native_ui.run(*command)
    if result is None:
        return None
    if result.returncode == 0:
        return True
    detail = (result.stderr or result.stdout).strip()
    logger.warning("autostart natif %s echoue : %s", action, detail)
    return None


def autostart_enabled() -> bool | None:
    """Interroge l'etat natif, ou rend None pour le repli Python."""
    result = native_ui.run("autostart", "status")
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() == "enabled"
