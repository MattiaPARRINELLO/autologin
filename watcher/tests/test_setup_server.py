from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import replace

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


def call(
    base: str,
    path: str,
    *,
    token: str,
    payload: dict | None = None,
) -> tuple[int, dict]:
    data = None
    headers = {"X-CheckMate-Token": token}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            parsed = json.loads(body or b"{}")
        except json.JSONDecodeError:
            parsed = {"raw": body.decode(errors="replace")}
        return error.code, parsed


def test_parcours_onboarding(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKMATE_PASSWORD", "secret")
    config = local_config(tmp_path)
    config_path = tmp_path / "config.toml"
    save_config(config_path, config, password_env="CHECKMATE_PASSWORD")

    monkeypatch.setattr(setup_server, "default_env_path", lambda: tmp_path / "env")
    monkeypatch.setattr(
        setup_server, "set_password", lambda service, user, password: True
    )
    monkeypatch.setattr(setup_server, "enable_autostart", lambda exe, cfg: True)
    monkeypatch.setattr(setup_server, "restart_autostart", lambda: True)

    session = SetupSession(config_path, config, "jeton-test")
    server = create_server(session)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = urllib.request.Request(f"{base}/")
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            assert error.code == 403

        with urllib.request.urlopen(f"{base}/?token=jeton-test", timeout=5) as response:
            html = response.read().decode()
        assert "CheckMate" in html
        assert "jeton-test" in html

        status, state = call(base, "/api/state", token="jeton-test")
        assert status == 200
        assert state["base_url"].startswith("https://cesar")

        status, _ = call(
            base,
            "/api/schedule",
            token="jeton-test",
            payload={"days": ["mon"], "windows": ["09:00-10:00"]},
        )
        assert status == 400

        status, _ = call(
            base,
            "/api/credentials",
            token="jeton-test",
            payload={
                "base_url": "https://cesar.example.fr",
                "username": "eleve",
                "password": "secret",
            },
        )
        assert status == 200
        assert config_path.is_file()
        assert (tmp_path / "env").read_text().strip() == 'CHECKMATE_PASSWORD="secret"'

        status, _ = call(
            base,
            "/api/signature",
            token="jeton-test",
            payload={
                "points": [
                    {"x": 1, "y": 2, "type": "start"},
                    {"x": 3, "y": 4, "type": "move"},
                    {"x": 5, "y": 6, "type": "end"},
                ]
            },
        )
        assert status == 200
        assert (tmp_path / "signature.json").is_file()

        status, _ = call(
            base,
            "/api/schedule",
            token="jeton-test",
            payload={"days": ["mon", "tue"], "windows": ["09:00-12:00"]},
        )
        assert status == 200
        reloaded = load_config(config_path, require_password=False)
        assert reloaded.schedule.days == (0, 1)
        assert str(reloaded.schedule.windows[0]) == "09:00-12:00"

        status, _ = call(
            base,
            "/api/finish",
            token="jeton-test",
            payload={"autostart": False},
        )
        assert status == 200
        assert session.finished.wait(2)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_signature_invalide_refusee(tmp_path):
    session = SetupSession(tmp_path / "config.toml", local_config(tmp_path), "jeton")
    try:
        session.save_signature({"points": []})
    except setup_server.SetupError as exc:
        assert "deux points" in str(exc)
    else:
        raise AssertionError("une signature vide doit etre refusee")


def test_identifiants_invalides_refuses(tmp_path):
    session = SetupSession(tmp_path / "config.toml", local_config(tmp_path), "jeton")
    try:
        session.save_credentials({"base_url": "", "username": "x", "password": "y"})
    except setup_server.SetupError as exc:
        assert "adresse" in str(exc)
    else:
        raise AssertionError("une adresse vide doit etre refusee")
