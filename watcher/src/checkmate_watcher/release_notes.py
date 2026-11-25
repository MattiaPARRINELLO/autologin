"""Resumes versionnes affiches apres les mises a jour importantes."""

from __future__ import annotations

import json
import logging
from importlib.resources import files

from .updates import parse_version

logger = logging.getLogger(__name__)

NOTES_RESOURCE = "release_notes.json"
LAST_VERSION_KEY = "app.last_version"
CELEBRATED_VERSION_KEY = "release.celebrated_version"


def _read_payload() -> dict:
    try:
        resource = files(__package__).joinpath(NOTES_RESOURCE)
        with resource.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        logger.debug("resumes de version indisponibles : %s", exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def release_note(version: str) -> dict | None:
    parsed = parse_version(version)
    if parsed is None:
        return None
    note = _read_payload().get(str(parsed))
    return note if isinstance(note, dict) else None


def is_significant_update(previous: str, current: str) -> bool:
    before = parse_version(previous)
    after = parse_version(current)
    if before is None or after is None or after <= before:
        return False
    return (after.major, after.minor) != (before.major, before.minor)


def prepare_release_celebration(state, current_version: str) -> dict | None:
    previous = state.get_meta(LAST_VERSION_KEY)
    state.set_meta(LAST_VERSION_KEY, current_version)
    if not previous or not is_significant_update(previous, current_version):
        return None
    if state.get_meta(CELEBRATED_VERSION_KEY) == current_version:
        return None
    return release_note(current_version)


def dismiss_release_celebration(state, version: str) -> None:
    state.set_meta(CELEBRATED_VERSION_KEY, version)
