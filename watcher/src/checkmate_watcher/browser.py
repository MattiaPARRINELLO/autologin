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
    (
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "msedge",
    ),
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


def _windows_playwright_cache() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData/Local")
    return Path(base) / "ms-playwright"


def playwright_cache_dir(platform: str | None = None) -> Path:
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override and override != "0":
        return Path(override)
    current = platform or sys.platform
    if current.startswith("win"):
        return _windows_playwright_cache()
    if current == "darwin":
        return Path.home() / "Library/Caches/ms-playwright"
    return Path.home() / ".cache/ms-playwright"


BUNDLED_CHROMIUM_PATTERNS = (
    "chromium-*/chrome-linux*/chrome",
    "chromium-*/chrome-win*/chrome.exe",
    "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
)


def bundled_chromium_path(
    platform: str | None = None,
    root: Path | None = None,
) -> str | None:
    """Chemin du Chromium installe par `playwright install chromium`."""
    cache = root or playwright_cache_dir(platform)
    for pattern in BUNDLED_CHROMIUM_PATTERNS:
        for candidate in sorted(cache.glob(pattern)):
            if candidate.is_file():
                return str(candidate)
    return None


def bundled_browser_present(
    platform: str | None = None,
    root: Path | None = None,
) -> bool:
    return bundled_chromium_path(platform, root) is not None


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


def _expected_executable(browser_type: BrowserType) -> str:
    try:
        return browser_type.executable_path
    except Exception:
        return ""


def _playwright_missing(expected: str) -> bool:
    return not (expected and Path(expected).is_file())


def _system_launch(current: str) -> LaunchOptions | None:
    channel = platform_channel(current)
    if not channel:
        return None
    logger.info("utilisation du navigateur systeme : %s", channel)
    return LaunchOptions(channel=channel)


def _log_fallback(expected: str, fallback: str) -> None:
    logger.warning(
        "Chromium de Playwright absent (%s), utilisation de %s",
        expected or "chemin inconnu",
        fallback,
    )


def _linux_fallback(current: str, expected: str) -> LaunchOptions | None:
    if not current.startswith("linux"):
        return None
    fallback = system_chromium()
    if not fallback:
        return None
    _log_fallback(expected, fallback)
    return LaunchOptions(executable_path=fallback)


def _bundle_available(browser_type: BrowserType) -> bool:
    expected = _expected_executable(browser_type)
    return not _playwright_missing(expected)


def _default_launch(current: str, expected: str) -> LaunchOptions:
    system = _system_launch(current)
    if system:
        return system
    return _linux_fallback(current, expected) or LaunchOptions()


def resolve_launch_options(
    browser_type: BrowserType,
    executable_path: str | None = None,
    platform: str | None = None,
) -> LaunchOptions:
    # Priorite : chemin configure, Chromium du bundle, navigateur systeme.
    if executable_path:
        return LaunchOptions(executable_path=executable_path)
    if _bundle_available(browser_type):
        return LaunchOptions()
    current = platform or sys.platform
    return _default_launch(current, _expected_executable(browser_type))


def missing_browser_message() -> str:
    return (
        "Navigateur introuvable. Trois solutions :\n"
        "  uv run playwright install chromium\n"
        "ou installer Microsoft Edge / Google Chrome,\n"
        "ou renseigner dans la configuration :\n"
        '  [watcher]\n  executable_path = "/usr/bin/chromium"'
    )
