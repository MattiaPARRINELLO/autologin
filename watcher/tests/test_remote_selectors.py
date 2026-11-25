from __future__ import annotations

import json
from dataclasses import replace

import pytest

from checkmate_watcher import remote_selectors
from checkmate_watcher.config import default_config


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size=-1):
        return self.payload[:size] if size >= 0 else self.payload


def payload(selector="button.remote") -> dict:
    return {
        "min_version": "0.6.0",
        "selectors": {"attendance_button": [selector]},
    }


def test_charge_les_selecteurs_distants_et_ecrit_le_cache(
    tmp_path, monkeypatch
):
    cache = tmp_path / "selectors.json"
    monkeypatch.setattr(
        remote_selectors.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(payload()),
    )

    selectors = remote_selectors.load_remote_selectors(
        "0.7.0-beta.4", cache, url="https://example.test/selectors.json"
    )

    assert selectors == {"attendance_button": ["button.remote"]}
    assert json.loads(cache.read_text(encoding="utf-8")) == payload()


def test_utilise_le_cache_si_le_reseau_est_indisponible(tmp_path, monkeypatch):
    cache = tmp_path / "selectors.json"
    cache.write_text(json.dumps(payload("button.cached")), encoding="utf-8")

    def offline(request, timeout):
        raise OSError("hors ligne")

    monkeypatch.setattr(remote_selectors.urllib.request, "urlopen", offline)

    selectors = remote_selectors.load_remote_selectors(
        "0.7.0", cache, url="https://example.test/selectors.json"
    )

    assert selectors == {"attendance_button": ["button.cached"]}


def test_sans_reseau_ni_cache_conserve_les_defauts(tmp_path, monkeypatch):
    def offline(request, timeout):
        raise OSError("hors ligne")

    monkeypatch.setattr(remote_selectors.urllib.request, "urlopen", offline)

    selectors = remote_selectors.load_remote_selectors(
        "0.7.0",
        tmp_path / "absent.json",
        url="https://example.test/selectors.json",
    )

    assert selectors == {}


def test_refuse_une_version_minimale_trop_recente(tmp_path, monkeypatch):
    data = payload()
    data["min_version"] = "9.0.0"
    monkeypatch.setattr(
        remote_selectors.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(data),
    )

    selectors = remote_selectors.load_remote_selectors(
        "0.7.0",
        tmp_path / "selectors.json",
        url="https://example.test/selectors.json",
    )

    assert selectors == {}


@pytest.mark.parametrize(
    "selector",
    ["javascript:alert(1)", "https://example.test/x", "<script>x</script>"],
)
def test_refuse_les_selecteurs_executables(selector, tmp_path, monkeypatch):
    monkeypatch.setattr(
        remote_selectors.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(payload(selector)),
    )

    selectors = remote_selectors.load_remote_selectors(
        "0.7.0",
        tmp_path / "selectors.json",
        url="https://example.test/selectors.json",
    )

    assert selectors == {}


def test_refuse_une_url_non_https():
    with pytest.raises(ValueError, match="HTTPS"):
        remote_selectors._fetch_payload("http://example.test/x", timeout=1)


def test_les_selecteurs_distants_remplacent_les_valeurs_locales(
    tmp_path, monkeypatch
):
    config = default_config()
    config = replace(
        config,
        selectors=replace(
            config.selectors, attendance_button=("button.local",)
        ),
    )
    monkeypatch.delenv("CHECKMATE_REMOTE_SELECTORS", raising=False)
    monkeypatch.setattr(
        remote_selectors,
        "load_remote_selectors",
        lambda version: {"attendance_button": ["button.remote"]},
    )

    updated = remote_selectors.with_remote_selectors(config)

    assert updated.selectors.attendance_button == ("button.remote",)
    assert config.selectors.attendance_button == ("button.local",)


def test_desactivation_explicite_des_selecteurs_distants(monkeypatch):
    config = default_config()
    monkeypatch.setenv("CHECKMATE_REMOTE_SELECTORS", "0")

    updated = remote_selectors.with_remote_selectors(config)

    assert updated is config
