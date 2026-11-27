from __future__ import annotations

import asyncio

import pytest

from checkmate_watcher.cesar import (
    CALENDAR_IDENTITY_JS,
    CANVAS_HITTABLE_JS,
    EVENT_DRAW_JS,
    INK_DIFF_JS,
    PERFORMANCE_BROWSER_ARGS,
    CesarSession,
    SignError,
    _block_nonessential_request,
    _should_block_request,
    draw_coordinates,
    signal_key,
)
from checkmate_watcher.config import (
    CesarConfig,
    Config,
    NotificationConfig,
    Selectors,
    SignatureConfig,
    WatcherConfig,
)
from checkmate_watcher.signature import FittedPoint


class FakePage:
    """Page minimale : seule l'attente et la duree reelle importent."""

    def __init__(self, wait_seconds: float = 0.02) -> None:
        self.wait_seconds = wait_seconds
        self.waits: list[int] = []

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)
        await asyncio.sleep(self.wait_seconds)


def _cesar_config() -> CesarConfig:
    return CesarConfig(
        base_url="https://cesar.example.fr",
        username="eleve",
        password="secret",
    )


def make_config(**sections) -> Config:
    base = {
        "cesar": _cesar_config(),
        "watcher": WatcherConfig(),
        "signature": SignatureConfig(),
        "notifications": NotificationConfig(),
        "selectors": Selectors.from_dict({}),
    }
    return Config(**{**base, **sections})


def make_session(page: FakePage) -> CesarSession:
    session = CesarSession(make_config())
    session.page = page
    return session


class FakeRequest:
    def __init__(
        self,
        resource_type: str,
        url: str,
        *,
        is_navigation_request: bool = False,
    ) -> None:
        self.resource_type = resource_type
        self.url = url
        self.is_navigation_request = is_navigation_request
        self.headers = {"Accept": "text/html"}


class FakeRoute:
    def __init__(
        self,
        resource_type: str,
        url: str,
        *,
        is_navigation_request: bool = False,
    ) -> None:
        self.request = FakeRequest(
            resource_type,
            url,
            is_navigation_request=is_navigation_request,
        )
        self.aborted = False
        self.continued = False
        self.headers = None

    async def abort(self) -> None:
        self.aborted = True

    async def continue_(self, headers=None) -> None:
        self.continued = True
        self.headers = headers


@pytest.mark.parametrize(
    ("resource_type", "url", "blocked"),
    [
        ("image", "https://cesar.example.fr/logo.png", True),
        ("font", "https://cesar.example.fr/font.woff2", True),
        ("media", "https://cesar.example.fr/video.mp4", True),
        ("stylesheet", "https://cesar.example.fr/app.css", False),
        ("script", "https://cesar.example.fr/app.js", False),
        ("xhr", "https://google-analytics.com/collect", True),
        ("fetch", "https://cesar.example.fr/api/status", False),
    ],
)
def test_filtre_des_ressources_non_essentielles(resource_type, url, blocked):
    assert _should_block_request(resource_type, url) is blocked


def test_route_abandonne_les_images_et_conserve_le_css():
    image = FakeRoute("image", "https://cesar.example.fr/logo.png")
    stylesheet = FakeRoute("stylesheet", "https://cesar.example.fr/app.css")

    asyncio.run(_block_nonessential_request(image))
    asyncio.run(_block_nonessential_request(stylesheet))

    assert image.aborted is True
    assert image.continued is False
    assert stylesheet.aborted is False
    assert stylesheet.continued is True


def test_navigation_demande_une_reponse_fraiche():
    route = FakeRoute(
        "document",
        "https://cesar.example.fr/",
        is_navigation_request=True,
    )

    asyncio.run(_block_nonessential_request(route))

    assert route.continued is True
    assert route.headers["Cache-Control"] == "no-cache"


def test_arguments_de_performance_chromium():
    assert "--disable-gpu" in PERFORMANCE_BROWSER_ARGS
    assert "--disable-dev-shm-usage" in PERFORMANCE_BROWSER_ARGS


def always_visible(session: CesarSession) -> None:
    async def first_visible(selectors):
        return object()

    session._first_visible = first_visible


def invisible_after(session: CesarSession, checks: int) -> None:
    calls = {"count": 0}

    async def first_visible(selectors):
        calls["count"] += 1
        return object() if calls["count"] <= checks else None

    session._first_visible = first_visible


