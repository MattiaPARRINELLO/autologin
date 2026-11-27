"""Reglages communs aux tests : aucun envoi externe."""

import pytest

from checkmate_watcher import native_ui


# Fixture autouse : desactive les statistiques et les binaires natifs.
# Les tests unitaires verifient les replis Python ; ils ne doivent pas lancer
# un `checkmate-ui` eventuellement compile dans rust/target.
@pytest.fixture(autouse=True)
def _no_analytics(monkeypatch, tmp_path):
    monkeypatch.setenv("CHECKMATE_ANALYTICS", "0")
    monkeypatch.setenv("CHECKMATE_REMOTE_SELECTORS", "0")
    monkeypatch.delenv(native_ui.BINARY_ENV, raising=False)
    monkeypatch.setattr(
        native_ui, "_repository_root", lambda: tmp_path / "repo"
    )
    monkeypatch.setattr(native_ui.shutil, "which", lambda name: None)
