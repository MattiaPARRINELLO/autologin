"""Etat courant expose par le tableau de bord local."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import BUILD, __version__
from .config import Config
from .paths import default_log_file
from .schedule import DAY_NAMES
from .state import StateStore


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _recent(value: str | None, now: datetime, seconds: int = 600) -> bool:
    if not value:
        return False
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return False
    return (now - stamp).total_seconds() < seconds


def _resolved(state: StateStore) -> bool:
    """Vrai si une surveillance a reussi depuis la derniere erreur."""
    error_at = state.get_meta("last_error_at")
    ok_at = state.get_meta("last_ok_at")
    return bool(error_at and ok_at and ok_at >= error_at)


def build_snapshot(
    config: Config,
    state: StateStore,
    started_at: datetime,
    config_path: Path,
    now: datetime | None = None,
) -> dict:
    moment = now or datetime.now()
    schedule = config.schedule
    situation = schedule.situation(moment, state.window_done)
    window = situation.window

    labels = {
        "disabled": "Surveillance active",
        "active": "Surveillance active",
        "outside": "Hors créneau",
        "signed": "Créneau signé",
    }
    mode = "active" if situation.reason == "disabled" else situation.reason
    label = labels[situation.reason]

    if _recent(state.get_meta("last_error_at"), moment) and not _resolved(state):
        mode, label = "error", "Erreur récente"

    next_start = schedule.next_start(moment)
    days = [
        name
        for name, index in sorted(DAY_NAMES.items(), key=lambda item: item[1])
        if index in schedule.days
    ]

    restart_required = False
    try:
        restart_required = config_path.stat().st_mtime > started_at.timestamp() + 1
    except OSError:
        pass

    return {
        "version": __version__,
        "channel": config.updates.channel,
        "build": BUILD,
        "started_at": _iso(started_at),
        "now": _iso(moment),
        "uptime_seconds": max(0, int((moment - started_at).total_seconds())),
        "mode": mode,
        "label": label,
        "window": str(window) if window else None,
        "next_window": _iso(next_start) if next_start else None,
        "schedule": {
            "enabled": schedule.enabled,
            "days": days,
            "windows": [str(item) for item in schedule.windows],
        },
        "counters": {
            "starts": state.counter("stats.starts"),
            "detections": state.counter("stats.detections"),
            "signed": state.counter("stats.signed"),
            "errors": state.counter("stats.errors"),
        },
        "last_signed_at": state.get_meta("last_signed_at"),
        "last_detection_at": state.get_meta("last_detection_at"),
        "last_error_at": state.get_meta("last_error_at"),
        "last_error_kind": state.get_meta("last_error_kind"),
        "last_error_message": state.get_meta("last_error_message"),
        "restart_required": restart_required,
        "log_file": str(default_log_file()),
    }
