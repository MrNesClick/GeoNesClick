"""Garde-fous communs à tous les tests."""

import pytest

from geonesclick import plonkit, vision


@pytest.fixture(autouse=True)
def no_network_to_plonkit(monkeypatch):
    """Aucun test ne doit contacter plonkit.net : un test qui l'oublierait échoue au lieu de collecter."""

    def blocked(url, timeout=20.0):
        raise AssertionError(f"accès réseau interdit pendant les tests : {url}")

    monkeypatch.setattr(plonkit, "_get", blocked)


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    """Les tests ne voient jamais la clé NVIDIA de .env : aucun appel réel à l'API, même par oubli."""
    monkeypatch.setattr(vision, "read_secret", lambda _name: None)
