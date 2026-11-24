"""Etat courant expose par le tableau de bord local."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import BUILD, __version__
from .config import Config
from .paths import default_log_file
from .schedule import DAY_NAMES, Schedule, Situation
from .state import StateStore

_LABELS = {
    "disabled": "Surveillance active",
    "active": "Surveillance active",
    "outside": "Hors créneau",
    "signed": "Créneau signé",
}
_COUNTERS = ("starts", "detections", "signed", "errors")


@dataclass
class _Context:
    config: Config
    state: StateStore
    started_at: datetime
    config_path: Path
    moment: datetime
    schedule: Schedule
    situation: Situation


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


def _days(schedule: Schedule) -> list[str]:
    return [
        name
        for name, index in sorted(DAY_NAMES.items(), key=lambda item: item[1])
        if index in schedule.days
    ]


def _status(ctx: _Context) -> tuple[str, str]:
    reason = ctx.situation.reason
    mode = "active" if reason == "disabled" else reason
    failed = _recent(ctx.state.get_meta("last_error_at"), ctx.moment)
    if failed and not _resolved(ctx.state):
        return "error", "Erreur récente"
    return mode, _LABELS[reason]


def _base(ctx: _Context) -> dict:
    return {
        "version": __version__,
        "channel": ctx.config.updates.channel,
        "build": BUILD,
        "started_at": _iso(ctx.started_at),
        "now": _iso(ctx.moment),
        "uptime_seconds": max(0, int((ctx.moment - ctx.started_at).total_seconds())),
    }


def _schedule_dict(ctx: _Context) -> dict:
    return {
        "enabled": ctx.schedule.enabled,
        "days": _days(ctx.schedule),
        "windows": [str(item) for item in ctx.schedule.windows],
    }


def _activity(ctx: _Context) -> dict:
    mode, label = _status(ctx)
    return {
        "mode": mode,
        "label": label,
        "window": str(ctx.situation.window) if ctx.situation.window else None,
        "next_window": _next_window(ctx),
        "schedule": _schedule_dict(ctx),
    }


def _state(ctx: _Context) -> dict:
    state = ctx.state
    return {
        "counters": {key: state.counter(f"stats.{key}") for key in _COUNTERS},
        "last_signed_at": state.get_meta("last_signed_at"),
        "last_detection_at": state.get_meta("last_detection_at"),
        "last_error_at": state.get_meta("last_error_at"),
        "last_error_kind": state.get_meta("last_error_kind"),
        "last_error_message": state.get_meta("last_error_message"),
    }


def _next_window(ctx: _Context) -> str | None:
    next_start = ctx.schedule.next_start(ctx.moment)
    return _iso(next_start) if next_start else None


def _restart_required(config_path: Path, started_at: datetime) -> bool:
    try:
        return config_path.stat().st_mtime > started_at.timestamp() + 1
    except OSError:
        return False


def _build_context(config, state, started_at, config_path, now) -> _Context:
    moment = now or datetime.now()
    schedule = config.schedule
    args = (config, state, started_at, config_path, moment, schedule)
    situation = schedule.situation(moment, state.window_done)
    return _Context(*args, situation)


def _render(ctx: _Context) -> dict:
    return {
        **_base(ctx),
        **_activity(ctx),
        **_state(ctx),
        "restart_required": _restart_required(ctx.config_path, ctx.started_at),
        "log_file": str(default_log_file()),
    }


def build_snapshot(
    config: Config,
    state: StateStore,
    started_at: datetime,
    config_path: Path,
    now: datetime | None = None,
) -> dict:
    return _render(_build_context(config, state, started_at, config_path, now))
