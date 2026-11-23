from __future__ import annotations

import asyncio
import http.client
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
from checkmate_watcher.capture import CaptureSession, sanitize, write_scenario
from checkmate_watcher.cesar import CesarSession
from checkmate_watcher.config import (
    AnalyticsConfig,
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
SCENARIO = REPO_ROOT / "emulator" / "scenarios" / "cesar-simplifie"
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


def fetch(base_url: str, path: str) -> tuple[str, str]:
    with urllib.request.urlopen(f"{base_url}{path}", timeout=5) as response:
        content_type = response.headers.get("Content-Type", "")
        return content_type, response.read().decode("utf-8")


def post(base_url: str, path: str) -> dict:
    request = urllib.request.Request(f"{base_url}{path}", method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


POINTS = [Point(10, 10, "start"), Point(60, 40, "move"), Point(120, 20, "end")]


@contextmanager
def emulator_server(*arguments: str, **environment: str):
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, str(EMULATOR), "--port", str(port), *arguments],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, **environment},
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        wait_for_state(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


@contextmanager
def emulator(*arguments: str, **environment: str):
    executable = chromium_path()
    if executable is None:
        pytest.skip("aucun Chromium disponible")

    with emulator_server(*arguments, **environment) as base_url:
        post(base_url, "/api/attendance/open")
        yield executable, base_url


def make_config(tmp_path, executable: str, base_url: str, points=None) -> Config:
    signature_file = tmp_path / "signature.json"
    save_signature(signature_file, POINTS if points is None else points)
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
        analytics=AnalyticsConfig(enabled=False),
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


def test_une_signature_reduite_a_un_point_ne_signe_pas(tmp_path):
    with emulator() as (executable, base_url):
        config = make_config(
            tmp_path,
            executable,
            base_url,
            points=[Point(20, 20, "start"), Point(20, 20, "end")],
        )
        code = asyncio.run(
            asyncio.wait_for(
                run_loop(config, once=True, auto_override=True), timeout=60
            )
        )
        assert code == 2

        state = wait_for_state(base_url)
        assert state["signed"] is False


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


def test_le_mode_scenario_sert_les_pages_capturees():
    with emulator("--scenario", str(SCENARIO)) as (_, base_url):
        content_type, html = fetch(base_url, "/connexion")
        assert content_type.startswith("text/html")
        assert 'data-scenario="cesar-simplifie"' in html
        assert "/assets/cesar-lib.js" in html

        css_type, css = fetch(base_url, "/assets/cesar.css")
        assert css_type == "text/css"
        assert "--cesar-accent" in css


def test_le_watcher_detecte_et_signe_sur_un_scenario_capture(tmp_path):
    with emulator("--scenario", str(SCENARIO)) as (executable, base_url):
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


def test_le_scenario_respecte_le_delai_de_fermeture(tmp_path):
    with emulator(
        "--scenario",
        str(SCENARIO),
        "--attendance-close-delay-ms",
        "1500",
    ) as (executable, base_url):
        config = make_config(tmp_path, executable, base_url)

        async def scenario() -> tuple[str, float]:
            session = CesarSession(config)
            await session.open(headless=True)
            try:
                await session._goto_dashboard()
                await session._ensure_logged_in()
                started = time.monotonic()
                confirmation = await session.sign(POINTS)
                return confirmation, time.monotonic() - started
            finally:
                await session.close()

        confirmation, elapsed = asyncio.run(asyncio.wait_for(scenario(), timeout=120))

        assert "prise en compte" in confirmation.lower()
        assert elapsed >= 1.5
        assert wait_for_state(base_url)["signed"] is True


def test_le_watcher_signe_avec_une_animation_lente(tmp_path):
    with emulator("--variant", "slow-animation") as (executable, base_url):
        config = make_config(tmp_path, executable, base_url)

        async def scenario() -> tuple[str, str]:
            session = CesarSession(config)
            await session.open(headless=True)
            try:
                await session._goto_dashboard()
                await session._ensure_logged_in()
                html = await session.page.content()
                return html, await session.sign(POINTS)
            finally:
                await session.close()

        html, confirmation = asyncio.run(asyncio.wait_for(scenario(), timeout=120))

        assert "modal-in" in html
        assert "prise en compte" in confirmation.lower()
        assert wait_for_state(base_url)["signed"] is True


def test_le_watcher_signe_quand_le_canvas_ignore_les_evenements_pointer(tmp_path):
    with emulator("--variant", "mouse-events-only") as (executable, base_url):
        config = make_config(tmp_path, executable, base_url)

        async def scenario() -> tuple[str, str]:
            session = CesarSession(config)
            await session.open(headless=True)
            try:
                await session._goto_dashboard()
                await session._ensure_logged_in()
                html = await session.page.content()
                return html, await session.sign(POINTS)
            finally:
                await session.close()

        html, confirmation = asyncio.run(asyncio.wait_for(scenario(), timeout=120))

        assert "mousemove" in html
        assert "pointerdown" not in html
        assert "prise en compte" in confirmation.lower()
        assert wait_for_state(base_url)["signed"] is True


async def draw_signature(page) -> None:
    canvas = page.locator("canvas[data-written-signature-target]")
    box = await canvas.bounding_box()
    x = box["x"] + 24
    y = box["y"] + 30
    await page.mouse.move(x, y)
    await page.mouse.down()
    for step in range(1, 6):
        await page.mouse.move(x + step * 28, y + step * 9)
    await page.mouse.up()


async def capture_scenario_pages(base_url: str, output: Path) -> None:
    session = CaptureSession(output, base_url)
    await session.start(headless=True)
    try:
        await session.goto("/connexion")
        await session.save_step("connexion")

        await session.page.fill("input#username", "demo")
        await session.page.fill("input#password", "demo")
        await session.page.click("button[type='submit'].btn-primary")
        await session.save_step("accueil")

        await session.page.click("button.buttonPresent")
        await session.page.wait_for_selector(
            "canvas[data-written-signature-target]", state="visible"
        )
        await session.save_step("signature")

        await draw_signature(session.page)
        await session.page.click("button[data-live-action-param='signed']")
        await session.page.wait_for_function(
            "() => document.querySelector('.swal2-html-container')"
            ".textContent.includes('prise en compte')"
        )
        await session.save_step("confirmation")

        await session.page.reload(wait_until="networkidle")
        await session.save_step("accueil-signe")
    finally:
        await session.close()


def test_une_capture_de_cesar_devient_un_scenario_jouable(tmp_path):
    output = tmp_path / "capture"
    with emulator("--scenario", str(SCENARIO)) as (_, source_url):
        asyncio.run(
            asyncio.wait_for(capture_scenario_pages(source_url, output), timeout=120)
        )

    sanitize(output)
    write_scenario(output, "capture-emulateur")

    pages = sorted(page.stem for page in (output / "pages").glob("*.html"))
    assert pages == [
        "accueil",
        "accueil-signe",
        "confirmation",
        "connexion",
        "signature",
    ]
    for page in (output / "pages").glob("*.html"):
        assert source_url not in page.read_text(encoding="utf-8")

    with emulator("--scenario", str(output)) as (executable, base_url):
        config = make_config(tmp_path, executable, base_url)
        code = asyncio.run(
            asyncio.wait_for(
                run_loop(config, once=True, auto_override=True), timeout=120
            )
        )
        assert code == 0
        assert wait_for_state(base_url)["signed"] is True


def test_la_connexion_accepte_les_champs_du_formulaire_cesar():
    with emulator_server() as base_url:
        port = int(base_url.rsplit(":", 1)[1])
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request(
            "POST",
            "/connexion",
            body="_username=demo&_password=demo",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = connection.getresponse()

        assert response.status == 303
        assert "cesar_session=" in (response.getheader("Set-Cookie") or "")
        connection.close()
