"""Selecteurs CSS distants, mis en cache localement.

Le fichier distant ne peut contenir que des selecteurs CSS. Aucune URL, aucun
JavaScript, aucune cle inconnue : tout fichier invalide est ignore en bloc.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import __version__
from .config import DEFAULT_SELECTORS, ConfigError, Selectors
from .paths import data_dir
from .updates import parse_version

logger = logging.getLogger(__name__)

REMOTE_URL = (
    "https://raw.githubusercontent.com/MattiaPARRINELLO/autologin/main/selectors.json"
)
MAX_BYTES = 20_000
MAX_ITEMS = 6
MAX_LENGTH = 200
TIMEOUT_SECONDS = 5

# Ces motifs n'ont rien a faire dans un selecteur CSS et trahissent une tentative
# d'injection (CSS exotique ou code executable).
FORBIDDEN = ("javascript:", "url(", "@import", "<", ">", "expression(")


@dataclass(frozen=True)
class RemoteSelectors:
    selectors: dict[str, tuple[str, ...]] = field(default_factory=dict)
    min_version: str | None = None
    updated: str | None = None

    def __bool__(self) -> bool:
        return bool(self.selectors)


def cache_path() -> Path:
    return data_dir() / "selectors-cache.json"


def _clean_selector(value) -> str:
    if not isinstance(value, str):
        raise ConfigError("un selecteur doit etre une chaine")
    text = value.strip()
    if not text or len(text) > MAX_LENGTH:
        raise ConfigError("selecteur vide ou trop long")
    if any(char in text for char in ("\n", "\r", "\t")) or any(
        ord(char) < 32 for char in text
    ):
        raise ConfigError("selecteur avec caracteres de controle")
    lowered = text.lower()
    if any(pattern in lowered for pattern in FORBIDDEN):
        raise ConfigError(f"selecteur interdit : {text}")
    return text


def parse(payload: object) -> RemoteSelectors:
    if not isinstance(payload, dict):
        raise ConfigError("le fichier de selecteurs doit etre un objet JSON")
    raw = payload.get("selectors")
    if not isinstance(raw, dict):
        raise ConfigError("selecteurs absents")
    if len(raw) > len(DEFAULT_SELECTORS):
        raise ConfigError("trop de groupes de selecteurs")

    selectors: dict[str, tuple[str, ...]] = {}
    for key, values in raw.items():
        if key not in DEFAULT_SELECTORS:
            raise ConfigError(f"groupe de selecteurs inconnu : {key}")
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list) or not 1 <= len(values) <= MAX_ITEMS:
            raise ConfigError(f"selecteurs.{key} doit contenir 1 a {MAX_ITEMS} entrees")
        selectors[key] = tuple(_clean_selector(item) for item in values)

    min_version = payload.get("min_version")
    if min_version is not None and (
        not isinstance(min_version, str) or parse_version(min_version) is None
    ):
        raise ConfigError("min_version invalide")

    updated = payload.get("updated")
    if updated is not None and not isinstance(updated, str):
        raise ConfigError("updated invalide")

    return RemoteSelectors(
        selectors=selectors, min_version=min_version, updated=updated
    )


def apply(config, remote: RemoteSelectors):
    """Renvoie une configuration avec les selecteurs distants fusionnes."""
    if not remote:
        return config
    merged = {key: getattr(config.selectors, key) for key in DEFAULT_SELECTORS}
    merged.update(remote.selectors)
    return replace(config, selectors=Selectors(**merged))


def _read(url: str, timeout: int) -> bytes:
    if not url.startswith("https://raw.githubusercontent.com/"):
        raise ValueError("domaine de selecteurs non autorise")
    request = urllib.request.Request(
        url, headers={"User-Agent": f"checkmate-watcher/{__version__}"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("fichier de selecteurs trop volumineux")
    return body


def load(
    *,
    url: str = REMOTE_URL,
    path: Path | None = None,
    timeout: int = TIMEOUT_SECONDS,
) -> RemoteSelectors:
    """Recupere le fichier distant, sinon le cache, sinon rien."""
    cache = path or cache_path()
    try:
        body = _read(url, timeout)
        remote = parse(json.loads(body))
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(body.decode("utf-8"), encoding="utf-8")
        except OSError as exc:
            logger.debug("cache des selecteurs non ecrit : %s", exc)
        logger.info("selecteurs distants charges (%s)", remote.updated or "sans date")
        return remote
    except (urllib.error.URLError, OSError, ValueError, ConfigError) as exc:
        logger.debug("selecteurs distants indisponibles : %s", exc)

    try:
        return parse(json.loads(cache.read_text(encoding="utf-8")))
    except (OSError, ValueError, ConfigError) as exc:
        logger.debug("cache des selecteurs inutilisable : %s", exc)
    return RemoteSelectors()


def requires_update(remote: RemoteSelectors, current: str = __version__) -> bool:
    if not remote.min_version:
        return False
    minimum = parse_version(remote.min_version)
    actual = parse_version(current)
    if minimum is None or actual is None:
        return False
    return actual < minimum
