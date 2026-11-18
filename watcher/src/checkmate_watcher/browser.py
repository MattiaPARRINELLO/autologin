"""Choix de l'executable Chromium et messages d'erreur associes."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Protocol

from .config import Config

logger = logging.getLogger(__name__)

SYSTEM_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "brave-browser",
)


class BrowserType(Protocol):
    @property
    def executable_path(self) -> str: ...


def system_chromium() -> str | None:
    for name in SYSTEM_CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


def resolve_executable(browser_type: BrowserType, config: Config) -> str | None:
    """Renvoie l'executable a passer a Playwright, ou None pour celui du bundle.

    Priorite : executable_path de la config, puis Chromium du bundle s'il est
    installe, puis un Chromium systeme en secours.
    """
    configured = config.watcher.executable_path
    if configured:
        return configured

    try:
        expected = browser_type.executable_path
    except Exception:  # noqa: BLE001
        expected = ""

    if expected and Path(expected).is_file():
        return None

    fallback = system_chromium()
    if fallback:
        logger.warning(
            "Chromium de Playwright absent (%s), utilisation de %s",
            expected or "chemin inconnu",
            fallback,
        )
        return fallback
    return None


def missing_browser_message() -> str:
    return (
        "Chromium introuvable. Deux solutions :\n"
        "  uv run playwright install chromium\n"
        "ou renseigner dans la configuration :\n"
        '  [watcher]\n  executable_path = "/usr/bin/chromium"'
    )
