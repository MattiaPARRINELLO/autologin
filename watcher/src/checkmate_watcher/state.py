"""Etat persistant pour eviter de notifier plusieurs fois le meme emargement."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _parse_number_map(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): float(item)
        for key, item in value.items()
        if isinstance(item, (int, float))
    }


def _parse_meta_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if isinstance(item, str)
    }


class StateStore:
    def __init__(self, path: Path, ttl: int = 3600) -> None:
        self.path = path
        self.ttl = ttl
        self._signals: dict[str, float] = {}
        self._windows: dict[str, float] = {}
        self._meta: dict[str, str] = {}
        self._load()

    def _read_payload(self) -> dict | None:
        if not self.path.is_file():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("etat illisible, reinitialisation : %s", exc)
            return None
        return data if isinstance(data, dict) else None

    def _load(self) -> None:
        payload = self._read_payload()
        if payload is None:
            return
        self._signals = _parse_number_map(payload.get("signals"))
        self._windows = _parse_number_map(payload.get("windows"))
        self._meta = _parse_meta_map(payload.get("meta"))

    def _build_payload(self) -> dict:
        return {
            "signals": self._signals,
            "windows": self._windows,
            "meta": self._meta,
        }

    def _write_payload(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self.path)

    def _save(self) -> None:
        self._write_payload(self._build_payload())

    def prune(self, now: float | None = None) -> None:
        current = time.time() if now is None else now
        expired = [
            key
            for key, timestamp in self._signals.items()
            if current - timestamp >= self.ttl
        ]
        for key in expired:
            del self._signals[key]
        if expired:
            self._save()

    def seen(self, key: str, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        timestamp = self._signals.get(key)
        if timestamp is None:
            return False
        return (current - timestamp) < self.ttl

    def mark(self, key: str, now: float | None = None) -> None:
        self._signals[key] = time.time() if now is None else now
        self.prune(now)
        self._save()

    def get_meta(self, key: str) -> str | None:
        return self._meta.get(key)

    def set_meta(self, key: str, value: str) -> None:
        self._meta[key] = value
        self._save()

    def counter(self, key: str) -> int:
        try:
            return int(self._meta.get(key, "0"))
        except ValueError:
            return 0

    def increment(self, key: str, amount: int = 1) -> None:
        self._meta[key] = str(self.counter(key) + amount)
        self._save()

    def window_done(self, key: str) -> bool:
        return key in self._windows

    def mark_window(self, key: str, now: float | None = None) -> None:
        current = time.time() if now is None else now
        self._windows[key] = current
        # Un creneau signe ne sert plus apres une semaine.
        for old_key, timestamp in list(self._windows.items()):
            if current - timestamp > 7 * 24 * 3600:
                del self._windows[old_key]
        self._save()
