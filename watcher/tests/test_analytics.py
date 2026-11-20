"""Tests des compteurs d'usage anonymes."""

from __future__ import annotations

from pathlib import Path

import pytest

from checkmate_watcher import analytics
from checkmate_watcher.config import (
    AnalyticsConfig,
    CesarConfig,
    Config,
    NotificationConfig,
    Selectors,
    SignatureConfig,
    WatcherConfig,
)


class _State:
    def __init__(self) -> None:
        self.meta: dict[str, str] = {}

    def get_meta(self, key: str) -> str | None:
        return self.meta.get(key)

    def set_meta(self, key: str, value: str) -> None:
        self.meta[key] = value


@pytest.fixture
def sent(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(analytics, "install_id", lambda path=None: "abc123")
    monkeypatch.setattr(analytics, "_send", lambda config, event: events.append(event))
    monkeypatch.delenv(analytics.DISABLE_ENV, raising=False)
    return events


def test_install_id_is_stable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(analytics, "_install_id", None)
    first = analytics.install_id(tmp_path / "install-id")
    second = analytics.install_id(tmp_path / "install-id")
    assert first == second
    assert len(first) == 32
    assert (tmp_path / "install-id").read_text(encoding="utf-8").strip() == first
    monkeypatch.setattr(analytics, "_install_id", None)


def test_startup_sends_install_once(sent):
    config = analytics_config()
    state = _State()

    analytics.record_startup(config, state)
    analytics.record_startup(config, state)
    analytics.record_startup(config, state)

    assert sent == ["install"]


def test_disabled_by_environment(sent, monkeypatch):
    monkeypatch.setenv(analytics.DISABLE_ENV, "0")
    analytics.record_startup(analytics_config(), _State())
    analytics.record(analytics_config(), "signature")
    assert sent == []


def test_disabled_by_config(sent):
    analytics.record_startup(analytics_config(enabled=False), _State())
    analytics.record(analytics_config(enabled=False), "signature")
    assert sent == []


def test_payload_has_no_identity(monkeypatch, tmp_path: Path):
    captured: list[dict] = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout=0):
        captured.append(
            {
                "url": request.full_url,
                "body": request.data,
                "headers": dict(request.header_items()),
            }
        )
        return _Response()

    monkeypatch.setattr(analytics.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        analytics,
        "install_id",
        lambda path=None: analytics.secrets.token_hex(16),
    )

    analytics._post(analytics.DEFAULT_ENDPOINT, {"install": "abc", "event": "install"})

    assert captured[0]["url"] == analytics.DEFAULT_ENDPOINT
    assert b"install" in captured[0]["body"]
    assert analytics.INGEST_HEADER.lower() in {
        name.lower() for name in captured[0]["headers"]
    }


def analytics_config(enabled: bool = True):
    return Config(
        cesar=CesarConfig(
            base_url="https://cesar.example.fr",
            username="eleve",
            password="secret",
        ),
        watcher=WatcherConfig(),
        signature=SignatureConfig(),
        notifications=NotificationConfig(),
        selectors=Selectors.from_dict({}),
        analytics=AnalyticsConfig(enabled=enabled),
    )
