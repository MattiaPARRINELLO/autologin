from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import datetime

from checkmate_watcher.config import UpdatesConfig, default_config
from checkmate_watcher.state import StateStore
from checkmate_watcher.status_server import StatusSession, create_server


def call(base: str, path: str, *, token: str, payload: dict | None = None):
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
        return error.code, json.loads(error.read() or b"{}")


def test_tableau_de_bord(tmp_path):
    config = default_config()
    state = StateStore(tmp_path / "state.json")
    session = StatusSession(
        config,
        tmp_path / "config.toml",
        state,
        datetime.now(),
    )
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

        with urllib.request.urlopen(
            f"{base}/?token={session.token}", timeout=5
        ) as response:
            html = response.read().decode()
        assert "CheckMate" in html
        assert session.token in html

        status, snapshot = call(base, "/api/status", token=session.token)
        assert status == 200
        assert snapshot["version"]
        assert snapshot["channel"] == "stable"
        assert "counters" in snapshot

        setattr(session, "test_notification", lambda: {"ok": True, "message": "test"})
        status, result = call(
            base,
            "/api/action",
            token=session.token,
            payload={"action": "test-notification"},
        )
        assert status == 200
        assert result["message"] == "test"

        status, result = call(
            base,
            "/api/action",
            token=session.token,
            payload={"action": "inconnue"},
        )
        assert status == 400
        assert "inconnue" in result["error"]

        status, result = call(
            base,
            "/api/action",
            token=session.token,
            payload={"action": "quit"},
        )
        assert status == 200
        assert session.stop_event.wait(2)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_check_update_utilise_le_canal(tmp_path, monkeypatch):
    from checkmate_watcher import status_server
    from checkmate_watcher.updates import Release, parse_version

    seen = []
    release = Release(
        tag="watcher-v0.6.0-beta.1",
        version=parse_version("0.6.0-beta.1"),
        url="https://example.com",
        name="beta",
        prerelease=True,
    )

    def fake_check(current, **kwargs):
        seen.append(kwargs.get("channel"))
        return release

    monkeypatch.setattr(status_server, "check_for_update", fake_check)
    config = replace(
        default_config(),
        updates=UpdatesConfig(channel="beta"),
    )
    session = StatusSession(
        config,
        tmp_path / "config.toml",
        StateStore(tmp_path / "state.json"),
        datetime.now(),
    )
    result = session.check_update()
    assert seen == ["beta"]
    assert result["available"] is True
    assert result["channel"] == "beta"
    assert result["version"] == "0.6.0-beta.1"
