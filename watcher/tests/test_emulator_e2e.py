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
from contextlib import contextmanager
from pathlib import Path

import pytest

from checkmate_watcher.browser import bundled_chromium_path
from checkmate_watcher.cesar import CesarSession
from checkmate_watcher.config import (
    CesarConfig,
    Config,
    NotificationConfig,
    Selectors,
    SignatureConfig,
    UpdatesConfig,
    WatcherConfig,
)
from checkmate_watcher.signature import Point, save_signature
from checkmate_watcher.watcher import run_loop

REPO_ROOT = Path(__file__).resolve().parents[2]
EMULATOR = REPO_ROOT / "emulator" / "server.py"
E2E_ENABLED = os.environ.get("CHECKMATE_E2E") == "1"

pytestmark = pytest.mark.skipif(
    not E2E_ENABLED,
    reason=(
        "tests e2e desactives : definir CHECKMATE_E2E=1 "
        "(Chromium requis, l'emulateur est lance par le test)"
    ),
)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def chromium_path() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "brave-browser"):
        path = shutil.which(name)
        if path:
            return path
    return bundled_chromium_path()


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


POINTS = [Point(10, 10, "start"), Point(60, 40, "move"), Point(120, 20, "end")]


@contextmanager
def emulator(**environment: str):
    executable = chromium_path()
    if executable is None:
        pytest.skip("aucun Chromium disponible")

    port = free_port()
    process = subprocess.Popen(
        [sys.executable, str(EMULATOR), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, **environment},
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        wait_for_state(base_url)
        post(base_url, "/api/attendance/open")
        yield executable, base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def make_config(tmp_path, executable: str, base_url: str) -> Config:
    signature_file = tmp_path / "signature.json"
    save_signature(signature_file, POINTS)
    return Config(
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
            visible_on_sign=False,
            executable_path=executable,
            profile_dir=tmp_path / "profile",
            state_file=tmp_path / "state.json",
        ),
        signature=SignatureConfig(file=signature_file, padding_ratio=0.9),
        notifications=NotificationConfig(enabled=False),
        updates=UpdatesConfig(enabled=False),
        selectors=Selectors.from_dict({}),
    )


def test_le_watcher_detecte_et_signe_sur_l_emulateur(tmp_path):
    with emulator() as (executable, base_url):
        config = make_config(tmp_path, executable, base_url)
        code = asyncio.run(
            asyncio.wait_for(
                run_loop(config, once=True, auto_override=True), timeout=120
            )
        )
        assert code == 0

        state = wait_for_state(base_url)
        assert state["signed"] is True
        assert state["signature_points"] >= 2


def test_sign_attend_la_disparition_du_bouton(tmp_path):
    with emulator(ATTENDANCE_CLOSE_DELAY_MS="2000") as (executable, base_url):
        config = make_config(tmp_path, executable, base_url)

        async def scenario() -> tuple[str, float, int]:
            session = CesarSession(config)
            await session.open(headless=True)
            try:
                await session._goto_dashboard()
                await session._ensure_logged_in()
                started = time.monotonic()
                confirmation = await session.sign(POINTS)
                elapsed = time.monotonic() - started
                # Au retour de sign(), le bouton doit deja avoir disparu du DOM.
                remaining = await session.page.locator(".buttonPresent").count()
                return confirmation, elapsed, remaining
            finally:
                await session.close()

        confirmation, elapsed, remaining = asyncio.run(
            asyncio.wait_for(scenario(), timeout=120)
        )

        assert "prise en compte" in confirmation.lower()
        assert remaining == 0
        assert elapsed >= 2.0
        assert wait_for_state(base_url)["signed"] is True
