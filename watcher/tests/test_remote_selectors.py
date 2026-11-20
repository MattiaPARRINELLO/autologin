"""Tests des selecteurs distants."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from checkmate_watcher import remote_selectors
from checkmate_watcher.config import (
    DEFAULT_SELECTORS,
    CesarConfig,
    Config,
    ConfigError,
    NotificationConfig,
    Selectors,
    SignatureConfig,
    WatcherConfig,
)


def config() -> Config:
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
    )


def payload(**selectors) -> dict:
    return {"updated": "2026-11-20", "selectors": selectors or {"confirmation": [".x"]}}


def test_parse_valid_partial_override():
    remote = remote_selectors.parse(
        {
            "updated": "2026-11-20",
            "min_version": "0.7.0",
            "selectors": {"confirmation": [".nouveau", ".autre"]},
        }
    )
    assert remote.selectors == {"confirmation": (".nouveau", ".autre")}
    assert remote.min_version == "0.7.0"
    assert remote.updated == "2026-11-20"
    assert remote


def test_parse_rejects_unknown_group():
    with pytest.raises(ConfigError):
        remote_selectors.parse(payload(inexistant=[".x"]))


@pytest.mark.parametrize(
    "values",
    [
        [],
        [""],
        ["a" * 201],
        ["javascript:alert(1)"],
        ["div { background: url(https://x) }"],
        ["<script>"],
        ["a\nb"],
        ["ligne\tbizarre"],
    ],
)
def test_parse_rejects_bad_selector(values):
    with pytest.raises(ConfigError):
        remote_selectors.parse(payload(confirmation=values))


def test_parse_rejects_bad_shape():
    with pytest.raises(ConfigError):
        remote_selectors.parse([])
    with pytest.raises(ConfigError):
        remote_selectors.parse({"selectors": []})
    with pytest.raises(ConfigError):
        remote_selectors.parse(
            {"selectors": {"confirmation": [".x"]}, "min_version": "x"}
        )
    with pytest.raises(ConfigError):
        remote_selectors.parse({"selectors": {"confirmation": [".x"]}, "updated": 3})


def test_parse_accepts_empty_overrides():
    remote = remote_selectors.parse({"updated": "2026-11-20", "selectors": {}})
    assert not remote


def test_apply_merges_over_defaults_without_touching_others():
    remote = remote_selectors.parse(payload(confirmation=[".nouveau"]))
    merged = remote_selectors.apply(config(), remote)
    assert merged.selectors.confirmation == (".nouveau",)
    assert merged.selectors.attendance_button == DEFAULT_SELECTORS["attendance_button"]
    assert config().selectors.confirmation == DEFAULT_SELECTORS["confirmation"]


def test_apply_without_remote_keeps_config():
    base = config()
    assert remote_selectors.apply(base, remote_selectors.RemoteSelectors()) is base


def test_load_uses_cache_when_network_fails(monkeypatch, tmp_path: Path):
    cache = tmp_path / "selectors-cache.json"
    cache.write_text(json.dumps(payload(confirmation=[".cache"])), encoding="utf-8")

    def boom(url, timeout):
        raise OSError("hors ligne")

    monkeypatch.setattr(remote_selectors, "_read", boom)
    remote = remote_selectors.load(path=cache)
    assert remote.selectors == {"confirmation": (".cache",)}


def test_load_writes_cache_on_success(monkeypatch, tmp_path: Path):
    cache = tmp_path / "selectors-cache.json"
    body = json.dumps(payload(confirmation=[".reseau"])).encode("utf-8")
    monkeypatch.setattr(remote_selectors, "_read", lambda url, timeout: body)

    remote = remote_selectors.load(path=cache)
    assert remote.selectors == {"confirmation": (".reseau",)}
    assert json.loads(cache.read_text(encoding="utf-8"))["selectors"] == {
        "confirmation": [".reseau"]
    }


def test_load_ignores_invalid_cache(monkeypatch, tmp_path: Path):
    cache = tmp_path / "selectors-cache.json"
    cache.write_text("{pas du json", encoding="utf-8")

    def boom(url, timeout):
        raise OSError("hors ligne")

    monkeypatch.setattr(remote_selectors, "_read", boom)
    assert not remote_selectors.load(path=cache)


def test_load_ignores_invalid_remote_and_falls_back(monkeypatch, tmp_path: Path):
    cache = tmp_path / "selectors-cache.json"
    monkeypatch.setattr(
        remote_selectors,
        "_read",
        lambda url, timeout: b'{"selectors": {"confirmation": ["javascript:1"]}}',
    )
    assert not remote_selectors.load(path=cache)


def test_requires_update():
    remote = remote_selectors.parse(
        {"selectors": {"confirmation": [".x"]}, "min_version": "0.7.0"}
    )
    assert remote_selectors.requires_update(remote, "0.6.2")
    assert not remote_selectors.requires_update(remote, "0.7.0")
    assert not remote_selectors.requires_update(remote, "0.8.0")
