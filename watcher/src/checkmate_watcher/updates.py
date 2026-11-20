"""Verification des mises a jour publiees sur GitHub."""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from . import __version__

GITHUB_REPO = "MattiaPARRINELLO/autologin"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=30"
TAG_PREFIX = "watcher-"
USER_AGENT = "checkmate-watcher"


@dataclass(frozen=True)
class Release:
    tag: str
    version: tuple[int, int, int]
    url: str
    name: str
    prerelease: bool

    @property
    def version_text(self) -> str:
        return ".".join(str(part) for part in self.version)


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def parse_release(data: dict) -> Release | None:
    tag = str(data.get("tag_name") or "")
    if not tag.startswith(TAG_PREFIX):
        return None
    version = parse_version(tag)
    if version is None:
        return None
    return Release(
        tag=tag,
        version=version,
        url=str(data.get("html_url") or ""),
        name=str(data.get("name") or tag),
        prerelease=bool(data.get("prerelease")),
    )


def select_latest(
    releases: list[Release],
    *,
    include_prerelease: bool = True,
) -> Release | None:
    candidates = [
        release for release in releases if include_prerelease or not release.prerelease
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda release: release.version)


def fetch_releases(timeout: int = 10) -> list[Release]:
    request = urllib.request.Request(
        RELEASES_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, list):
        return []
    return [
        release
        for release in (parse_release(item) for item in payload)
        if release is not None
    ]


def check_for_update(
    current: str = __version__,
    *,
    include_prerelease: bool = True,
    releases: list[Release] | None = None,
) -> Release | None:
    current_version = parse_version(current)
    if current_version is None:
        return None
    if releases is None:
        releases = fetch_releases()
    latest = select_latest(releases, include_prerelease=include_prerelease)
    if latest is None:
        return None
    if latest.version > current_version:
        return latest
    return None
