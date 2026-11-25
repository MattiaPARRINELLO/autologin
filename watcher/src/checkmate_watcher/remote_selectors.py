"""Selecteurs CESAR distants, valides et mis en cache localement."""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import asdict, replace
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__
from .config import Config, Selectors
from .file_io import write_private_json
from .paths import default_selectors_cache_file
from .updates import parse_version

logger = logging.getLogger(__name__)

REMOTE_SELECTORS_URL = (
    "https://raw.githubusercontent.com/MattiaPARRINELLO/autologin/"
    "main/watcher/selectors.json"
)
MAX_PAYLOAD_BYTES = 65_536
SELECTOR_NAMES = frozenset(Selectors.__dataclass_fields__)


def _selector_is_safe(value: str) -> bool:
    lowered = value.strip().lower()
    if "://" in lowered or lowered.startswith("javascript:"):
        return False
    return "<script" not in lowered


def _validate_payload(
    payload: object, current_version: str
) -> dict[str, list[str]]:
    if not isinstance(payload, dict):
        raise TypeError("chargement des selecteurs : objet JSON attendu")
    current = parse_version(current_version)
    minimum = parse_version(str(payload.get("min_version", "0.0.0")))
    if current is None or minimum is None or minimum > current:
        raise ValueError("chargement des selecteurs : version incompatible")
    selectors = payload.get("selectors")
    if not isinstance(selectors, dict):
        raise TypeError("chargement des selecteurs : table absente")
    unknown = set(selectors) - SELECTOR_NAMES
    if unknown:
        raise ValueError("chargement des selecteurs : cles inconnues")
    validated = {}
    for name, values in selectors.items():
        if not isinstance(values, list) or not values:
            raise ValueError(f"selecteur {name} : liste vide attendue")
        if not all(isinstance(item, str) and item.strip() for item in values):
            raise ValueError(f"selecteur {name} : chaines non vides attendues")
        if not all(_selector_is_safe(item) for item in values):
            raise ValueError(f"selecteur {name} : contenu interdit")
        validated[name] = [item.strip() for item in values]
    return validated


def _fetch_payload(url: str, timeout: float) -> object:
    if urlsplit(url).scheme != "https":
        raise ValueError("chargement des selecteurs : HTTPS obligatoire")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": f"CheckMate/{__version__}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_PAYLOAD_BYTES + 1)
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError("chargement des selecteurs : fichier trop volumineux")
    return json.loads(raw)


def _read_cache(path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_remote_selectors(
    current_version: str = __version__,
    cache_path=None,
    *,
    url: str = REMOTE_SELECTORS_URL,
    timeout: float = 2.0,
) -> dict[str, list[str]]:
    cache_path = (
        Path(cache_path) if cache_path else default_selectors_cache_file()
    )
    try:
        payload = _fetch_payload(url, timeout)
        selectors = _validate_payload(payload, current_version)
        write_private_json(cache_path, payload)
        logger.info("selecteurs CESAR distants charges")
        return selectors
    except Exception as exc:
        logger.debug("selecteurs distants indisponibles : %s", exc)
    try:
        payload = _read_cache(cache_path)
        selectors = _validate_payload(payload, current_version)
        logger.info("selecteurs CESAR charges depuis le cache local")
        return selectors
    except Exception as exc:
        logger.debug("cache de selecteurs indisponible : %s", exc)
    return {}


def with_remote_selectors(config: Config) -> Config:
    disabled = os.environ.get("CHECKMATE_REMOTE_SELECTORS", "1")
    if disabled.strip().lower() in {"0", "false", "non", "off"}:
        return config
    remote = load_remote_selectors(__version__)
    if not remote:
        return config
    local = asdict(config.selectors)
    return replace(config, selectors=Selectors.from_dict({**local, **remote}))
