"""Garde-fous communs à tous les tests."""

import pytest

from geonesclick import places, plonkit, vision


@pytest.fixture(autouse=True)
def no_network_to_plonkit(monkeypatch):
    """Aucun test ne doit contacter plonkit.net : un test qui l'oublierait échoue au lieu de collecter."""

    def blocked(url, timeout=20.0):
        raise AssertionError(f"accès réseau interdit pendant les tests : {url}")

    monkeypatch.setattr(plonkit, "_get", blocked)


@pytest.fixture(autouse=True)
def no_model_download(monkeypatch):
    """Aucun test ne télécharge de poids (PLONK…) : les tests fournissent leur propre petit réseau."""
    import huggingface_hub

    def blocked(repo_id, *_args, **_kwargs):
        raise AssertionError(f"téléchargement de modèle interdit pendant les tests : {repo_id}")

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", blocked)


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    """Les tests ne voient jamais la clé NVIDIA de .env : aucun appel réel à l'API, même par oubli."""
    monkeypatch.setattr(vision, "read_secret", lambda _name: None)


@pytest.fixture(autouse=True)
def no_geonames_download(monkeypatch):
    """Aucun test ne télécharge le répertoire GeoNames : les tests fournissent leur petite archive."""

    def blocked(url):
        raise AssertionError(f"téléchargement interdit pendant les tests : {url}")

    monkeypatch.setattr(places, "_fetch", blocked)


@pytest.fixture(autouse=True)
def no_real_key_file(monkeypatch, tmp_path_factory):
    """Les tests ne lisent ni n'écrivent jamais ta vraie clé (~/.config/geonesclick/nvapi.key)."""
    from geonesclick import paths

    monkeypatch.setattr(paths, "CONFIG_DIR", tmp_path_factory.mktemp("config"))
    monkeypatch.delenv("NVAPI", raising=False)
