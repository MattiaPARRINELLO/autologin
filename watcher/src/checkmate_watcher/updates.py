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
    migration_reason: str | None = None
    required_reason: str | None = None
    markers_declared: bool = False

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
MARKER_PATTERN = re.compile(
    r"^\s*CHECKMATE-(MIGRATION|REQUIRED)\s*:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _release_markers(body: object) -> tuple[str | None, str | None, bool]:
    values = {"MIGRATION": None, "REQUIRED": None}
    seen = set()
    for match in MARKER_PATTERN.finditer(str(body or "")):
        kind = match.group(1).upper()
        reason = match.group(2).strip()
        seen.add(kind)
        values[kind] = None if reason == "0" else reason
    return values["MIGRATION"], values["REQUIRED"], seen == {"MIGRATION", "REQUIRED"}


def parse_version(text: str) -> Version | None:
    """Lit une version X.Y.Z ou X.Y.Z-beta.N, ordonnable."""
    match = VERSION_PATTERN.search(text or "")
    if not match:
        return None
    major, minor, patch = (int(part) for part in match.groups()[:3])
    if match.group(4):
        number = int(match.group(5) or 1)
        return Version(major, minor, patch, stage=0, number=number)
    return Version(major, minor, patch)


def _release_assets(assets):
    return tuple(
        Asset(
            name=str(a.get("name") or ""),
            url=str(a.get("browser_download_url") or ""),
            size=int(a.get("size") or 0),
        )
        for a in assets
        if isinstance(a, dict) and a.get("name")
    )


def _release_downloads(assets):
    return sum(int(a.get("download_count") or 0) for a in assets if isinstance(a, dict))


def _marker_fields(body) -> dict:
    migration, required, declared = _release_markers(body)
    return {
        "migration_reason": migration,
        "required_reason": required,
        "markers_declared": declared,
    }


def _build_release(tag, version, data, assets):
    return Release(
        tag=tag,
        version=version,
        url=str(data.get("html_url") or ""),
        name=str(data.get("name") or tag),
        prerelease=bool(data.get("prerelease")),
        downloads=_release_downloads(assets),
        assets=_release_assets(assets),
        **_marker_fields(data.get("body")),
    )


def parse_release(data: dict) -> Release | None:
    tag = str(data.get("tag_name") or "")
    if not tag.startswith(TAG_PREFIX):
        return None
    version = parse_version(tag)
    if version is None:
        return None
    return _build_release(tag, version, data, data.get("assets") or [])


def _channel_candidates(releases: list[Release], channel: str) -> list[Release]:
    accept_prerelease = str(channel).strip().lower() == BETA_CHANNEL
    return [
        release for release in releases if accept_prerelease or not release.prerelease
    ]


def select_latest(
    releases: list[Release],
    *,
    channel: str = STABLE_CHANNEL,
) -> Release | None:
    candidates = _channel_candidates(releases, channel)
    if not candidates:
        return None
    return max(candidates, key=lambda release: release.version)


@dataclass(frozen=True)
class UpdatePolicy:
    current: Version | None
    latest: Release | None
    required: Release | None
    migration: Release | None
    channel: str

    @property
    def available(self) -> bool:
        return (
            self.current is not None
            and self.latest is not None
            and self.latest.version > self.current
        )

    @property
    def install_target(self) -> Release | None:
        """La migration a passer d'abord, sinon la derniere version disponible."""
        return self.migration or (self.latest if self.available else None)


def _required_release(window):
    return max(
        (release for release in window if release.required_reason),
        key=lambda release: release.version,
        default=None,
    )


def _migration_release(window):
    return min(
        (release for release in window if release.migration_reason),
        key=lambda release: release.version,
        default=None,
    )


def _policy_for(current, channel, releases) -> UpdatePolicy:
    candidates = _channel_candidates(releases, channel)
    latest = max(candidates, key=lambda release: release.version, default=None)
    window = [release for release in candidates if release.version > current]
    required = _required_release(window)
    migration = _migration_release(window)
    return UpdatePolicy(current, latest, required, migration, channel)


def update_policy(current, *, channel=STABLE_CHANNEL, releases=None):
    """Resume la cible, la version minimale exigee et la migration a passer."""
    current_version = parse_version(str(current))
    if current_version is None:
        return UpdatePolicy(None, None, None, None, channel)
    available = releases if releases is not None else fetch_releases()
    return _policy_for(current_version, channel, available)


def _releases_request(timeout: int):
    return urllib.request.Request(
        RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
    )


def fetch_releases(timeout: int = 10) -> list[Release]:
    with urllib.request.urlopen(
        _releases_request(timeout), timeout=timeout
    ) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, list):
        return []
    return [r for r in (parse_release(i) for i in payload) if r is not None]


def check_for_update(
    current: str = __version__,
    *,
    channel: str = STABLE_CHANNEL,
    releases: list[Release] | None = None,
) -> Release | None:
    policy = update_policy(current, channel=channel, releases=releases)
    return policy.latest if policy.available else None


def platform_asset(release: Release, platform: str) -> Asset | None:
    """Choisit l'artefact a installer pour la plateforme courante."""
    if platform.startswith("win"):
        return release.find_asset(WINDOWS_PREFIX, ".exe")
    if platform.startswith("linux"):
        return release.find_asset(LINUX_PREFIX, ".tar.gz")
    return None


def _ecrire_morceau(handle, chunk) -> None:
    handle.write(chunk)


def _download_chunks(response, handle):
    while True:
        chunk = response.read(256 * 1024)
        if not chunk:
            break
        _ecrire_morceau(handle, chunk)


def download(url: str, destination: Path, *, timeout: int = 60) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with (
        urllib.request.urlopen(request, timeout=timeout) as response,
        destination.open("wb") as handle,
    ):
        _download_chunks(response, handle)
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


def _download_update_asset(release, platform):
    asset = platform_asset(release, platform)
    if asset is None:
        raise UpdateError("aucun paquet pour cette plateforme")
    return asset


def download_update(
    release: Release, directory: Path, *, platform: str | None = None
) -> Path:
    """Telecharge l'artefact et verifie sa somme. Rend le chemin local."""
    platform = platform or sys.platform
    asset = _download_update_asset(release, platform)
    target = directory / asset.name
    download(asset.url, target)
    checksums_asset = release.asset(CHECKSUMS_NAME)
    if checksums_asset is None:
        raise UpdateError("sommes de controle absentes de la release")
    sums_path = download(checksums_asset.url, directory / CHECKSUMS_NAME)
    verify_checksum(target, parse_checksums(sums_path.read_text(encoding="utf-8")))
    return target
