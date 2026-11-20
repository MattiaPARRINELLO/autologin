from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from checkmate_watcher import watcher as watcher_module
from checkmate_watcher.cesar import SignError
from checkmate_watcher.config import (
    CesarConfig,
    Config,
    NotificationConfig,
    Selectors,
    SignatureConfig,
    WatcherConfig,
)
from checkmate_watcher.schedule import Schedule, parse_windows
from checkmate_watcher.state import StateStore
from checkmate_watcher.watcher import _pause_reason, _sign_with_retry

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


def retry_config(retries: int) -> Config:
    return Config(
        cesar=CesarConfig(
            base_url="https://cesar.example.fr",
            username="eleve",
            password="secret",
        ),
        watcher=WatcherConfig(sign_retries=retries, sign_retry_delay=0),
        signature=SignatureConfig(),
        notifications=NotificationConfig(enabled=False),
        selectors=Selectors.from_dict({}),
    )


def test_signature_reessayee_apres_un_echec(monkeypatch):
    calls: list[str] = []

    async def fake_sign(config, session, points):
        calls.append("essai")
        if len(calls) == 1:
            raise SignError("bouton disparu")
        return "presence enregistree"

    monkeypatch.setattr(watcher_module, "sign_with_visibility", fake_sign)

    result = asyncio.run(_sign_with_retry(retry_config(1), object(), []))

    assert result == "presence enregistree"
    assert calls == ["essai", "essai"]


def test_signature_echoue_apres_toutes_les_tentatives(monkeypatch):
    calls: list[str] = []

    async def fake_sign(config, session, points):
        calls.append("essai")
        raise SignError("echec")

    monkeypatch.setattr(watcher_module, "sign_with_visibility", fake_sign)

    with pytest.raises(SignError):
        asyncio.run(_sign_with_retry(retry_config(2), object(), []))

    assert calls == ["essai", "essai", "essai"]


def test_signature_sans_nouvelle_tentative(monkeypatch):
    calls: list[str] = []

    async def fake_sign(config, session, points):
        calls.append("essai")
        raise SignError("echec")

    monkeypatch.setattr(watcher_module, "sign_with_visibility", fake_sign)

    with pytest.raises(SignError):
        asyncio.run(_sign_with_retry(retry_config(0), object(), []))

    assert calls == ["essai"]


def test_compteurs_du_jour_remis_a_zero(tmp_path):
    from checkmate_watcher.watcher import _bump_daily

    state = StateStore(tmp_path / "s.json")
    _bump_daily(state, "detections", datetime(2026, 11, 16, 10, 0))
    _bump_daily(state, "detections", datetime(2026, 11, 16, 11, 0))
    _bump_daily(state, "signed", datetime(2026, 11, 16, 11, 5))
    assert state.counter("daily.detections") == 2
    assert state.counter("daily.signed") == 1

    _bump_daily(state, "detections", datetime(2026, 11, 17, 9, 0))
    assert state.counter("daily.detections") == 1
    assert state.counter("daily.signed") == 0


def test_veille_du_soir_sans_emargement(tmp_path):
    from checkmate_watcher.watcher import evening_message

    state = StateStore(tmp_path / "s.json")
    assert evening_message(state, datetime(2026, 11, 16, 19, 0)) is None


def test_veille_du_soir_tout_est_signe(tmp_path):
    from checkmate_watcher.watcher import _bump_daily, evening_message

    state = StateStore(tmp_path / "s.json")
    now = datetime(2026, 11, 16, 10, 0)
    _bump_daily(state, "detections", now)
    _bump_daily(state, "signed", now)
    assert evening_message(state, datetime(2026, 11, 16, 19, 0)) is None


def test_veille_du_soir_signale_les_emargements_manques(tmp_path):
    from checkmate_watcher.watcher import _bump_daily, evening_message

    state = StateStore(tmp_path / "s.json")
    now = datetime(2026, 11, 16, 10, 0)
    _bump_daily(state, "detections", now)
    _bump_daily(state, "detections", now)
    _bump_daily(state, "signed", now)
    message = evening_message(state, datetime(2026, 11, 16, 19, 0))
    assert message is not None
    assert "1 emargement" in message
    assert "absence" not in message.lower()


def test_veille_du_soir_ignore_un_autre_jour(tmp_path):
    from checkmate_watcher.watcher import _bump_daily, evening_message

    state = StateStore(tmp_path / "s.json")
    _bump_daily(state, "detections", datetime(2026, 11, 16, 10, 0))
    assert evening_message(state, datetime(2026, 11, 17, 19, 0)) is None
