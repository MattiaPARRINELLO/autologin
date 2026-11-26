"""Messages diffuses par le mainteneur a toutes les installations.

Le collecteur expose ``GET /api/messages`` : de courts messages publics. Le
watcher retient le dernier identifiant vu et affiche chaque nouveau message en
notification. Une panne reseau est ignoree : la surveillance continue.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass

from . import __version__

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://main.mprnl.fr/cm-stats/api/messages"
DISABLE_ENV = "CHECKMATE_BROADCAST"
TIMEOUT_SECONDS = 5
MAX_TITLE = 120
MAX_TEXT = 1000


@dataclass(frozen=True)
class Message:
    """Message public destine a toutes les installations."""

    id: int
    title: str
    text: str


def _text(item: dict, key: str) -> str:
    value = item.get(key)
    return value.strip() if isinstance(value, str) else ""


def _valid_id(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def parse_one(item) -> Message | None:
    """Un message valide, ou None si l'entree est inutilisable."""
    if not isinstance(item, dict):
        return None
    message_id = _valid_id(item.get("id"))
    title = _text(item, "title")
    text = _text(item, "message")
    if message_id is None or not title or not text:
        return None
    return Message(message_id, title[:MAX_TITLE], text[:MAX_TEXT])


def parse_messages(payload) -> list[Message]:
    """Messages lisibles d'une reponse JSON, sans jamais lever d'exception."""
    if not isinstance(payload, dict):
        return []
    items = payload.get("messages")
    if not isinstance(items, list):
        return []
    return [
        message for message in map(parse_one, items) if message is not None
    ]


def _request(endpoint: str) -> urllib.request.Request:
    headers = {
        "Accept": "application/json",
        "User-Agent": f"checkmate-watcher/{__version__}",
    }
    return urllib.request.Request(endpoint, headers=headers)


def fetch_messages(
    endpoint: str = DEFAULT_ENDPOINT, *, timeout: int = TIMEOUT_SECONDS
) -> list[Message]:
    """Messages publies, tries par identifiant croissant."""
    with urllib.request.urlopen(
        _request(endpoint), timeout=timeout
    ) as response:
        payload = json.loads(response.read())
    return parse_messages(payload)


def unseen(messages: list[Message], last_id: int) -> list[Message]:
    """Messages jamais affiches, du plus ancien au plus recent."""
    return sorted(
        (message for message in messages if message.id > last_id),
        key=lambda message: message.id,
    )


def newest_id(messages: list[Message]) -> int:
    return max((message.id for message in messages), default=0)


def _disabled_by_env() -> bool:
    value = os.environ.get(DISABLE_ENV, "").strip().lower()
    return value in {"0", "false", "non", "off"}


def is_enabled(config) -> bool:
    if _disabled_by_env():
        return False
    section = getattr(config, "broadcast", None)
    return bool(getattr(section, "enabled", True))


def endpoint(config) -> str:
    section = getattr(config, "broadcast", None)
    return str(getattr(section, "endpoint", DEFAULT_ENDPOINT))
