"""Determine le canal de publication a partir d'un tag de release.

Le workflow de release s'appuie sur cette logique testable : un tag
`watcher-vX.Y.Z-beta.N` part du canal beta, un tag `watcher-vX.Y.Z` du canal
stable. Le suffixe ne remplace pas le booleen `prerelease` de l'API GitHub, qui
reste la source de verite pour classer les releases deja publiees.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

from .updates import (
    BETA_CHANNEL,
    STABLE_CHANNEL,
    TAG_PREFIX,
    Version,
    parse_version,
)

EXPECTED_BRANCHES = {
    STABLE_CHANNEL: "main",
    BETA_CHANNEL: "beta",
}

TAG_PATTERN = re.compile(
    r"^" + re.escape(TAG_PREFIX) + r"v\d+\.\d+\.\d+(?:-beta\.?\d+)?$"
)


@dataclass(frozen=True)
class ReleaseChannel:
    name: str
    expected_branch: str
    prerelease: bool
    version: str


def _version_from_tag(tag: str) -> Version:
    if not TAG_PATTERN.match(tag):
        raise ValueError(f"tag de release attendu : {TAG_PREFIX}vX.Y.Z[-beta.N]")
    version = parse_version(tag)
    if version is None:
        raise ValueError(f"version illisible dans le tag {tag}")
    return version


def _channel_from_version(version: Version) -> ReleaseChannel:
    name = BETA_CHANNEL if version.is_beta else STABLE_CHANNEL
    return ReleaseChannel(
        name=name,
        expected_branch=EXPECTED_BRANCHES[name],
        prerelease=name == BETA_CHANNEL,
        version=f"{version.major}.{version.minor}.{version.patch}",
    )


def channel_for_tag(tag: str) -> ReleaseChannel:
    """Rend le canal attendu pour un tag, ou leve ValueError si le tag est invalide."""
    return _channel_from_version(_version_from_tag(tag))


def _afficher_usage() -> None:
    print(
        f"usage : python -m checkmate_watcher.release_channel {TAG_PREFIX}vX.Y.Z",
        file=sys.stderr,
    )


def _afficher_erreur(exc: Exception) -> None:
    print(f"erreur : {exc}", file=sys.stderr)


def _afficher_canal(channel: ReleaseChannel) -> None:
    print(f"channel={channel.name}")
    print(f"branch={channel.expected_branch}")
    print(f"version={channel.version}")
    print(f"prerelease={'true' if channel.prerelease else 'false'}")


def _parse_args(argv: list[str] | None) -> list[str]:
    """Rend les arguments a analyser, par defaut ceux de la ligne de commande."""
    return sys.argv[1:] if argv is None else argv


def _resolve_channel(tags: list[str]) -> tuple[int, ReleaseChannel | None]:
    """Valide le tag unique et rend le code de sortie avec le canal associe."""
    if len(tags) != 1:
        _afficher_usage()
        return 2, None
    try:
        channel = channel_for_tag(tags[0])
    except ValueError as exc:
        _afficher_erreur(exc)
        return 1, None
    return 0, channel


def main(argv: list[str] | None = None) -> int:
    """Affiche le canal sous forme de variables pour `$GITHUB_OUTPUT`."""
    code, channel = _resolve_channel(_parse_args(argv))
    if channel is not None:
        _afficher_canal(channel)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
