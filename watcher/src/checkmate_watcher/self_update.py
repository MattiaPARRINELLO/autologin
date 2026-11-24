"""Installation d'une mise a jour deja telechargee et verifiee.

Le binaire ne pouvant pas se remplacer pendant qu'il tourne, l'installation est
deleguee a un processus detache : l'installeur Inno sous Windows, un petit
script shell sous Linux. Le dossier de telechargement est nettoye apres succes.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import __version__
from .autostart import UNIT_NAME
from .paths import default_update_dir
from .updates import (
    Release,
    UpdateError,
    check_for_update,
    download_update,
)

logger = logging.getLogger(__name__)

WINDOWS_FLAGS = [
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/CLOSEAPPLICATIONS",
]

LINUX_SCRIPT = """#!/usr/bin/env bash
set -u
sleep 2
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
# Arreter le service ne tue ce script que s'il tourne dans la meme unite que le
# watcher. C'est le cas quand systemd-run n'a pas pu detacher l'installation.
if [ -n "${{CHECKMATE_UPDATE_DETACHED:-}}" ]; then
    systemctl --user stop {unit} >/dev/null 2>&1 || true
fi
status=1
if tar -xzf {archive} -C "$WORK"; then
    cd "$WORK"/CheckMate-linux-* && ./install.sh
    status=$?
fi
# L'installeur redemarre deja le service, mais si l'installation echoue il faut
# rendre la main a l'ancienne version plutot que de laisser le service arrete.
systemctl --user start {unit} >/dev/null 2>&1 || true
if [ "$status" -eq 0 ]; then
    rm -rf {cleanup}
fi
exit "$status"
"""


def install(archive: Path, *, cleanup: Path | None = None) -> None:
    """Lance l'installation en arriere-plan puis rend la main."""
    if not archive.is_file():
        raise UpdateError("paquet de mise a jour introuvable")
    if sys.platform.startswith("win"):
        _install_windows(archive)
    elif sys.platform.startswith("linux"):
        _install_linux(archive, cleanup or archive.parent)
    else:
        raise UpdateError("mise a jour automatique indisponible sur ce systeme")


def _install_windows(archive: Path) -> None:
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            [str(archive), *WINDOWS_FLAGS],
            close_fds=True,
            creationflags=flags,
        )
    except OSError as exc:
        raise UpdateError(f"lancement de l'installeur impossible : {exc}") from exc


def _write_update_script(archive, cleanup):
    # fmt: off
    handle, path = tempfile.mkstemp(prefix="checkmate-update-", suffix=".sh")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(LINUX_SCRIPT.format(archive=_quote(str(archive)), cleanup=_quote(str(cleanup)), unit=UNIT_NAME))
        os.chmod(path, 0o700)
        return path
    except OSError:
        Path(path).unlink(missing_ok=True)
        raise
    # fmt: on


def _install_linux(archive: Path, cleanup: Path) -> None:
    try:
        path = _write_update_script(archive, cleanup)
        _spawn_linux_installer(path)
    except OSError as exc:
        raise UpdateError(
            f"lancement du script de mise a jour impossible : {exc}"
        ) from exc


def _try_systemd_run(script, unit):
    # fmt: off
    runner = shutil.which("systemd-run")
    if runner is None: return False
    try:
        subprocess.Popen([runner, "--user", "--collect", "--quiet", f"--unit={unit}", "--description=Installation d'une mise a jour CheckMate", "--setenv=CHECKMATE_UPDATE_DETACHED=1", "/bin/bash", script], close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        logger.warning("systemd-run indisponible, installation non detachee"); return False
    if _transient_unit_active(unit): return True
    logger.warning("unite %s inactive, installation dans le cgroup du service", unit)
    return False
    # fmt: on


def _spawn_detached(argv: list[str]) -> None:
    subprocess.Popen(
        argv,
        close_fds=True,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _spawn_linux_installer(script: str) -> None:
    """Detache l'installation du service pour qu'elle lui survive."""
    unit = f"checkmate-update-{os.getpid()}"
    if _try_systemd_run(script, unit):
        return
    _spawn_detached(["/bin/bash", script])


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _transient_unit_active(unit: str, attempts: int = 5) -> bool:
    # fmt: off
    for attempt in range(attempts):
        try:
            result = subprocess.run(["systemctl", "--user", "show", "--property=ActiveState", "--value", unit], capture_output=True, text=True, timeout=2, check=False)
        except (OSError, subprocess.SubprocessError):
            return False
        state = result.stdout.strip()
        if state in {"active", "activating"}: return True
        if state in {"inactive", "failed"} and attempt >= 1: return False
        time.sleep(0.2)
    return False
    # fmt: on


def prepare(config) -> tuple[Release, Path]:
    """Verifie, telecharge et controle la mise a jour. Rend (version, archive)."""
    release = check_for_update(
        __version__,
        channel=config.updates.channel,
    )
    if release is None:
        raise UpdateError(f"CheckMate {__version__} est deja a jour")
    directory = default_update_dir() / release.version_text
    archive = download_update(release, directory)
    return release, archive


def update_now(config) -> str:
    """Prepare puis lance l'installation. Rend le numero de version installe."""
    release, archive = prepare(config)
    install(archive)
    return release.version_text
