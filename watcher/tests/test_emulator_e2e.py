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
from contextlib import asynccontextmanager, contextmanager
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


# Fixture autouse : isole les diagnostics de chaque test sans appel explicite.
@pytest.fixture(autouse=True)
def diagnostics_isolees(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKMATE_DIAGNOSTICS_DIR", str(tmp_path / "diagnostics"))


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
        except Exception:
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


def _start_process(command: list[str], environment: dict[str, str]):
    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, **environment},
    )


def _stop_process(process) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


@contextmanager
def running_process(command: list[str], environment: dict[str, str]):
    process = _start_process(command, environment)
    try:
        yield process
    finally:
        _stop_process(process)


@contextmanager
def emulator_server(*arguments: str, **environment: str):
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    command = [sys.executable, str(EMULATOR), "--port", str(port), *arguments]
    with running_process(command, environment):
        wait_for_state(base_url)
        yield base_url


@contextmanager
def emulator(*arguments: str, **environment: str):
    executable = chromium_path()
    if executable is None:
        pytest.skip("aucun Chromium disponible")

    with emulator_server(*arguments, **environment) as base_url:
        post(base_url, "/api/attendance/open")
        yield executable, base_url


def _cesar(base_url: str) -> CesarConfig:
    return CesarConfig(
        base_url=base_url,
        username="demo",
        password="demo",
        login_path="/connexion",
        dashboard_path="/",
    )


def _watcher(tmp_path, executable: str) -> WatcherConfig:
    return WatcherConfig(
        poll_interval=15,
        auto_sign=True,
        auto_sign_delay=0,
        headless=True,
        visible_on_sign=False,
        executable_path=executable,
        profile_dir=tmp_path / "profile",
        state_file=tmp_path / "state.json",
    )


def _signature_config(tmp_path, points=None) -> SignatureConfig:
    signature_file = tmp_path / "signature.json"
    save_signature(signature_file, POINTS if points is None else points)
    return SignatureConfig(file=signature_file, padding_ratio=0.9)


def make_config(tmp_path, executable: str, base_url: str, points=None) -> Config:
    return Config(
        cesar=_cesar(base_url),
        watcher=_watcher(tmp_path, executable),
        signature=_signature_config(tmp_path, points),
        notifications=NotificationConfig(enabled=False),
        updates=UpdatesConfig(enabled=False),
        analytics=AnalyticsConfig(enabled=False),
        selectors=Selectors.from_dict({}),
    )


def run_once(config: Config, timeout: float) -> int:
    coroutine = run_loop(config, once=True, auto_override=True)
    return asyncio.run(asyncio.wait_for(coroutine, timeout=timeout))


def run_watcher(tmp_path, base_url, executable, points=None, timeout=120) -> int:
    config = make_config(tmp_path, executable, base_url, points=points)
    return run_once(config, timeout)


@asynccontextmanager
async def session_ouverte(config: Config):
    session = CesarSession(config)
    await session.open(headless=True)
    try:
        await session._goto_dashboard()
        await session._ensure_logged_in()
        yield session
    finally:
        await session.close()


async def _sign_et_attendre(config: Config) -> tuple[str, float, int]:
    async with session_ouverte(config) as session:
        started = time.monotonic()
        confirmation = await session.sign(POINTS)
        elapsed = time.monotonic() - started
        remaining = await session.page.locator(".buttonPresent").count()
        return confirmation, elapsed, remaining


async def _sign_et_mesurer(config: Config) -> tuple[str, float]:
    async with session_ouverte(config) as session:
        started = time.monotonic()
        confirmation = await session.sign(POINTS)
        return confirmation, time.monotonic() - started


async def _signer_avec_html(config: Config) -> tuple[str, str]:
    async with session_ouverte(config) as session:
        html = await session.page.content()
        return html, await session.sign(POINTS)


def _run_sur_emulateur(tmp_path, *arguments: str) -> tuple[int, dict]:
    with emulator(*arguments) as (executable, base_url):
        config = make_config(tmp_path, executable, base_url)
        return run_once(config, 120), wait_for_state(base_url)


def test_le_watcher_detecte_et_signe_sur_l_emulateur(tmp_path):
    with emulator() as (executable, base_url):
        code = run_once(make_config(tmp_path, executable, base_url), 120)
        assert code == 0
        state = wait_for_state(base_url)
        assert state["signed"] is True
        assert state["signature_points"] >= 2


