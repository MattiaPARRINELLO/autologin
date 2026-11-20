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

from .updates import BETA_CHANNEL, STABLE_CHANNEL, TAG_PREFIX, parse_version

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


def channel_for_tag(tag: str) -> ReleaseChannel:
    """Rend le canal attendu pour un tag, ou leve ValueError si le tag est invalide."""
    if not TAG_PATTERN.match(tag):
        raise ValueError(f"tag de release attendu : {TAG_PREFIX}vX.Y.Z[-beta.N]")
    version = parse_version(tag)
    if version is None:
        raise ValueError(f"version illisible dans le tag {tag}")
    name = BETA_CHANNEL if version.is_beta else STABLE_CHANNEL
    return ReleaseChannel(
        name=name,
        expected_branch=EXPECTED_BRANCHES[name],
        prerelease=name == BETA_CHANNEL,
        version=f"{version.major}.{version.minor}.{version.patch}",
    )


def main(argv: list[str] | None = None) -> int:
    """Affiche le canal sous forme de variables pour `$GITHUB_OUTPUT`."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(
            f"usage : python -m checkmate_watcher.release_channel {TAG_PREFIX}vX.Y.Z",
            file=sys.stderr,
        )
        return 2
    try:
        channel = channel_for_tag(args[0])
    except ValueError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    print(f"channel={channel.name}")
    print(f"branch={channel.expected_branch}")
    print(f"version={channel.version}")
    print(f"prerelease={'true' if channel.prerelease else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
