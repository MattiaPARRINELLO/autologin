"""Reglages communs aux tests : aucun envoi de statistiques."""

import pytest


# Fixture autouse : desactive les statistiques pour toute la suite de tests.
@pytest.fixture(autouse=True)
def _no_analytics(monkeypatch):
    monkeypatch.setenv("CHECKMATE_ANALYTICS", "0")
