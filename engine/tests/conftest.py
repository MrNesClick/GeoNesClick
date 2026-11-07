"""Garde-fous communs à tous les tests."""

import pytest

from geonesclick import plonkit


@pytest.fixture(autouse=True)
def no_network_to_plonkit(monkeypatch):
    """Aucun test ne doit contacter plonkit.net : un test qui l'oublierait échoue au lieu de collecter."""

    def blocked(url, timeout=20.0):
        raise AssertionError(f"accès réseau interdit pendant les tests : {url}")

    monkeypatch.setattr(plonkit, "_get", blocked)
