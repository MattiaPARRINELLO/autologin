"""Installation d'une mise a jour deja telechargee et verifiee.

Le binaire ne pouvant pas se remplacer pendant qu'il tourne, l'installation est
deleguee a un processus detache : l'installeur Inno sous Windows, un petit
script shell sous Linux. Le dossier de telechargement est nettoye apres succes.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__
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
systemctl --user stop checkmate-watcher >/dev/null 2>&1 || true
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
tar -xzf {archive} -C "$WORK" || exit 1
cd "$WORK"/CheckMate-linux-* || exit 1
./install.sh
status=$?
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


def _install_linux(archive: Path, cleanup: Path) -> None:
    script = LINUX_SCRIPT.format(
        archive=_quote(str(archive)),
        cleanup=_quote(str(cleanup)),
    )
    handle, path = tempfile.mkstemp(prefix="checkmate-update-", suffix=".sh")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(script)
        os.chmod(path, 0o700)
        subprocess.Popen(
            ["/bin/bash", path],
            close_fds=True,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        Path(path).unlink(missing_ok=True)
        raise UpdateError(
            f"lancement du script de mise a jour impossible : {exc}"
        ) from exc


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def prepare(config) -> tuple[Release, Path]:
    """Verifie, telecharge et controle la mise a jour. Rend (version, archive)."""
    release = check_for_update(
        __version__,
        include_prerelease=config.updates.include_prerelease,
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
