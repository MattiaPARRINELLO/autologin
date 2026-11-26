from __future__ import annotations

import pytest

from checkmate_watcher.release_notes import (
    CELEBRATED_VERSION_KEY,
    LAST_VERSION_KEY,
    dismiss_release_celebration,
    is_significant_update,
    prepare_release_celebration,
    release_note,
)
from checkmate_watcher.state import StateStore


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        ("0.6.9", "0.7.0", True),
        ("0.7.0", "0.8.0", True),
        ("0.9.0", "1.0.0", True),
        ("0.7.0", "0.7.1", False),
        ("0.6.9", "0.7.0-beta.1", False),
        ("0.7.0-beta.4", "0.7.0-beta.5", False),
        ("0.7.0-beta.4", "0.7.0", True),
        ("0.7.0", "0.6.9", False),
        ("inconnue", "0.7.0", False),
    ],
)
def test_seules_les_releases_stables_importantes_ouvrent_le_popup(
    previous, current, expected
):
    assert is_significant_update(previous, current) is expected


def test_le_resume_0_7_0_contient_les_gains_mesures():
    note = release_note("0.7.0")

    assert note is not None
    assert note["version"] == "0.7.0"
    assert "2,3×" in note["teaser"]
    assert [item["value"] for item in note["metrics"]] == ["2,3×", "15×", "0"]
    assert len(note["features"]) == 6
    assert note["features"][-1]["title"] == "Des messages de l'équipe"
    assert note["performance"]["items"][0]["before"] == 657
    assert note["performance"]["items"][0]["after"] == 284


def test_premiere_execution_sans_popup(tmp_path):
    state = StateStore(tmp_path / "state.json")

    note = prepare_release_celebration(state, "0.7.0")

    assert note is None
    assert state.get_meta(LAST_VERSION_KEY) == "0.7.0"


def test_mise_a_jour_importante_avec_resume(tmp_path):
    state = StateStore(tmp_path / "state.json")
    state.set_meta(LAST_VERSION_KEY, "0.6.9")

    note = prepare_release_celebration(state, "0.7.0")

    assert note is not None
    assert note["version"] == "0.7.0"
    assert state.get_meta(LAST_VERSION_KEY) == "0.7.0"


def test_beta_sans_popup(tmp_path):
    state = StateStore(tmp_path / "state.json")
    state.set_meta(LAST_VERSION_KEY, "0.6.9")

    note = prepare_release_celebration(state, "0.7.0-beta.1")

    assert note is None
    assert state.get_meta(LAST_VERSION_KEY) == "0.7.0-beta.1"


def test_passage_d_une_beta_vers_sa_version_stable(tmp_path):
    state = StateStore(tmp_path / "state.json")
    state.set_meta(LAST_VERSION_KEY, "0.7.0-beta.4")

    note = prepare_release_celebration(state, "0.7.0")

    assert note is not None
    assert note["version"] == "0.7.0"


def test_correctif_sans_popup(tmp_path):
    state = StateStore(tmp_path / "state.json")
    state.set_meta(LAST_VERSION_KEY, "0.7.0")

    note = prepare_release_celebration(state, "0.7.1")

    assert note is None
    assert state.get_meta(LAST_VERSION_KEY) == "0.7.1"


def test_popup_deja_ferme(tmp_path):
    state = StateStore(tmp_path / "state.json")
    state.set_meta(LAST_VERSION_KEY, "0.6.9")
    state.set_meta(CELEBRATED_VERSION_KEY, "0.7.0")

    note = prepare_release_celebration(state, "0.7.0")

    assert note is None


def test_fermeture_persistee(tmp_path):
    state = StateStore(tmp_path / "state.json")

    dismiss_release_celebration(state, "0.7.0")

    assert state.get_meta(CELEBRATED_VERSION_KEY) == "0.7.0"


def test_version_sans_resume(tmp_path):
    state = StateStore(tmp_path / "state.json")
    state.set_meta(LAST_VERSION_KEY, "0.6.9")

    note = prepare_release_celebration(state, "1.0.0")

    assert note is None
