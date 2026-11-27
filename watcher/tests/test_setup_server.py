from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import replace

import pytest

from checkmate_watcher import setup_server
from checkmate_watcher.config import default_config, load_config, save_config
from checkmate_watcher.setup_server import SetupSession, create_server


def local_config(tmp_path):
    config = default_config()
    return replace(
        config,
        watcher=replace(
            config.watcher,
            profile_dir=tmp_path / "profile",
            state_file=tmp_path / "state.json",
        ),
        signature=replace(config.signature, file=tmp_path / "signature.json"),
    )


def _decode(raw: bytes) -> dict:
    try:
        return json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return {"raw": raw.decode(errors="replace")}


def _open(request: urllib.request.Request) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def _build_request(
    base: str, path: str, token: str, payload: dict | None
) -> urllib.request.Request:
    headers = {"X-CheckMate-Token": token}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(base + path, data=data, headers=headers)


def call(
    base: str,
    path: str,
    *,
    token: str,
    payload: dict | None = None,
) -> tuple[int, dict]:
    request = _build_request(base, path, token, payload)
    status, body = _open(request)
    return status, _decode(body)


TOKEN = "jeton-test"

SIGNATURE_RAW = json.dumps(
    {
        "signatureData": [
            {"x": 1, "y": 2, "type": "start"},
            {"x": 3, "y": 4, "type": "end"},
        ]
    }
)

SIGNATURE_POINTS = [
    {"x": 1, "y": 2, "type": "start"},
    {"x": 3, "y": 4, "type": "move"},
    {"x": 5, "y": 6, "type": "end"},
]


def _prepare_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKMATE_PASSWORD", "secret")
    config = local_config(tmp_path)
    path = tmp_path / "config.toml"
    save_config(path, config, password_env="CHECKMATE_PASSWORD")
    monkeypatch.setattr(
        setup_server, "default_env_path", lambda: tmp_path / "env"
    )
    monkeypatch.setattr(setup_server, "set_password", lambda *args: True)
    monkeypatch.setattr(setup_server, "enable_autostart", lambda *args: True)
    monkeypatch.setattr(setup_server, "restart_autostart", lambda: True)
    return SetupSession(path, config, TOKEN), path


@contextmanager
def _serveur(session):
    server = create_server(session)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def serveur(tmp_path, monkeypatch):
    session, path = _prepare_setup(tmp_path, monkeypatch)
    with _serveur(session) as base:
        yield base, session, path, tmp_path


def page(base):
    with urllib.request.urlopen(
        f"{base}/?token={TOKEN}", timeout=5
    ) as response:
        return response.read().decode()


def etat(base):
    return call(base, "/api/state", token=TOKEN)


def planning(base, days, windows):
    return call(
        base,
        "/api/schedule",
        token=TOKEN,
        payload={"days": days, "windows": windows},
    )


def credentials(base, url, user, password):
    payload = {"base_url": url, "username": user, "password": password}
    return call(base, "/api/credentials", token=TOKEN, payload=payload)


def signature(base, points):
    return call(
        base, "/api/signature", token=TOKEN, payload={"points": points}
    )


def import_signature(base, raw):
    return call(
        base, "/api/import-signature", token=TOKEN, payload={"raw": raw}
    )


def finish(base):
    return call(base, "/api/finish", token=TOKEN, payload={"autostart": False})


def _verifier_403(base):
    request = urllib.request.Request(f"{base}/")
    try:
        urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        assert error.code == 403


def _verifier_page(base):
    html = page(base)
    assert "CheckMate" in html
    assert TOKEN in html
    assert 'value="09:00-12:00, 13:30-16:30"' in html
    assert '<input type="checkbox" value="mon" checked>' in html


def _verifier_etat(base):
    status, state = etat(base)
    assert status == 200
    assert state["base_url"].startswith("https://cesar")


def _verifier_planning_refuse(base):
    status, _ = planning(base, ["mon"], ["09:00-10:00"])
    assert status == 400


def _verifier_credentials(base, config_path, tmp_path):
    status, _ = credentials(
        base, "https://cesar.example.fr", "eleve", "secret"
    )
    assert status == 200
    assert config_path.is_file()
    if sys.platform.startswith("linux"):
        assert (
            tmp_path / "env"
        ).read_text().strip() == 'CHECKMATE_PASSWORD="secret"'


def _verifier_signatures(base, tmp_path):
    assert import_signature(base, SIGNATURE_RAW)[0] == 200
    assert import_signature(base, "pas du json")[0] == 400
    assert signature(base, SIGNATURE_POINTS)[0] == 200
    assert (tmp_path / "signature.json").is_file()


