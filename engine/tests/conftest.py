"""Safeguards shared by all the tests."""

import atexit
import os
import shutil
import tempfile

# BEFORE any import of the app: its folders (config, data, socket, models) point to a temporary
# folder. Seen on 2026-11-07: without it, the tests built fake GeoNames villages on top of the
# real ones (~/.local/share/geonesclick/places), and their folder blocked the migration from the old name.
_SANDBOX = tempfile.mkdtemp(prefix="geonesclick-tests-")
atexit.register(shutil.rmtree, _SANDBOX, ignore_errors=True)  # nothing piles up in /tmp (disk almost full)
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
    """No test may contact plonkit.net: a test that forgot it fails instead of collecting."""

    def blocked(url, timeout=20.0):
        raise AssertionError(f"network access forbidden during the tests: {url}")

    monkeypatch.setattr(plonkit, "_get", blocked)


@pytest.fixture(autouse=True)
def no_model_download(monkeypatch):
    """No test downloads weights (PLONK…): the tests provide their own small network."""
    import huggingface_hub

    def blocked(repo_id, *_args, **_kwargs):
        raise AssertionError(f"model download forbidden during the tests: {repo_id}")

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", blocked)


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    """The tests never see the NVIDIA key from .env: no real API call, even by mistake."""
    monkeypatch.setattr(vision, "read_secret", lambda _name: None)


@pytest.fixture(autouse=True)
def no_geonames_download(monkeypatch):
    """No test downloads the GeoNames directory: the tests provide their own small archive."""

    def blocked(url):
        raise AssertionError(f"download forbidden during the tests: {url}")

    monkeypatch.setattr(places, "_fetch", blocked)


@pytest.fixture(autouse=True)
def no_real_key_file(monkeypatch, tmp_path_factory):
    """The tests never read or write your real key (~/.config/geonesclick/nvapi.key)."""
    from geonesclick import paths

    monkeypatch.setattr(paths, "CONFIG_DIR", tmp_path_factory.mktemp("config"))
    monkeypatch.delenv("NVAPI", raising=False)


@pytest.fixture(autouse=True)
def no_real_shortcuts(monkeypatch):
    """No test reads or modifies your GNOME shortcuts."""
    from geonesclick import storage

    def blocked(args):
        raise AssertionError(f"gsettings forbidden during the tests: {args}")

    monkeypatch.setattr(storage, "_gsettings", blocked)


@pytest.fixture(autouse=True)
def english_after_each_test():
    """A test that starts an engine in French must not leave the next ones in French (the language is global)."""
    yield
    from geonesclick import i18n

    i18n.set_language("en")
