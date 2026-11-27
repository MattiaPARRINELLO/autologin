"""Rejoue les fixtures de parite Rust avec les implementations Python.

Les fichiers de `rust/fixtures/parity/` sont la reference partagee entre les
tests Python et les tests Rust. Ce test garantit qu'ils decrivent le
comportement reel de `checkmate_watcher` et qu'ils ne derivent pas.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from checkmate_watcher.config import ConfigError, load_config
from checkmate_watcher.release_notes import (
    CELEBRATED_VERSION_KEY,
    LAST_VERSION_KEY,
    is_significant_update,
    prepare_release_celebration,
    release_note,
)
from checkmate_watcher.schedule import (
    Schedule,
    ScheduleError,
    parse_days,
    parse_window,
    parse_windows,
)
from checkmate_watcher.state import StateStore
from checkmate_watcher.updates import (
    Asset,
    Release,
    check_for_update,
    parse_checksums,
    parse_release,
    parse_version,
    platform_asset,
    select_latest,
    update_policy,
)

FIXTURES = Path(__file__).resolve().parents[2] / "rust" / "fixtures" / "parity"
DOMAINS = ("config", "schedule", "release_notes", "updates")


def _load(domain: str) -> dict:
    return json.loads(
        (FIXTURES / f"{domain}.json").read_text(encoding="utf-8")
    )


def _cases():
    for domain in DOMAINS:
        payload = _load(domain)
        for case in payload["cases"]:
            yield domain, payload.get("defaults", {}), case


CASES = list(_cases())


def _jsonable(value):
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if hasattr(value, "start") and hasattr(value, "end"):
        return str(value)
    return value


def _resolve(value, path: str):
    current = value
    for part in path.split("."):
        current = (
            current[int(part)] if part.isdigit() else getattr(current, part)
        )
    return current


def _config(case, monkeypatch, tmp_path):
    for name in case.get("unset_env", []):
        monkeypatch.delenv(name, raising=False)
    for name, value in case.get("env", {}).items():
        monkeypatch.setenv(name, value)
    path = tmp_path / "config.toml"
    if case.get("file", True):
        path.write_text(case["toml"], encoding="utf-8")
    config = load_config(path)
    expected = case["expect"].get("values", {})
    return {
        "values": {key: _jsonable(_resolve(config, key)) for key in expected}
    }


def _schedule(case, defaults, monkeypatch, tmp_path):
    data = {**defaults, **case.get("input", {})}
    op = case["op"]
    if op == "parse_window":
        window = parse_window(data["value"])
        return {
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "text": str(window),
        }
    if op == "parse_windows":
        parse_windows(data["values"])
        return {}
    if op == "parse_days":
        return {"days": list(parse_days(data["values"]))}
    plan = Schedule(
        enabled=data.get("enabled", True),
        days=parse_days(data["days"]),
        windows=parse_windows(data["windows"]),
    )
    now = datetime.fromisoformat(data["now"])
    if op == "active_window":
        window = plan.active_window(now)
        return {"window": None if window is None else str(window)}
    if op == "window_key":
        return {"key": plan.window_key(now)}
    if op == "next_start":
        return {"at": plan.next_start(now).isoformat(timespec="seconds")}
    if op == "seconds_until_next":
        return {"seconds": plan.seconds_until_next(now)}
    raise AssertionError(f"operation inconnue : {op}")


def _release_notes(case, defaults, monkeypatch, tmp_path):
    op = case["op"]
    data = case["input"]
    if op == "significant":
        return {
            "significant": is_significant_update(
                data["previous"], data["current"]
            )
        }
    if op == "note":
        note = release_note(data["version"])
        if note is None:
            return {"note": None}
        return {
            "version": note["version"],
            "metrics": [item["value"] for item in note["metrics"]],
            "features": len(note["features"]),
            "last_feature": note["features"][-1]["title"],
            "performance_before": note["performance"]["items"][0]["before"],
            "performance_after": note["performance"]["items"][0]["after"],
        }
    if op == "celebration":
        state = StateStore(tmp_path / "state.json")
        if data.get("last_version"):
            state.set_meta(LAST_VERSION_KEY, data["last_version"])
        if data.get("celebrated_version"):
            state.set_meta(CELEBRATED_VERSION_KEY, data["celebrated_version"])
        note = prepare_release_celebration(state, data["current"])
        return {
            "note_version": None if note is None else note["version"],
            "last_version": state.get_meta(LAST_VERSION_KEY),
        }
    raise AssertionError(f"operation inconnue : {op}")


def _release(spec: dict) -> Release:
    version = parse_version(spec["tag"])
    assert version is not None
    return Release(
        tag=spec["tag"],
        version=version,
        url="https://example.com/release",
        name=spec["tag"],
        prerelease=spec.get("prerelease", False),
        assets=tuple(
            Asset(asset["name"], asset.get("browser_download_url", "u"))
            for asset in spec.get("assets", [])
        ),
        migration_reason=spec.get("migration"),
        required_reason=spec.get("required"),
        markers_declared=spec.get("markers_declared", False),
    )


def _updates(case, defaults, monkeypatch, tmp_path):
    op = case["op"]
    data = case["input"]
    if op == "parse_version":
        version = parse_version(data["tag"])
        return {"version": None if version is None else str(version)}
    if op == "parse_release":
        parsed = parse_release(data["payload"])
        if parsed is None:
            return {"release": None}
        setup = parsed.find_asset("CheckMate-Setup-", ".exe")
        return {
            "release": parsed.tag,
            "markers_declared": parsed.markers_declared,
            "migration_reason": parsed.migration_reason,
            "required_reason": parsed.required_reason,
            "teaser": parsed.teaser,
            "downloads": parsed.downloads,
            "assets": len(parsed.assets),
            "setup_size": None if setup is None else setup.size,
        }
    releases = [_release(spec) for spec in data.get("releases", [])]
    if op == "select_latest":
        latest = select_latest(releases, channel=data["channel"])
        return {"tag": None if latest is None else latest.tag}
    if op == "check_for_update":
        update = check_for_update(
            data["current"],
            channel=data.get("channel", "stable"),
            releases=releases,
        )
        return {"tag": None if update is None else update.tag}
    if op == "platform_asset":
        version = parse_version(data["tag"])
        assert version is not None
        release = Release(
            tag=data["tag"],
            version=version,
            url="https://example.com/release",
            name=data["tag"],
            prerelease=False,
            assets=tuple(
                Asset(asset["name"], asset.get("browser_download_url", "u"))
                for asset in data["assets"]
            ),
        )
        asset = platform_asset(release, data["platform"])
        return {"name": None if asset is None else asset.name}
    if op == "parse_checksums":
        return {"map": parse_checksums(data["text"])}
    if op == "update_policy":
        policy = update_policy(
            data["current"],
            channel=data.get("channel", "stable"),
            releases=releases,
        )
        return {
            "available": policy.available,
            "migration_tag": getattr(policy.migration, "tag", None),
            "required_tag": getattr(policy.required, "tag", None),
            "install_target_tag": getattr(policy.install_target, "tag", None),
        }
    raise AssertionError(f"operation inconnue : {op}")


HANDLERS = {
    "config": lambda case, defaults, monkeypatch, tmp_path: _config(
        case, monkeypatch, tmp_path
    ),
    "schedule": _schedule,
    "release_notes": _release_notes,
    "updates": _updates,
}


@pytest.mark.parametrize(
    ("domain", "defaults", "case"),
    CASES,
    ids=[f"{domain}:{case['name']}" for domain, _, case in CASES],
)
def test_fixture_de_parite(domain, defaults, case, monkeypatch, tmp_path):
    try:
        actual = HANDLERS[domain](case, defaults, monkeypatch, tmp_path)
    except (ConfigError, ScheduleError) as error:
        actual = {"error": type(error).__name__, "message": str(error)}
    expected = case["expect"]
    if "error" in expected:
        assert actual.get("error") == expected["error"], actual
        if "match" in expected:
            assert expected["match"] in actual.get("message", ""), actual
        return
    for key, value in expected.items():
        assert actual.get(key) == value, f"{key} : {actual.get(key)!r}"


def test_les_quatre_fixtures_existent():
    assert {path.stem for path in FIXTURES.glob("*.json")} == set(DOMAINS)


def test_chaque_cas_a_un_nom_unique():
    for domain in DOMAINS:
        names = [case["name"] for case in _load(domain)["cases"]]
        assert len(names) == len(set(names)), domain
