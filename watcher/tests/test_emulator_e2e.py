from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from checkmate_watcher.config import (
    CesarConfig,
    Config,
    NotificationConfig,
    Selectors,
    SignatureConfig,
    WatcherConfig,
)
from checkmate_watcher.signature import Point, save_signature
from checkmate_watcher.watcher import run_loop

REPO_ROOT = Path(__file__).resolve().parents[2]
EMULATOR = REPO_ROOT / "emulator" / "server.py"
E2E_ENABLED = os.environ.get("CHECKMATE_E2E") == "1"

pytestmark = pytest.mark.skipif(not E2E_ENABLED, reason="definir CHECKMATE_E2E=1")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def chromium_path() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "brave-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def wait_for_state(base_url: str, attempts: int = 60) -> dict:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(f"{base_url}/api/state", timeout=1) as response:
                return json.loads(response.read())
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
    raise AssertionError("l'emulateur n'a pas demarre")


def post(base_url: str, path: str) -> dict:
    request = urllib.request.Request(f"{base_url}{path}", method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def test_le_watcher_detecte_et_signe_sur_l_emulateur(tmp_path):
    executable = chromium_path()
    if executable is None:
        pytest.skip("aucun Chromium disponible")

    port = free_port()
    process = subprocess.Popen(
        [sys.executable, str(EMULATOR), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"

    try:
        wait_for_state(base_url)
        post(base_url, "/api/attendance/open")

        signature_file = tmp_path / "signature.json"
        save_signature(
            signature_file,
            [Point(10, 10, "start"), Point(60, 40, "move"), Point(120, 20, "end")],
        )

        config = Config(
            cesar=CesarConfig(
                base_url=base_url,
                username="demo",
                password="demo",
                login_path="/connexion",
                dashboard_path="/",
            ),
            watcher=WatcherConfig(
                poll_interval=15,
                auto_sign=True,
                auto_sign_delay=0,
                headless=True,
                executable_path=executable,
                profile_dir=tmp_path / "profile",
                state_file=tmp_path / "state.json",
            ),
            signature=SignatureConfig(file=signature_file, padding_ratio=0.9),
            notifications=NotificationConfig(enabled=False),
            selectors=Selectors.from_dict({}),
        )

        code = asyncio.run(
            asyncio.wait_for(
                run_loop(config, once=True, auto_override=True), timeout=120
            )
        )
        assert code == 0

        state = wait_for_state(base_url)
        assert state["signed"] is True
        assert state["signature_points"] >= 2
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
