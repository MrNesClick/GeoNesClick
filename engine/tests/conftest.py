"""Garde-fous communs à tous les tests."""

import atexit
import os
import shutil
import tempfile

# AVANT tout import de l'application : ses dossiers (config, données, socket, modèles) pointent vers un dossier
# temporaire. Constaté le 2026-11-07 : sans cela, les tests construisaient de faux villages GeoNames par-dessus les
# vrais (~/.local/share/geonesclick/places), et leur dossier empêchait la migration de l'ancien nom.
_SANDBOX = tempfile.mkdtemp(prefix="geonesclick-tests-")
atexit.register(shutil.rmtree, _SANDBOX, ignore_errors=True)  # rien ne s'accumule dans /tmp (disque presque plein)
for _var, _sub in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_RUNTIME_DIR", "run"),
                   ("HF_HOME", "hf")):
    os.environ[_var] = os.path.join(_SANDBOX, _sub)
    os.makedirs(os.environ[_var], exist_ok=True)
os.environ.pop("HF_HUB_CACHE", None)

import pytest  # noqa: E402

from geonesclick import paths, places, plonkit, vision  # noqa: E402

assert str(paths.DATA_DIR).startswith(_SANDBOX) and str(paths.CONFIG_DIR).startswith(_SANDBOX)


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


@pytest.fixture(autouse=True)
def no_real_shortcuts(monkeypatch):
    """Aucun test ne lit ni ne modifie tes raccourcis GNOME."""
    from geonesclick import storage

    def blocked(args):
        raise AssertionError(f"gsettings interdit pendant les tests : {args}")

    monkeypatch.setattr(storage, "_gsettings", blocked)