def test_wait_for_hidden_disparition_immediate():
    page = FakePage()
    session = make_session(page)
    invisible_after(session, checks=0)

    hidden = asyncio.run(
        session._wait_for_hidden(session.selectors.attendance_button, 1000)
    )

    assert hidden is True
    assert page.waits == []


def test_wait_for_hidden_disparition_retardee():
    page = FakePage(wait_seconds=0)
    session = make_session(page)
    invisible_after(session, checks=2)

    hidden = asyncio.run(
        session._wait_for_hidden(session.selectors.attendance_button, 1000)
    )

    assert hidden is True
    assert page.waits == [250, 250]


def test_wait_for_hidden_timeout():
    page = FakePage()
    session = make_session(page)
    always_visible(session)

    hidden = asyncio.run(
        session._wait_for_hidden(session.selectors.attendance_button, 60)
    )

    assert hidden is False
    assert page.waits


@pytest.mark.parametrize("selectors", [(), ("button.buttonPresent",)])
def test_wait_for_hidden_sans_page(selectors):
    session = make_session(FakePage())
    session.page = None

    assert asyncio.run(session._wait_for_hidden(selectors, 1000)) is False


@pytest.mark.parametrize(
    ("ink", "attendu"),
    [
        (None, False),
        (
            {
                "count": 0,
                "minX": 0,
                "minY": 0,
                "maxX": -1,
                "maxY": -1,
                "width": 600,
                "height": 240,
            },
            True,
        ),
        (
            {
                "count": 12,
                "minX": 300,
                "minY": 120,
                "maxX": 302,
                "maxY": 122,
                "width": 600,
                "height": 240,
            },
            True,
        ),
        (
            {
                "count": 4000,
                "minX": 30,
                "minY": 20,
                "maxX": 560,
                "maxY": 220,
                "width": 600,
                "height": 240,
            },
            False,
        ),
        (
            {
                "count": 900,
                "minX": 40,
                "minY": 118,
                "maxX": 540,
                "maxY": 121,
                "width": 600,
                "height": 240,
            },
            True,
        ),
        (
            {
                "count": 900,
                "minX": 298,
                "minY": 20,
                "maxX": 301,
                "maxY": 220,
                "width": 600,
                "height": 240,
            },
            True,
        ),
    ],
)
def test_ink_is_incomplete(ink, attendu):
    assert CesarSession._ink_is_incomplete(ink) is attendu


def test_draw_coordinates_arrondit_les_points():
    fitted = [FittedPoint(x=1.234, y=5.678), FittedPoint(x=9.0, y=0.5)]

    assert draw_coordinates(fitted) == [[1.23, 5.68], [9.0, 0.5]]


def test_signal_key_utilise_les_uuuids_du_calendrier():
    payload = {
        "course_uuid": "course-1",
        "line_uuid": "line-1",
        "label": "Libelle variable",
        "row": "texte variable",
    }
    other = {**payload, "label": "Autre libelle", "row": "Autre texte"}

    assert signal_key(payload) == signal_key(other)


def test_signal_key_conserve_le_repli_sans_uuid():
    payload = {"action": "present", "row": "cours", "label": "Emargement"}

    assert signal_key(payload)


def test_check_navigateur_utilise_les_uuuids_du_calendrier():
    class Button:
        async def evaluate(self, script):
            return {"action": "present", "row": "cours", "label": "Emargement"}

    class Page:
        async def evaluate(self, script):
            assert script == CALENDAR_IDENTITY_JS
            return {"course_uuid": "course-1", "line_uuid": "line-1"}

    async def no_op():
        return None

    async def button_after_wait(selectors, timeout_ms):
        return Button()

    session = make_session(FakePage())
    session.page = Page()
    session._goto_dashboard = no_op
    session._ensure_logged_in = no_op
    session._find_with_wait = button_after_wait

    signal = asyncio.run(session.check())

    assert signal.key == signal_key(
        {"course_uuid": "course-1", "line_uuid": "line-1"}
    )


class FakeHitCanvas:
    """Canvas dont le hit-test est scripte, pour tester l'attente."""

    def __init__(self, results: list[bool]) -> None:
        self.results = list(results)
        self.current = results[-1] if results else True

    async def evaluate(self, script, arg=None):
        if script is CANVAS_HITTABLE_JS:
            if self.results:
                self.current = self.results.pop(0)
            return self.current
        return True


def test_attend_que_le_canvas_soit_decouvert():
    page = FakePage(wait_seconds=0)
    session = make_session(page)
    canvas = FakeHitCanvas([False, False, True])

    assert (
        asyncio.run(session._wait_until_hittable(canvas, timeout_ms=500))
        is True
    )
    assert len(page.waits) == 2


