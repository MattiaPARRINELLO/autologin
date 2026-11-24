from __future__ import annotations

from datetime import datetime, time

import pytest

from checkmate_watcher.config import ConfigError, load_config
from checkmate_watcher.schedule import (
    Schedule,
    ScheduleError,
    parse_days,
    parse_window,
    parse_windows,
)
from checkmate_watcher.state import StateStore, _parse_number_map

WINDOWS = parse_windows(["09:00-12:00", "13:30-16:30"])
SCHEDULE = Schedule(enabled=True, days=(0, 1, 2, 3, 4), windows=WINDOWS)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    # 16 novembre 2026 est un lundi.
    return datetime(2026, 11, 16 + day, hour, minute)


def test_parse_window_valide():
    window = parse_window("09:00-12:00")
    assert window.start == time(9, 0)
    assert window.end == time(12, 0)
    assert str(window) == "09:00-12:00"


@pytest.mark.parametrize("value", ["9h-12h", "12:00-09:00", "09:00", ""])
def test_parse_window_invalide(value):
    with pytest.raises(ScheduleError):
        parse_window(value)


def test_parse_windows_refuse_le_chevauchement():
    with pytest.raises(ScheduleError):
        parse_windows(["09:00-12:00", "11:00-13:00"])


def test_parse_days_accepte_les_abreviations():
    assert parse_days(["Mon", "tue", "WED"]) == (0, 1, 2)
    with pytest.raises(ScheduleError):
        parse_days(["lundi"])


def test_active_window():
    assert SCHEDULE.active_window(at(0, 10)) == WINDOWS[0]
    assert SCHEDULE.active_window(at(0, 14)) == WINDOWS[1]
    assert SCHEDULE.active_window(at(0, 12, 30)) is None
    assert SCHEDULE.active_window(at(5, 10)) is None  # samedi
    assert SCHEDULE.active_window(at(0, 9, 0)) == WINDOWS[0]
    assert SCHEDULE.active_window(at(0, 12, 0)) is None


def test_window_key_change_par_creneau():
    assert SCHEDULE.window_key(at(0, 10)) == "2026-11-16#0"
    assert SCHEDULE.window_key(at(0, 14)) == "2026-11-16#1"
    assert SCHEDULE.window_key(at(0, 20)) is None


def test_next_start_depuis_l_exterieur():
    assert SCHEDULE.next_start(at(0, 8)) == at(0, 9)
    assert SCHEDULE.next_start(at(0, 12, 30)) == at(0, 13, 30)
    assert SCHEDULE.next_start(at(0, 17)) == at(1, 9)
    # vendredi soir vers lundi matin
    assert SCHEDULE.next_start(at(4, 18)) == at(7, 9)


def test_seconds_until_next():
    assert SCHEDULE.seconds_until_next(at(0, 8)) == 3600
    assert SCHEDULE.seconds_until_next(at(0, 10)) > 3 * 3600


def test_schedule_desactivee_ne_bloque_rien():
    schedule = Schedule(enabled=False)
    assert schedule.active_window(at(0, 10)) is None
    assert schedule.window_key(at(0, 10)) is None


def test_state_memorise_un_creneau(tmp_path):
    store = StateStore(tmp_path / "state.json")
    assert not store.window_done("2026-11-16#0")
    store.mark_window("2026-11-16#0", now=1000)
    assert store.window_done("2026-11-16#0")

    reloaded = StateStore(tmp_path / "state.json")
    assert reloaded.window_done("2026-11-16#0")
    assert not reloaded.window_done("2026-11-16#1")


def test_config_lit_le_planning(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[cesar]
base_url = "https://cesar.example.fr"
username = "eleve"
password = "secret"

[schedule]
enabled = true
days = ["mon", "tue"]
windows = ["09:00-12:00", "13:30-16:30"]
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.schedule.enabled is True
    assert config.schedule.days == (0, 1)
    assert len(config.schedule.windows) == 2


def test_config_refuse_un_planning_invalide(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[cesar]
base_url = "https://cesar.example.fr"
username = "eleve"
password = "secret"

[schedule]
enabled = true
windows = ["09:00-12:00", "11:00-13:00"]
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)


def test_parse_number_map_filtre_les_valeurs_non_numeriques():
    value = {"a": 1, "b": 2.5, "c": "x", 7: 3}
    assert _parse_number_map(value) == {"a": 1.0, "b": 2.5, "7": 3.0}
