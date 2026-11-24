"""Plages horaires de surveillance et calcul des prochaines ouvertures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from itertools import pairwise

DAY_NAMES = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

DEFAULT_DAYS = ("mon", "tue", "wed", "thu", "fri")
DEFAULT_WINDOWS = ("09:00-12:00", "13:30-16:30")


class ScheduleError(Exception):
    """Plage horaire invalide."""


@dataclass(frozen=True)
class Window:
    start: time
    end: time

    def contains(self, moment: time) -> bool:
        return self.start <= moment and moment < self.end

    def __str__(self) -> str:
        return f"{self.start.strftime('%H:%M')}-{self.end.strftime('%H:%M')}"


@dataclass(frozen=True)
class Situation:
    """Etat du planning a un instant donne."""

    reason: str
    window: Window | None = None
    key: str | None = None


@dataclass(frozen=True)
class Schedule:
    enabled: bool = False
    days: tuple[int, ...] = (0, 1, 2, 3, 4)
    windows: tuple[Window, ...] = ()

    def covers(self, moment: datetime) -> bool:
        return moment.weekday() in self.days

    def active_window(self, moment: datetime) -> Window | None:
        if not self.enabled or not self.covers(moment):
            return None
        current = moment.time()
        for window in self.windows:
            if window.contains(current):
                return window
        return None

    def window_key(self, moment: datetime) -> str | None:
        if not self.enabled:
            return None
        window = self.active_window(moment)
        if window is None:
            return None
        index = self.windows.index(window)
        return f"{moment.date().isoformat()}#{index}"

    def situation(
        self, moment: datetime, is_signed: Callable[[str], bool]
    ) -> Situation:
        """Decrit le creneau courant : desactive, hors plage, signe ou actif."""
        if not self.enabled:
            return Situation("disabled")
        window = self.active_window(moment)
        if window is None:
            return Situation("outside")
        key = self.window_key(moment)
        if key and is_signed(key):
            return Situation("signed", window, key)
        return Situation("active", window, key)

    def next_start(self, moment: datetime) -> datetime | None:
        """Prochain debut de plage apres l'instant donne."""
        if not self.enabled:
            return None
        for offset in range(8):
            day = moment.date() + timedelta(days=offset)
            if day.weekday() not in self.days:
                continue
            for window in sorted(self.windows, key=lambda item: item.start):
                candidate = datetime.combine(day, window.start)
                if candidate > moment:
                    return candidate
        return None

    def seconds_until_next(self, moment: datetime) -> float:
        next_start = self.next_start(moment)
        if next_start is None:
            return 3600.0
        return max(1.0, (next_start - moment).total_seconds())

    def describe(self) -> str:
        if not self.enabled:
            return "desactivee"
        days = ",".join(name for name, index in DAY_NAMES.items() if index in self.days)
        windows = ", ".join(str(window) for window in self.windows)
        return f"{days} {windows}"


def parse_time(value: str) -> time:
    text = str(value).strip()
    try:
        hours, minutes = text.split(":", 1)
        return time(int(hours), int(minutes))
    except (ValueError, TypeError) as exc:
        raise ScheduleError(f"heure invalide : {value!r} (attendu HH:MM)") from exc


def parse_window(value: str) -> Window:
    text = str(value).strip()
    if "-" not in text:
        raise ScheduleError(f"plage invalide : {value!r} (attendu HH:MM-HH:MM)")
    start_text, end_text = text.split("-", 1)
    start = parse_time(start_text)
    end = parse_time(end_text)
    if end <= start:
        raise ScheduleError(f"plage invalide : {value!r} (fin avant debut)")
    return Window(start=start, end=end)


def parse_windows(values: object) -> tuple[Window, ...]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)) or not values:
        raise ScheduleError(
            "windows doit etre une liste non vide de plages HH:MM-HH:MM"
        )
    windows = [parse_window(str(value)) for value in values]
    ordered = sorted(windows, key=lambda window: window.start)
    for previous, current in pairwise(ordered):
        if current.start < previous.end:
            raise ScheduleError(f"les plages se chevauchent : {previous} et {current}")
    return tuple(ordered)


def parse_days(values: object) -> tuple[int, ...]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)) or not values:
        raise ScheduleError("days doit etre une liste non vide de jours")
    days = []
    for value in values:
        key = str(value).strip().lower()[:3]
        if key not in DAY_NAMES:
            raise ScheduleError(f"jour inconnu : {value!r} (mon, tue, wed, ...)")
        days.append(DAY_NAMES[key])
    return tuple(sorted(set(days)))
