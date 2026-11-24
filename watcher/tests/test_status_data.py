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


def make_state(tmp_path):
    return StateStore(tmp_path / "state.json")


def snapshot_at(tmp_path, state, started, now, *, enabled=True):
    config = make_config(tmp_path, enabled=enabled)
    return build_snapshot(config, state, started, tmp_path / "config.toml", now=now)


def test_snapshot_bloque_par_une_version_obligatoire(tmp_path):
    state = make_state(tmp_path)
    blocked = {"tag": "watcher-v0.8.0", "version": "0.8.0", "reason": "faille"}
    snapshot = build_snapshot(
        make_config(tmp_path),
        state,
        datetime(2026, 11, 16, 9, 55),
        tmp_path / "config.toml",
        now=datetime(2026, 11, 16, 10, 0),
        blocked=blocked,
    )
    assert snapshot["blocked"] == blocked
    assert snapshot["migration"] is None
    assert snapshot["mode"] == "blocked"
    assert snapshot["label"] == "Mise a jour obligatoire"


def test_snapshot_signale_une_migration_intermediaire(tmp_path):
    migration = {"tag": "watcher-v0.7.5", "version": "0.7.5", "reason": "format v2"}
    snapshot = build_snapshot(
        make_config(tmp_path),
        make_state(tmp_path),
        datetime(2026, 11, 16, 9, 55),
        tmp_path / "config.toml",
        now=datetime(2026, 11, 16, 10, 0),
        migration=migration,
    )
    assert snapshot["migration"] == migration
    assert snapshot["blocked"] is None


def test_snapshot_surveillance_active(tmp_path):
    state = make_state(tmp_path)
    state.increment("stats.detections", 3)
    started = datetime(2026, 11, 16, 9, 55)
    snapshot = snapshot_at(tmp_path, state, started, datetime(2026, 11, 16, 10, 0))
    assert snapshot["mode"] == "active"
    assert snapshot["label"] == "Surveillance active"
    assert snapshot["window"] == "09:00-12:00"
    assert snapshot["counters"]["detections"] == 3
    assert snapshot["next_window"].endswith("13:30:00")


def test_snapshot_creneau_signe(tmp_path):
    state = make_state(tmp_path)
    state.mark_window("2026-11-16#0", now=1000)
    snapshot = snapshot_at(
        tmp_path,
        state,
        datetime(2026, 11, 16, 9, 55),
        datetime(2026, 11, 16, 10, 0),
    )
    assert snapshot["mode"] == "signed"
    assert snapshot["label"] == "Créneau signé"


def test_snapshot_hors_creneau(tmp_path):
    state = make_state(tmp_path)
    snapshot = snapshot_at(
        tmp_path, state, datetime(2026, 11, 16, 8, 0), datetime(2026, 11, 16, 8, 30)
    )
    assert snapshot["mode"] == "outside"
    assert snapshot["window"] is None
    assert snapshot["next_window"].endswith("09:00:00")


def test_snapshot_planning_desactive(tmp_path):
    state = make_state(tmp_path)
    started, now = datetime(2026, 11, 16, 8, 0), datetime(2026, 11, 16, 3, 0)
    snapshot = snapshot_at(tmp_path, state, started, now, enabled=False)
    assert snapshot["mode"] == "active"
    assert snapshot["window"] is None


def test_snapshot_derniere_signature_et_redemarrage(tmp_path):
    state = make_state(tmp_path)
    state.set_meta("last_signed_at", "2026-11-16T09:58:00")
    state.set_meta("last_error_at", "2026-11-16T09:00:00")
    (tmp_path / "config.toml").write_text("x", encoding="utf-8")
    snapshot = snapshot_at(
        tmp_path, state, datetime(2026, 11, 16, 9, 0), datetime(2026, 11, 16, 10, 0)
    )
    assert snapshot["last_signed_at"] == "2026-11-16T09:58:00"
    assert snapshot["restart_required"] is True
    assert snapshot["mode"] != "error"


def test_snapshot_erreur_recente(tmp_path):
    state = make_state(tmp_path)
    state.set_meta("last_error_at", "2026-11-16T09:58:00")
    state.set_meta("last_error_kind", "reseau")
    state.set_meta("last_error_message", "CESAR est injoignable pour le moment.")
    started, now = datetime(2026, 11, 16, 9, 0), datetime(2026, 11, 16, 10, 0)
    snapshot = snapshot_at(tmp_path, state, started, now)
    assert snapshot["mode"] == "error"
    assert snapshot["label"] == "Erreur récente"
    assert snapshot["last_error_kind"] == "reseau"
    assert snapshot["last_error_message"] == "CESAR est injoignable pour le moment."


def test_snapshot_erreur_sans_cause(tmp_path):
    state = make_state(tmp_path)
    state.set_meta("last_error_at", "2026-11-16T09:58:00")
    snapshot = snapshot_at(
        tmp_path, state, datetime(2026, 11, 16, 9, 0), datetime(2026, 11, 16, 10, 0)
    )
    assert snapshot["last_error_kind"] is None
    assert snapshot["last_error_message"] is None


def test_snapshot_erreur_resolue(tmp_path):
    state = make_state(tmp_path)
    state.set_meta("last_error_at", "2026-11-16T09:50:00")
    state.set_meta("last_error_message", "CESAR est injoignable pour le moment.")
    state.set_meta("last_ok_at", "2026-11-16T09:52:00")
    snapshot = snapshot_at(
        tmp_path, state, datetime(2026, 11, 16, 9, 0), datetime(2026, 11, 16, 10, 0)
    )
    assert snapshot["mode"] == "active"
    assert snapshot["label"] == "Surveillance active"
    assert snapshot["last_error_message"] == "CESAR est injoignable pour le moment."


def test_snapshot_erreur_posterieure_au_succes(tmp_path):
    state = make_state(tmp_path)
    state.set_meta("last_ok_at", "2026-11-16T09:50:00")
    state.set_meta("last_error_at", "2026-11-16T09:58:00")
    snapshot = snapshot_at(
        tmp_path, state, datetime(2026, 11, 16, 9, 0), datetime(2026, 11, 16, 10, 0)
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
