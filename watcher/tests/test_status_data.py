from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from checkmate_watcher.config import default_config
from checkmate_watcher.schedule import Schedule, parse_windows
from checkmate_watcher.state import StateStore
from checkmate_watcher.status_data import build_snapshot

WINDOWS = parse_windows(["09:00-12:00", "13:30-16:30"])


def make_config(tmp_path, *, enabled=True):
    config = default_config()
    return replace(
        config,
        schedule=Schedule(enabled=enabled, days=(0, 1, 2, 3, 4), windows=WINDOWS),
        watcher=replace(
            config.watcher,
            state_file=tmp_path / "state.json",
            profile_dir=tmp_path / "profile",
        ),
    )


def test_snapshot_surveillance_active(tmp_path):
    config = make_config(tmp_path)
    state = StateStore(tmp_path / "state.json")
    state.increment("stats.detections", 3)
    started = datetime(2026, 11, 16, 9, 55)
    snapshot = build_snapshot(
        config,
        state,
        started,
        tmp_path / "config.toml",
        now=datetime(2026, 11, 16, 10, 0),
    )
    assert snapshot["mode"] == "active"
    assert snapshot["label"] == "Surveillance active"
    assert snapshot["window"] == "09:00-12:00"
    assert snapshot["counters"]["detections"] == 3
    assert snapshot["next_window"].endswith("13:30:00")


def test_snapshot_creneau_signe(tmp_path):
    config = make_config(tmp_path)
    state = StateStore(tmp_path / "state.json")
    state.mark_window("2026-11-16#0", now=1000)
    snapshot = build_snapshot(
        config,
        state,
        datetime(2026, 11, 16, 9, 55),
        tmp_path / "config.toml",
        now=datetime(2026, 11, 16, 10, 0),
    )
    assert snapshot["mode"] == "signed"
    assert snapshot["label"] == "Créneau signé"


def test_snapshot_hors_creneau(tmp_path):
    config = make_config(tmp_path)
    state = StateStore(tmp_path / "state.json")
    snapshot = build_snapshot(
        config,
        state,
        datetime(2026, 11, 16, 8, 0),
        tmp_path / "config.toml",
        now=datetime(2026, 11, 16, 8, 30),
    )
    assert snapshot["mode"] == "outside"
    assert snapshot["window"] is None
    assert snapshot["next_window"].endswith("09:00:00")


def test_snapshot_planning_desactive(tmp_path):
    config = make_config(tmp_path, enabled=False)
    state = StateStore(tmp_path / "state.json")
    snapshot = build_snapshot(
        config,
        state,
        datetime(2026, 11, 16, 8, 0),
        tmp_path / "config.toml",
        now=datetime(2026, 11, 16, 3, 0),
    )
    assert snapshot["mode"] == "active"
    assert snapshot["window"] is None


def test_snapshot_derniere_signature_et_redemarrage(tmp_path):
    config = make_config(tmp_path)
    state = StateStore(tmp_path / "state.json")
    state.set_meta("last_signed_at", "2026-11-16T09:58:00")
    state.set_meta("last_error_at", "2026-11-16T09:00:00")
    config_path = tmp_path / "config.toml"
    config_path.write_text("x", encoding="utf-8")
    started = datetime(2026, 11, 16, 9, 0)

    snapshot = build_snapshot(
        config,
        state,
        started,
        config_path,
        now=datetime(2026, 11, 16, 10, 0),
    )
    assert snapshot["last_signed_at"] == "2026-11-16T09:58:00"
    assert snapshot["restart_required"] is True
    assert snapshot["mode"] != "error"


def test_snapshot_erreur_recente(tmp_path):
    config = make_config(tmp_path)
    state = StateStore(tmp_path / "state.json")
    state.set_meta("last_error_at", "2026-11-16T09:58:00")
    state.set_meta("last_error_kind", "reseau")
    state.set_meta("last_error_message", "CESAR est injoignable pour le moment.")
    snapshot = build_snapshot(
        config,
        state,
        datetime(2026, 11, 16, 9, 0),
        tmp_path / "config.toml",
        now=datetime(2026, 11, 16, 10, 0),
    )
    assert snapshot["mode"] == "error"
    assert snapshot["label"] == "Erreur récente"
    assert snapshot["last_error_kind"] == "reseau"
    assert snapshot["last_error_message"] == "CESAR est injoignable pour le moment."


def test_snapshot_erreur_sans_cause(tmp_path):
    config = make_config(tmp_path)
    state = StateStore(tmp_path / "state.json")
    state.set_meta("last_error_at", "2026-11-16T09:58:00")
    snapshot = build_snapshot(
        config,
        state,
        datetime(2026, 11, 16, 9, 0),
        tmp_path / "config.toml",
        now=datetime(2026, 11, 16, 10, 0),
    )
    assert snapshot["last_error_kind"] is None
    assert snapshot["last_error_message"] is None


def test_snapshot_erreur_resolue(tmp_path):
    config = make_config(tmp_path)
    state = StateStore(tmp_path / "state.json")
    state.set_meta("last_error_at", "2026-11-16T09:50:00")
    state.set_meta("last_error_message", "CESAR est injoignable pour le moment.")
    state.set_meta("last_ok_at", "2026-11-16T09:52:00")
    snapshot = build_snapshot(
        config,
        state,
        datetime(2026, 11, 16, 9, 0),
        tmp_path / "config.toml",
        now=datetime(2026, 11, 16, 10, 0),
    )
    assert snapshot["mode"] == "active"
    assert snapshot["label"] == "Surveillance active"
    assert snapshot["last_error_message"] == "CESAR est injoignable pour le moment."


def test_snapshot_erreur_posterieure_au_succes(tmp_path):
    config = make_config(tmp_path)
    state = StateStore(tmp_path / "state.json")
    state.set_meta("last_ok_at", "2026-11-16T09:50:00")
    state.set_meta("last_error_at", "2026-11-16T09:58:00")
    snapshot = build_snapshot(
        config,
        state,
        datetime(2026, 11, 16, 9, 0),
        tmp_path / "config.toml",
        now=datetime(2026, 11, 16, 10, 0),
    )
    assert snapshot["mode"] == "error"


def test_snapshot_uptime(tmp_path):
    config = make_config(tmp_path)
    state = StateStore(tmp_path / "state.json")
    snapshot = build_snapshot(
        config,
        state,
        datetime(2026, 11, 16, 9, 0),
        tmp_path / "config.toml",
        now=datetime(2026, 11, 16, 9, 5),
    )
    assert snapshot["uptime_seconds"] == 300
