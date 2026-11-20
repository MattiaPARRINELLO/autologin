"""Reglages communs aux tests : aucun envoi de statistiques."""

import pytest


@pytest.fixture(autouse=True)
def _no_analytics(monkeypatch):
    monkeypatch.setenv("CHECKMATE_ANALYTICS", "0")
    monkeypatch.setenv("CHECKMATE_REMOTE_SELECTORS", "0")
