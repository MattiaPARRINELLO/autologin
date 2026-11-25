from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from checkmate_watcher import watcher
from checkmate_watcher.http_session import HttpTransportError
from checkmate_watcher.schedule import Schedule, parse_windows
from checkmate_watcher.state import StateStore
from checkmate_watcher.updates import Release, UpdatePolicy, Version
from checkmate_watcher.watcher import _pause_reason, _record_success

SCHEDULE = Schedule(
    enabled=True,
    days=(0, 1, 2, 3, 4),
    windows=parse_windows(["09:00-12:00"]),
)
LUNDI_10H = datetime(2026, 11, 16, 10, 0)


class _Updates:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.channel = "stable"


class _Config:
    def __init__(self, enabled: bool = True) -> None:
        self.updates = _Updates(enabled)


def _loader(policy):
    async def load(config):
        return policy

    return load


def _required_policy() -> UpdatePolicy:
    release = Release(
        "watcher-v0.8.0",
        Version(0, 8, 0),
        "https://example.com",
        "obligatoire",
        False,
        required_reason="faille de signature",
        markers_declared=True,
    )
    return UpdatePolicy(Version(0, 7, 0), release, release, None, "stable")


def test_version_obligatoire_detectee(monkeypatch):
    policy = _required_policy()
    monkeypatch.setattr(watcher, "_load_policy", _loader(policy))
    assert asyncio.run(watcher._startup_policy(_Config())) is policy


def test_sans_version_obligatoire_la_politique_reste_disponible(monkeypatch):
    policy = UpdatePolicy(Version(0, 7, 0), None, None, None, "stable")
    monkeypatch.setattr(watcher, "_load_policy", _loader(policy))
    result = asyncio.run(watcher._startup_policy(_Config()))
    assert result is policy and result.required is None


def test_verification_desactivee_ne_bloque_pas(monkeypatch):
    monkeypatch.setattr(watcher, "_load_policy", _loader(_required_policy()))
    assert asyncio.run(watcher._startup_policy(_Config(enabled=False))) is None


def test_erreur_reseau_ne_bloque_pas(monkeypatch):
    async def boom(config):
        raise RuntimeError("reseau")

    monkeypatch.setattr(watcher, "_load_policy", boom)
    assert asyncio.run(watcher._startup_policy(_Config())) is None


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


def test_open_session_choisit_le_transport_http(monkeypatch):
    class FakeHttp:
        def __init__(self, config):
            self.config = config
            self.opened = False

        async def open(self, headless):
            self.opened = headless

    monkeypatch.setattr(watcher, "HttpCesarSession", FakeHttp)
    config = SimpleNamespace(watcher=SimpleNamespace(transport="http"))

    session = asyncio.run(watcher._open_session(config, True))

    assert isinstance(session, FakeHttp)
    assert session.opened is True


def test_open_session_choisit_le_transport_navigateur(monkeypatch):
    class FakeBrowser:
        def __init__(self, config):
            self.config = config
            self.opened = False

        async def open(self, headless):
            self.opened = headless

    monkeypatch.setattr(watcher, "CesarSession", FakeBrowser)
    config = SimpleNamespace(watcher=SimpleNamespace(transport="browser"))

    session = asyncio.run(watcher._open_session(config, False))

    assert isinstance(session, FakeBrowser)
    assert session.opened is False


def test_open_session_bascule_sur_navigateur_si_http_echoue(monkeypatch):
    class FailingHttp:
        def __init__(self, config):
            self.closed = False

        async def open(self, headless):
            raise HttpTransportError("CESAR HTTP 403")

        async def close(self):
            self.closed = True

    class FakeBrowser:
        def __init__(self, config):
            self.opened = False

        async def open(self, headless):
            self.opened = headless

    async def no_send(*args, **kwargs):
        return False

    monkeypatch.setattr(watcher, "HttpCesarSession", FailingHttp)
    monkeypatch.setattr(watcher, "CesarSession", FakeBrowser)
    monkeypatch.setattr(watcher, "_send", no_send)
    config = SimpleNamespace(watcher=SimpleNamespace(transport="http"))

    session = asyncio.run(watcher._open_session(config, True))

    assert isinstance(session, FakeBrowser)
    assert session.opened is True
