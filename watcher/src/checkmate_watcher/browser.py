"""Choix du navigateur Chromium selon la plateforme et la configuration."""

from __future__ import annotations

import logging
import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import Config

logger = logging.getLogger(__name__)

LINUX_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "brave-browser",
)

WINDOWS_CANDIDATES = (
    (r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe", "msedge"),
    (r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe", "msedge"),
    (r"%ProgramFiles%\Google\Chrome\Application\chrome.exe", "chrome"),
    (r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe", "chrome"),
    (r"%LocalAppData%\Google\Chrome\Application\chrome.exe", "chrome"),
)

MAC_CANDIDATES = (
    (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "chrome",
    ),
    ("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "msedge"),
)


class BrowserType(Protocol):
    @property
    def executable_path(self) -> str: ...


@dataclass(frozen=True)
class LaunchOptions:
    executable_path: str | None = None
    channel: str | None = None

    def as_kwargs(self) -> dict[str, str]:
        if self.executable_path:
            return {"executable_path": self.executable_path}
        if self.channel:
            return {"channel": self.channel}
        return {}


def system_chromium() -> str | None:
    for name in LINUX_CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


def _existing_channel(
    candidates: tuple[tuple[str, str], ...],
    exists: Callable[[Path], bool],
) -> str | None:
    for raw_path, channel in candidates:
        path = Path(os.path.expandvars(raw_path))
        if exists(path):
            return channel
    return None


def platform_channel(
    platform: str, exists: Callable[[Path], bool] | None = None
) -> str | None:
    probe = exists or (lambda path: path.is_file())
    if platform.startswith("win"):
        return _existing_channel(WINDOWS_CANDIDATES, probe)
    if platform == "darwin":
        return _existing_channel(MAC_CANDIDATES, probe)
    return None


def resolve_launch_options(
    browser_type: BrowserType,
    config: Config,
    platform: str | None = None,
) -> LaunchOptions:
    """Priorite : config, Chromium du bundle, navigateur systeme."""
    configured = config.watcher.executable_path
    if configured:
        return LaunchOptions(executable_path=configured)

    try:
        expected = browser_type.executable_path
    except Exception:  # noqa: BLE001
        expected = ""

    if expected and Path(expected).is_file():
        return LaunchOptions()

    current = platform or sys.platform
    channel = platform_channel(current)
    if channel:
        logger.info("utilisation du navigateur systeme : %s", channel)
        return LaunchOptions(channel=channel)

    if current.startswith("linux"):
        fallback = system_chromium()
        if fallback:
            logger.warning(
                "Chromium de Playwright absent (%s), utilisation de %s",
                expected or "chemin inconnu",
                fallback,
            )
            return LaunchOptions(executable_path=fallback)

    return LaunchOptions()


def missing_browser_message() -> str:
    return (
        "Navigateur introuvable. Trois solutions :\n"
        "  uv run playwright install chromium\n"
        "ou installer Microsoft Edge / Google Chrome,\n"
        "ou renseigner dans la configuration :\n"
        '  [watcher]\n  executable_path = "/usr/bin/chromium"'
    )