def test_abandonne_si_le_canvas_reste_recouvert():
    page = FakePage(wait_seconds=0)
    session = make_session(page)
    canvas = FakeHitCanvas([False] * 40)

    assert (
        asyncio.run(session._wait_until_hittable(canvas, timeout_ms=150))
        is False
    )
    assert len(page.waits) >= 1


INK_COMPLETE = {
    "count": 1200,
    "minX": 10,
    "minY": 5,
    "maxX": 290,
    "maxY": 140,
    "width": 300,
    "height": 150,
}
INK_INCOMPLETE = {
    "count": 2,
    "minX": 50,
    "minY": 50,
    "maxX": 51,
    "maxY": 51,
    "width": 300,
    "height": 150,
}


class FakeDiagnostics:
    def __init__(self) -> None:
        self.steps: list[tuple[str, dict | None]] = []
        self.saved = False

    async def add_step(self, label: str, canvas, ink) -> None:
        self.steps.append((label, ink))

    async def save(self, canvas) -> None:
        self.saved = True


class FakeMouse:
    def __init__(self) -> None:
        self.moves = 0

    async def move(self, *args, **kwargs) -> None:
        self.moves += 1

    async def down(self) -> None:
        return None

    async def up(self) -> None:
        return None


class FakeSignatureCanvas:
    def __init__(self, inks: list[dict], *, broken: bool = False) -> None:
        self.inks = list(inks)
        self.broken = broken
        self.scripts: list[dict | str] = []

    async def evaluate(self, script, arg=None):
        if self.broken and script is EVENT_DRAW_JS:
            raise RuntimeError(
                "Target page, context or browser has been closed"
            )
        self.scripts.append(script)
        if script is INK_DIFF_JS:
            return self.inks.pop(0)
        return True

    async def bounding_box(self):
        return {"x": 0, "y": 0, "width": 300, "height": 150}


class FakeSignaturePage(FakePage):
    def __init__(self) -> None:
        super().__init__(wait_seconds=0)
        self.mouse = FakeMouse()

    async def evaluate(self, script, arg=None):
        return True


def _signature_session(page=None) -> CesarSession:
    return make_session(page or FakeSignaturePage())


def test_trace_direct_suffit_quand_l_encre_est_complete():
    session = _signature_session()
    canvas = FakeSignatureCanvas([INK_COMPLETE])
    diagnostics = FakeDiagnostics()

    asyncio.run(
        session._draw_checked_inner(
            canvas,
            {"x": 0, "y": 0, "width": 300, "height": 150},
            [FittedPoint(x=10, y=10), FittedPoint(x=290, y=140)],
            diagnostics,
        )
    )

    assert diagnostics.steps == [("trace direct", INK_COMPLETE)]
    assert session.page.mouse.moves == 0


def test_trace_direct_incomplet_rejoue_a_la_souris():
    session = _signature_session()
    canvas = FakeSignatureCanvas([INK_INCOMPLETE, INK_COMPLETE])
    diagnostics = FakeDiagnostics()

    asyncio.run(
        session._draw_checked_inner(
            canvas,
            {"x": 0, "y": 0, "width": 300, "height": 150},
            [FittedPoint(x=10, y=10), FittedPoint(x=290, y=140)],
            diagnostics,
        )
    )

    assert [label for label, _ in diagnostics.steps] == [
        "trace direct",
        "rejeu souris",
    ]
    assert session.page.mouse.moves > 0


def test_diagnostic_enregistre_si_le_trace_est_interrompu():
    session = _signature_session()
    canvas = FakeSignatureCanvas([], broken=True)
    diagnostics = FakeDiagnostics()

    with pytest.raises(RuntimeError):
        asyncio.run(
            session._draw_checked(
                canvas,
                {"x": 0, "y": 0, "width": 300, "height": 150},
                [FittedPoint(x=10, y=10), FittedPoint(x=290, y=140)],
                diagnostics,
            )
        )

    assert diagnostics.saved is True


def test_navigateur_ferme_pendant_la_signature(monkeypatch):
    session = _signature_session()

    async def closed(points):
        raise RuntimeError(
            "Locator.evaluate: Target page, context or browser has been closed"
        )

    monkeypatch.setattr(session, "_sign", closed)

    with pytest.raises(SignError) as error:
        asyncio.run(session.sign([]))

    assert "navigateur ferme" in str(error.value)
