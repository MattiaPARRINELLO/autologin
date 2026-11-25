from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime

import pytest

from checkmate_watcher import status_server
from checkmate_watcher.config import (
    UpdatesConfig,
    default_config,
    load_config,
    save_config,
)
from checkmate_watcher.state import StateStore
from checkmate_watcher.status_server import StatusSession, create_server
from checkmate_watcher.updates import Release, parse_version


def _build_request(
    base: str, path: str, *, token: str, payload: dict | None = None
) -> urllib.request.Request:
    headers = {"X-CheckMate-Token": token}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(base + path, data=data, headers=headers)


def _decode_body(body: bytes) -> dict:
    return json.loads(body or b"{}")


def _perform(request: urllib.request.Request) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, _decode_body(response.read())
    except urllib.error.HTTPError as error:
        return error.code, _decode_body(error.read())


def call(
    base: str, path: str, *, token: str, payload: dict | None = None
) -> tuple[int, dict]:
    request = _build_request(base, path, token=token, payload=payload)
    return _perform(request)


def _page_sans_token(base: str) -> int:
    try:
        with urllib.request.urlopen(base + "/", timeout=5):
            return 200
    except urllib.error.HTTPError as error:
        return error.code


def _page_avec_token(base: str, token: str, *, timeout: int = 5) -> str:
    with urllib.request.urlopen(
        f"{base}/?token={token}", timeout=timeout
    ) as response:
        return response.read().decode()


def _statut(base: str, token: str) -> tuple[int, dict]:
    return call(base, "/api/status", token=token)


def _action(base: str, token: str, action: str) -> tuple[int, dict]:
    return call(base, "/api/action", token=token, payload={"action": action})


def _attendre_arret(session, *, delai: int = 2) -> bool:
    return session.stop_event.wait(delai)


def _session(tmp_path) -> StatusSession:
    state = StateStore(tmp_path / "state.json")
    config = default_config()
    return StatusSession(
        config, tmp_path / "config.toml", state, datetime.now()
    )


def _arreter(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@contextmanager
def _serveur(tmp_path) -> Iterator[tuple[str, StatusSession]]:
    session = _session(tmp_path)
    server = create_server(session)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield base, session
    finally:
        _arreter(server, thread)


@pytest.fixture
def serveur(tmp_path):
    with _serveur(tmp_path) as valeurs:
        yield valeurs


def _verifier_entete(base: str, token: str) -> None:
    assert _page_sans_token(base) == 403
    html = _page_avec_token(base, token)
    assert "CheckMate" in html
    assert token in html


def _verifier_statut(base: str, token: str) -> None:
    statut, snapshot = _statut(base, token)
    assert statut == 200
    assert snapshot["version"]
    assert snapshot["channel"] == default_config().updates.channel
    assert "counters" in snapshot


def _verifier_notification(base: str, session) -> None:
    setattr(
        session, "test_notification", lambda: {"ok": True, "message": "test"}
    )
    statut, resultat = _action(base, session.token, "test-notification")
    assert statut == 200
    assert resultat["message"] == "test"


def _verifier_action_inconnue(base: str, session) -> None:
    statut, resultat = _action(base, session.token, "inconnue")
    assert statut == 400
    assert "inconnue" in resultat["error"]


def _verifier_quit(base: str, session) -> None:
    statut, _ = _action(base, session.token, "quit")
    assert statut == 200
    assert _attendre_arret(session)


def test_tableau_de_bord(serveur):
    base, session = serveur
    _verifier_entete(base, session.token)
    _verifier_statut(base, session.token)
    _verifier_notification(base, session)
    _verifier_action_inconnue(base, session)
    _verifier_quit(base, session)


def _beta_release() -> Release:
    return Release(
        tag="watcher-v0.6.0-beta.1",
        version=parse_version("0.6.0-beta.1"),
        url="https://example.com",
        name="beta",
        prerelease=True,
    )


def _capture_channel(monkeypatch) -> list:
    seen = []
    release = _beta_release()

    def fake_check(current, **kwargs):
        seen.append(kwargs.get("channel"))
        return release

    monkeypatch.setattr(status_server, "check_for_update", fake_check)
    return seen


def _beta_session(tmp_path) -> StatusSession:
    config = replace(default_config(), updates=UpdatesConfig(channel="beta"))
    return StatusSession(
        config,
        tmp_path / "config.toml",
        StateStore(tmp_path / "state.json"),
        datetime.now(),
    )


def test_le_resume_de_mise_a_jour_peut_etre_ferme(tmp_path):
    session = _session(tmp_path)
    note = {"version": "0.7.0", "title": "Mise a jour terminee."}
    session.set_release_note(note)
    assert session.snapshot()["release_note"] == note

    result = session.dismiss_release()

    assert result["ok"] is True
    assert session.snapshot()["release_note"] is None
    assert session.state.get_meta("release.celebrated_version") == "0.7.0"


def test_le_message_stable_sur_beta_explique_le_maintien(monkeypatch):
    monkeypatch.setattr(status_server, "__version__", "0.7.0-beta.2")
    assert "restes" in status_server._channel_message("stable")


def _required_release() -> Release:
    return Release(
        tag="watcher-v0.8.0",
        version=parse_version("0.8.0"),
        url="https://example.com",
        name="obligatoire",
        prerelease=False,
        required_reason="faille de signature",
        markers_declared=True,
    )


def test_le_statut_signale_une_version_obligatoire(tmp_path):
    session = _session(tmp_path)
    session.set_blocked(_required_release())
    snapshot = session.snapshot()
    assert snapshot["mode"] == "blocked"
    assert snapshot["label"] == "Mise a jour obligatoire"
    assert snapshot["blocked"]["version"] == "0.8.0"
    assert snapshot["blocked"]["reason"] == "faille de signature"


def _migration_release() -> Release:
    return Release(
        tag="watcher-v0.7.5",
        version=parse_version("0.7.5"),
        url="https://example.com",
        name="migration",
        prerelease=False,
        migration_reason="format v2",
        markers_declared=True,
    )


def test_le_statut_signale_une_migration(tmp_path):
    session = _session(tmp_path)
    session.set_migration(_migration_release())
    snapshot = session.snapshot()
    assert snapshot["migration"]["version"] == "0.7.5"
    assert snapshot["migration"]["reason"] == "format v2"
    assert snapshot["blocked"] is None


def _channel_config():
    base = default_config()
    cesar = replace(base.cesar, username="eleve", password="secret")
    return replace(base, cesar=cesar, updates=UpdatesConfig(channel="stable"))


def test_le_canal_beta_se_change_et_se_persiste(tmp_path):
    config = _channel_config()
    path = tmp_path / "config.toml"
    save_config(path, config, password="secret")
    session = StatusSession(
        config, path, StateStore(tmp_path / "state.json"), datetime.now()
    )
    result = session.action("set-channel", {"channel": "beta"})
    assert result["channel"] == "beta"
    assert load_config(path).updates.channel == "beta"


def test_check_update_utilise_le_canal(tmp_path, monkeypatch):
    session = _beta_session(tmp_path)
    seen = _capture_channel(monkeypatch)
    result = session.check_update()
    assert seen == ["beta"]
    assert result["available"] is True
    assert result["channel"] == "beta"
    assert result["version"] == "0.6.0-beta.1"