def _verifier_planning_accepte(base, config_path):
    status, _ = planning(base, ["mon", "tue"], ["09:00-12:00"])
    assert status == 200
    reloaded = load_config(config_path, require_password=False)
    assert reloaded.schedule.days == (0, 1)
    assert str(reloaded.schedule.windows[0]) == "09:00-12:00"


def _verifier_finish(base, session):
    status, _ = finish(base)
    assert status == 200
    assert session.finished.wait(2)


def test_parcours_onboarding(serveur):
    base, session, config_path, tmp_path = serveur
    _verifier_403(base)
    _verifier_page(base)
    _verifier_etat(base)
    _verifier_planning_refuse(base)
    _verifier_credentials(base, config_path, tmp_path)
    _verifier_signatures(base, tmp_path)
    _verifier_planning_accepte(base, config_path)
    _verifier_finish(base, session)


def _fake_session(monkeypatch, calls):
    class FakeSession:
        def __init__(self, config):
            calls.append("init")

        async def open(self, headless=None):
            calls.append(f"open:{headless}")

        async def login(self):
            calls.append("login")

        async def close(self):
            calls.append("close")

    monkeypatch.setattr(setup_server, "CesarSession", FakeSession)


def test_le_test_de_connexion_reutilise_la_session(tmp_path, monkeypatch):
    calls: list[str] = []
    _fake_session(monkeypatch, calls)
    message = setup_server._test_connection(
        local_config(tmp_path), "https://cesar.example.fr", "eleve", "secret"
    )
    assert message == "Connexion reussie."
    assert calls == ["init", "open:True", "login", "close"]


def test_signature_invalide_refusee(tmp_path):
    session = SetupSession(
        tmp_path / "config.toml", local_config(tmp_path), "jeton"
    )
    try:
        session.save_signature({"points": []})
    except setup_server.SetupError as exc:
        assert "deux points" in str(exc)
    else:
        raise AssertionError("une signature vide doit etre refusee")


def test_identifiants_invalides_refuses(tmp_path):
    session = SetupSession(
        tmp_path / "config.toml", local_config(tmp_path), "jeton"
    )
    try:
        session.save_credentials(
            {"base_url": "", "username": "x", "password": "y"}
        )
    except setup_server.SetupError as exc:
        assert "adresse" in str(exc)
    else:
        raise AssertionError("une adresse vide doit etre refusee")


def test_active_days_tries_par_index(tmp_path):
    config = local_config(tmp_path)
    config = replace(config, schedule=replace(config.schedule, days=(6, 0, 2)))
    session = SetupSession(tmp_path / "config.toml", config, "jeton")
    assert session._active_days() == ["mon", "wed", "sun"]


def test_escape_env_value_double_antislashs_et_guillemets():
    assert setup_server._escape_env_value('a\\b"c') == 'a\\\\b\\"c'
    assert setup_server._escape_env_value("plain") == "plain"


def test_autostart_outcome(monkeypatch):
    assert setup_server._autostart_outcome(False, True)[1] == "disabled"
    assert setup_server._autostart_outcome(True, False)[1] == "failed"
    monkeypatch.setattr(sys, "platform", "linux")
    assert setup_server._autostart_outcome(True, True)[1] == "installed"
    monkeypatch.setattr(sys, "platform", "win32")
    message, state = setup_server._autostart_outcome(True, True)
    assert state == "installed"
    assert "prochaine ouverture de session" in message


def test_publie_et_retire_le_runtime_de_l_assistant(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(setup_server, "data_dir", lambda: tmp_path)
    session = SimpleNamespace(token="jeton-assistant")
    server = SimpleNamespace(server_address=("127.0.0.1", 4321))
    setup_server.write_setup_runtime(session, server)
    path = setup_server.setup_runtime_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["port"] == 4321
    assert payload["token"] == "jeton-assistant"
    assert payload["pid"] == os.getpid()
    assert path.stat().st_mode & 0o777 == 0o600
    setup_server.remove_setup_runtime()
    assert not path.exists()


def test_ne_retire_pas_le_runtime_d_un_autre_processus(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_server, "data_dir", lambda: tmp_path)
    path = setup_server.setup_runtime_path()
    path.write_text(
        json.dumps({"pid": 1, "port": 1, "token": "x"}), encoding="utf-8"
    )
    setup_server.remove_setup_runtime()
    assert path.exists()
