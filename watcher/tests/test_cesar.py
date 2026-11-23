from __future__ import annotations

import asyncio

import pytest

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


class FakePage:
    """Page minimale : seule l'attente et la duree reelle importent."""

    def __init__(self, wait_seconds: float = 0.02) -> None:
        self.wait_seconds = wait_seconds
        self.waits: list[int] = []

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)
        await asyncio.sleep(self.wait_seconds)


def make_session(page: FakePage) -> CesarSession:
    config = Config(
        cesar=CesarConfig(
            base_url="https://cesar.example.fr",
            username="eleve",
            password="secret",
        ),
        watcher=WatcherConfig(),
        signature=SignatureConfig(),
        notifications=NotificationConfig(),
        updates=UpdatesConfig(),
        selectors=Selectors.from_dict({}),
    )
    session = CesarSession(config)
    session.page = page
    return session


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
