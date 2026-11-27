"""Lancement de la coquille native GPUI.

Le binaire `checkmate-ui` est livre avec l'application. Il lit lui-meme
`runtime.json` et ne prend aucun argument obligatoire. Ce module le localise
et le lance ; si le binaire manque, l'appelant retombe sur la fenetre pywebview
puis le navigateur.

Le repli protege d'un paquet incomplet, ce n'est pas un drapeau opt-in : une
beta T1 publiee sans `checkmate-ui` est un paquet casse.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

BINARY_ENV = "CHECKMATE_UI_BINARY"


def binary_name() -> str:
    return (
        "checkmate-ui.exe"
        if sys.platform.startswith("win")
        else "checkmate-ui"
    )


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def candidates() -> list[Path]:
    """Emplacements essayes, dans l'ordre de priorite."""
    found: list[Path] = []
    override = os.environ.get(BINARY_ENV)
    if override:
        found.append(Path(override).expanduser())
    found.append(Path(sys.executable).resolve().parent / binary_name())
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        found.append(Path(bundle) / binary_name())
    root = _repository_root() / "rust" / "target"
    found.extend(
        [root / profile / binary_name() for profile in ("release", "debug")]
    )
    on_path = shutil.which(binary_name())
    if on_path:
        found.append(Path(on_path))
    return found


def locate() -> Path | None:
    """Premier binaire existant, ou None."""
    for candidate in candidates():
        if candidate.is_file():
            return candidate
    return None


def available() -> bool:
    return locate() is not None


def _spawn(binary: Path, args: tuple[str, ...]) -> bool:
    command = [str(binary), *args]
    options: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform.startswith("win"):
        options["creationflags"] = 0x00000008
    else:
        options["start_new_session"] = True
    try:
        subprocess.Popen(command, **options)
    except OSError as exc:
        logger.warning("lancement de %s impossible : %s", binary, exc)
        return False
    return True


def launch(*args: str) -> bool:
    """Lance le binaire s'il est present."""
    binary = locate()
    if binary is None:
        logger.debug("coquille native absente")
        return False
    return _spawn(binary, args)


def open_dashboard() -> bool:
    """Ouvre le tableau de bord natif."""
    return launch()


def open_setup() -> bool:
    """Ouvre l'assistant natif sur un serveur d'onboarding deja demarre."""
    return launch("--setup")
