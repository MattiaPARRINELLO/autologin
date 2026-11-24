from __future__ import annotations

from datetime import datetime

from checkmate_watcher.schedule import Schedule, parse_windows
from checkmate_watcher.state import StateStore
from checkmate_watcher.watcher import _pause_reason, _record_success

SCHEDULE = Schedule(
    enabled=True,
    days=(0, 1, 2, 3, 4),
    windows=parse_windows(["09:00-12:00"]),
)
LUNDI_10H = datetime(2026, 11, 16, 10, 0)


def test_pas_de_pause_hors_planning(tmp_path):
    assert (
        _pause_reason(
            Schedule(enabled=False), StateStore(tmp_path / "s.json"), LUNDI_10H
        )
        is None
    )


def test_pause_hors_plage(tmp_path):
    pause = _pause_reason(
        SCHEDULE, StateStore(tmp_path / "s.json"), datetime(2026, 11, 16, 8, 0)
    )
    assert pause is not None
    assert pause.reason == "hors plage"
    assert pause.window_key is None
    assert pause.resume == datetime(2026, 11, 16, 9, 0)


def test_pause_sur_creneau_deja_signe(tmp_path):
    state = StateStore(tmp_path / "s.json")
    state.mark_window(SCHEDULE.window_key(LUNDI_10H))
    pause = _pause_reason(SCHEDULE, state, LUNDI_10H)
    assert pause is not None
    assert pause.reason == "creneau deja signe"
    assert pause.window_key == "2026-11-16#0"


def test_surveillance_active_sur_creneau_libre(tmp_path):
    assert _pause_reason(SCHEDULE, StateStore(tmp_path / "s.json"), LUNDI_10H) is None


def test_succes_note_le_retour_a_la_normale(tmp_path):
    state = StateStore(tmp_path / "s.json")
    state.set_meta("last_error_at", "2026-11-16T09:00:00")
    _record_success(state)
    assert state.get_meta("last_ok_at") is not None


def test_succes_sans_erreur_n_ecrit_rien(tmp_path):
    state = StateStore(tmp_path / "s.json")
    _record_success(state)
    assert state.get_meta("last_ok_at") is None


def test_succes_repete_ne_reecrit_pas_l_heure(tmp_path):
    state = StateStore(tmp_path / "s.json")
    state.set_meta("last_error_at", "2026-11-16T09:00:00")
    state.set_meta("last_ok_at", "2026-11-16T09:05:00")
    _record_success(state)
    assert state.get_meta("last_ok_at") == "2026-11-16T09:05:00"