def test_une_signature_reduite_a_un_point_ne_signe_pas(tmp_path):
    with emulator() as (executable, base_url):
        points = [Point(20, 20, "start"), Point(20, 20, "end")]
        code = run_watcher(tmp_path, base_url, executable, points=points, timeout=60)
        assert code == 2
        assert wait_for_state(base_url)["signed"] is False


def test_sign_attend_la_disparition_du_bouton(tmp_path):
    with emulator(ATTENDANCE_CLOSE_DELAY_MS="2000") as (executable, base_url):
        config = make_config(tmp_path, executable, base_url)
        scenario = _sign_et_attendre(config)
        confirmation, elapsed, remaining = asyncio.run(
            asyncio.wait_for(scenario, timeout=120)
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
    code, state = _run_sur_emulateur(tmp_path, "--scenario", str(SCENARIO))
    assert code == 0
    assert state["signed"] is True
    assert state["signature_points"] >= 2


def test_le_scenario_respecte_le_delai_de_fermeture(tmp_path):
    arguments = ("--scenario", str(SCENARIO), "--attendance-close-delay-ms", "1500")
    with emulator(*arguments) as (executable, base_url):
        config = make_config(tmp_path, executable, base_url)
        scenario = _sign_et_mesurer(config)
        confirmation, elapsed = asyncio.run(asyncio.wait_for(scenario, timeout=120))
        assert "prise en compte" in confirmation.lower()
        assert elapsed >= 1.5
        assert wait_for_state(base_url)["signed"] is True


def test_le_watcher_signe_avec_une_animation_lente(tmp_path):
    with emulator("--variant", "slow-animation") as (executable, base_url):
        config = make_config(tmp_path, executable, base_url)
        scenario = _signer_avec_html(config)
        html, confirmation = asyncio.run(asyncio.wait_for(scenario, timeout=120))
        assert "modal-in" in html
        assert "prise en compte" in confirmation.lower()
        assert wait_for_state(base_url)["signed"] is True


def test_le_watcher_signe_quand_le_canvas_ignore_les_evenements_pointer(tmp_path):
    with emulator("--variant", "mouse-events-only") as (executable, base_url):
        config = make_config(tmp_path, executable, base_url)
        scenario = _signer_avec_html(config)
        html, confirmation = asyncio.run(asyncio.wait_for(scenario, timeout=120))
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


EXPECTED_PAGES = ["accueil", "accueil-signe", "confirmation", "connexion", "signature"]


def _capturer(source_url: str, output: Path) -> None:
    coroutine = capture_scenario_pages(source_url, output)
    asyncio.run(asyncio.wait_for(coroutine, timeout=120))
    sanitize(output)
    write_scenario(output, "capture-emulateur")


def _assert_capture(output: Path, source_url: str) -> None:
    pages = sorted(page.stem for page in (output / "pages").glob("*.html"))
    assert pages == EXPECTED_PAGES
    for page in (output / "pages").glob("*.html"):
        assert source_url not in page.read_text(encoding="utf-8")


def test_une_capture_de_cesar_devient_un_scenario_jouable(tmp_path):
    output = tmp_path / "capture"
    with emulator("--scenario", str(SCENARIO)) as (_, source_url):
        _capturer(source_url, output)
        _assert_capture(output, source_url)

    with emulator("--scenario", str(output)) as (executable, base_url):
        code = run_watcher(tmp_path, base_url, executable)
        assert code == 0
        assert wait_for_state(base_url)["signed"] is True


def _connexion(base_url: str):
    port = int(base_url.rsplit(":", 1)[1])
    return http.client.HTTPConnection("127.0.0.1", port, timeout=5)


def _poster(connection, path: str, corps: str):
    connection.request(
        "POST",
        path,
        body=corps,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return connection.getresponse()


def post_formulaire(base_url: str, path: str, corps: str) -> tuple[int, dict]:
    connection = _connexion(base_url)
    try:
        response = _poster(connection, path, corps)
        return response.status, dict(response.getheaders())
    finally:
        connection.close()


def test_la_connexion_accepte_les_champs_du_formulaire_cesar():
    with emulator_server() as base_url:
        status, entetes = post_formulaire(
            base_url, "/connexion", "_username=demo&_password=demo"
        )
        assert status == 303
        assert "cesar_session=" in entetes.get("Set-Cookie", "")
