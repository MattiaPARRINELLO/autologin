from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from checkmate_watcher import watcher
from checkmate_watcher.http_session import HttpTransportError
from checkmate_watcher.schedule import Schedule, parse_windows
from checkmate_watcher.state import StateStore
from checkmate_watcher.updates import Release, UpdatePolicy, Version
from checkmate_watcher.watcher import (
    _mark_absent,
    _pause_reason,
    _record_success,
)

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


def test_notification_de_mise_a_jour_avec_micro_resume(tmp_path, monkeypatch):
    release = Release(
        "watcher-v0.7.0",
        Version(0, 7, 0),
        "https://example.com/release",
        "stable",
        False,
        teaser="Detection 2,3 fois plus rapide.",
    )
    sent = []

    async def fake_send(config, title, message, **kwargs):
        sent.append((title, message))

    monkeypatch.setattr(watcher, "check_for_update", lambda *a, **k: release)
    monkeypatch.setattr(watcher, "_send", fake_send)
    state = StateStore(tmp_path / "state.json")

    asyncio.run(watcher._check_update(_Config(), state))

    assert len(sent) == 1
    assert release.teaser in sent[0][1]
    assert state.get_meta("update_notified") == release.tag


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


def test_pause_sur_creneau_declare_absent(tmp_path):
    state = StateStore(tmp_path / "s.json")
    state.mark_window(SCHEDULE.window_key(LUNDI_10H), reason="absent")

    pause = _pause_reason(SCHEDULE, state, LUNDI_10H)

    assert pause is not None
    assert pause.reason == "absence declaree"
    assert pause.window_key == "2026-11-16#0"


def test_absence_termine_le_creneau_courant(tmp_path):
    state = StateStore(tmp_path / "s.json")
    key = SCHEDULE.window_key(LUNDI_10H)

    stopped = _mark_absent(state, "signal-1", key)

    assert stopped is True
    assert state.window_reason(key) == "absent"
    assert state.get_meta("last_absent_at") is not None
    assert _pause_reason(SCHEDULE, state, LUNDI_10H) is not None


def test_surveillance_active_sur_creneau_libre(tmp_path):
    assert (
        _pause_reason(SCHEDULE, StateStore(tmp_path / "s.json"), LUNDI_10H)
        is None
    )


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


def test_ouvre_la_celebration_apres_mise_a_jour(monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            self.target = target
            self.args = args
            self.daemon = daemon
            started.append(self)

        def start(self):
            self.started = True

    monkeypatch.setattr(watcher.threading, "Thread", FakeThread)
    session = SimpleNamespace(
        release_note={"version": "0.7.0"},
        url="http://127.0.0.1:1234/?token=test",
    )

    watcher._open_update_celebration(session)

    assert len(started) == 1
    assert started[0].target is watcher.open_url
    assert started[0].args == (session.url,)
    assert started[0].daemon is True
    assert started[0].started is True


def test_sans_resume_aucune_fenetre_ne_s_ouvre(monkeypatch):
    class FakeThread:
        def __init__(self, **kwargs):
            raise AssertionError("aucun thread attendu")

    monkeypatch.setattr(watcher.threading, "Thread", FakeThread)

    watcher._open_update_celebration(
        SimpleNamespace(release_note=None, url="http://127.0.0.1:1234")
    )


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


class _CheckSession:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error

    async def check(self):
        if self.error is not None:
            raise self.error
        return self.result


def test_presence_deja_enregistree_quand_l_emargement_a_disparu():
    session = _CheckSession(result=None)

    assert asyncio.run(watcher._signature_landed(session)) is True


def test_signature_pas_encore_enregistree_si_l_emargement_est_ouvert():
    signal = SimpleNamespace(key="E13", label="Emargement ouvert")
    session = _CheckSession(result=signal)

    assert asyncio.run(watcher._signature_landed(session)) is False


def test_verification_apres_fermeture_du_navigateur_echoue_proprement():
    session = _CheckSession(error=RuntimeError("Target closed"))

    assert asyncio.run(watcher._signature_landed(session)) is False


def test_un_signal_annule_la_tache_en_cours():
    import threading

    async def scenario():
        stop = threading.Event()
        started = asyncio.Event()

        async def longue_operation():
            started.set()
            await asyncio.sleep(30)

        task = asyncio.create_task(longue_operation())
        await started.wait()
        watchdog = asyncio.create_task(watcher._cancel_on_stop(stop, task))
        stop.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        stop.set()
        await watchdog

    asyncio.run(scenario())


def test_l_arret_installe_les_gestionnaires_de_signal():
    import signal
    import threading

    stop = threading.Event()
    previous = {
        name: signal.getsignal(getattr(signal, name))
        for name in ("SIGTERM", "SIGINT")
    }
    try:
        watcher._install_stop_handlers(stop)
        signal.raise_signal(signal.SIGTERM)
        assert stop.is_set()
    finally:
        for name, handler in previous.items():
            signal.signal(getattr(signal, name), handler)
