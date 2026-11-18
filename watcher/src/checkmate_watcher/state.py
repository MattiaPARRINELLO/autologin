"""Etat persistant pour eviter de notifier plusieurs fois le meme emargement."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class StateStore:
    def __init__(self, path: Path, ttl: int = 3600) -> None:
        self.path = path
        self.ttl = ttl
        self._signals: dict[str, float] = {}
        self._windows: dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("etat illisible, reinitialisation : %s", exc)
            return
        signals = data.get("signals") if isinstance(data, dict) else None
        if isinstance(signals, dict):
            self._signals = {
                str(key): float(value)
                for key, value in signals.items()
                if isinstance(value, (int, float))
            }
        windows = data.get("windows") if isinstance(data, dict) else None
        if isinstance(windows, dict):
            self._windows = {
                str(key): float(value)
                for key, value in windows.items()
                if isinstance(value, (int, float))
            }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"signals": self._signals, "windows": self._windows}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self.path)

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
