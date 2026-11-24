"""Verification des mises a jour publiees sur GitHub."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__

GITHUB_REPO = "MattiaPARRINELLO/autologin"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=30"
TAG_PREFIX = "watcher-"
STABLE_CHANNEL = "stable"
BETA_CHANNEL = "beta"
CHANNELS = (STABLE_CHANNEL, BETA_CHANNEL)
USER_AGENT = "checkmate-watcher"
CHECKSUMS_NAME = "SHA256SUMS.txt"
LINUX_PREFIX = "CheckMate-linux-"
WINDOWS_PREFIX = "CheckMate-Setup-"


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int = 0


@dataclass(frozen=True, order=True)
class Version:
    """Version ordonnable : une beta precede toujours sa version stable."""

    major: int
    minor: int
    patch: int
    stage: int = 1  # 0 = beta, 1 = stable
    number: int = 0

    @property
    def is_beta(self) -> bool:
        return self.stage == 0

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.is_beta:
            return f"{base}-beta.{self.number}"
        return base


@dataclass(frozen=True)
class Release:
    tag: str
    version: Version
    url: str
    name: str
    prerelease: bool
    downloads: int = 0
    assets: tuple[Asset, ...] = field(default_factory=tuple)

    @property
    def version_text(self) -> str:
        return str(self.version)

    def asset(self, name: str) -> Asset | None:
        for item in self.assets:
            if item.name == name:
                return item
        return None

    def find_asset(self, prefix: str, suffix: str) -> Asset | None:
        for item in self.assets:
            if item.name.startswith(prefix) and item.name.endswith(suffix):
                return item
        return None


VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:-(beta)(?:\.?(\d+))?)?")


def parse_version(text: str) -> Version | None:
    """Lit une version X.Y.Z ou X.Y.Z-beta.N, ordonnable.

    Une beta est strictement inferieure a sa version stable, et deux betas
    successives sont ordonnees. Les tags historiques sans suffixe restent lus
    comme des versions stables.
    """
    match = VERSION_PATTERN.search(text or "")
    if not match:
        return None
    major, minor, patch = (int(part) for part in match.groups()[:3])
    if match.group(4):
        number = int(match.group(5) or 1)
        return Version(major, minor, patch, stage=0, number=number)
    return Version(major, minor, patch)


def parse_release(data: dict) -> Release | None:
    tag = str(data.get("tag_name") or "")
    if not tag.startswith(TAG_PREFIX):
        return None
    version = parse_version(tag)
    if version is None:
        return None
    assets = data.get("assets") or []
    downloads = sum(
        int(asset.get("download_count") or 0)
        for asset in assets
        if isinstance(asset, dict)
    )
    parsed = tuple(
        Asset(
            name=str(asset.get("name") or ""),
            url=str(asset.get("browser_download_url") or ""),
            size=int(asset.get("size") or 0),
        )
        for asset in assets
        if isinstance(asset, dict) and asset.get("name")
    )
    return Release(
        tag=tag,
        version=version,
        url=str(data.get("html_url") or ""),
        name=str(data.get("name") or tag),
        prerelease=bool(data.get("prerelease")),
        downloads=downloads,
        assets=parsed,
    )


def select_latest(
    releases: list[Release],
    *,
    channel: str = STABLE_CHANNEL,
) -> Release | None:
    accept_prerelease = str(channel).strip().lower() == BETA_CHANNEL
    candidates = [
        release for release in releases if accept_prerelease or not release.prerelease
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
    channel: str = STABLE_CHANNEL,
    releases: list[Release] | None = None,
) -> Release | None:
    current_version = parse_version(current)
    if current_version is None:
        return None
    if releases is None:
        releases = fetch_releases()
    latest = select_latest(releases, channel=channel)
    if latest is None:
        return None
    if latest.version > current_version:
        return latest
    return None


def platform_asset(release: Release, platform: str) -> Asset | None:
    """Choisit l'artefact a installer pour la plateforme courante."""
    if platform.startswith("win"):
        return release.find_asset(WINDOWS_PREFIX, ".exe")
    if platform.startswith("linux"):
        return release.find_asset(LINUX_PREFIX, ".tar.gz")
    return None


def _ecrire_morceau(handle, chunk) -> None:
    handle.write(chunk)


def download(url: str, destination: Path, *, timeout: int = 60) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with (
        urllib.request.urlopen(request, timeout=timeout) as response,
        destination.open("wb") as handle,
    ):
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            _ecrire_morceau(handle, chunk)
    return destination


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksums(text: str) -> dict[str, str]:
    """Lit un fichier `sha256sum` : somme puis nom de fichier."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        digest, name = parts[0].lower(), parts[-1].lstrip("*")
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            result[name] = digest
    return result


def verify_checksum(path: Path, checksums: dict[str, str]) -> None:
    expected = checksums.get(path.name)
    if expected is None:
        raise UpdateError(f"somme absente pour {path.name}")
    actual = sha256_file(path)
    if actual != expected:
        raise UpdateError("somme SHA256 invalide, telechargement corrompu")


class UpdateError(Exception):
    """Mise a jour impossible."""


def download_update(
    release: Release, directory: Path, *, platform: str | None = None
) -> Path:
    """Telecharge l'artefact et verifie sa somme. Rend le chemin local."""
    platform = platform or sys.platform
    asset = platform_asset(release, platform)
    if asset is None:
        raise UpdateError("aucun paquet pour cette plateforme")
    target = directory / asset.name
    download(asset.url, target)
    checksums_asset = release.asset(CHECKSUMS_NAME)
    if checksums_asset is None:
        raise UpdateError("sommes de controle absentes de la release")
    sums_path = download(checksums_asset.url, directory / CHECKSUMS_NAME)
    checksums = parse_checksums(sums_path.read_text(encoding="utf-8"))
    verify_checksum(target, checksums)
    return target
