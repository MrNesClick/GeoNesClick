"""Shared paths, without heavy dependencies (imported by the keyboard shortcut client).

App name: GeoNesClick, after the author's handle MrNesClick.
"""

import logging
import os
import shutil
from pathlib import Path

APP = "geonesclick"


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


CONFIG_DIR = config_home() / APP  # config.toml, my-metas.toml, screencast.token
DATA_DIR = data_home() / APP  # places/ (GeoNames), plonkit/ (guides and translations)
SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / f"{APP}.sock"


def hf_hub_cache() -> Path:
    """Hugging Face model cache (StreetCLIP, PLONK), without importing the library: the same variables, in the same
    order, as huggingface_hub/constants.py (HF_HUB_CACHE, HUGGINGFACE_HUB_CACHE, HF_HOME, XDG_CACHE_HOME)."""
    def expand(value: str) -> str:
        return os.path.expandvars(os.path.expanduser(value))

    cache_home = os.environ.get("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache"))
    hf_home = expand(os.environ.get("HF_HOME", os.path.join(cache_home, "huggingface")))
    legacy = os.environ.get("HUGGINGFACE_HUB_CACHE", os.path.join(hf_home, "hub"))
    return Path(expand(os.environ.get("HF_HUB_CACHE", legacy)))


class _TokenNagFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "unauthenticated requests" not in record.getMessage()  # not "HF_TOKEN": keeps a bad-token warning


def quiet_token_nag() -> None:
    """Hides the Hub's "unauthenticated requests, set a HF_TOKEN" warning: the models are public, nothing to do.

    The Hub sends it in an X-HF-Warning header and huggingface_hub logs it; its other warnings still show.
    """
    log = logging.getLogger("huggingface_hub.utils._http")
    if not any(isinstance(f, _TokenNagFilter) for f in log.filters):
        log.addFilter(_TokenNagFilter())


def migrate_repo_data(project_root: Path) -> list[str]:
    """Captures and the test set move out of the code folder (read-only in an AppImage) to DATA_DIR.

    The captures are MOVED (ignored by git); the test set is COPIED, so that
    the copy tracked by git in the repository (and the spikes/ benches that read it) stays intact. Only once:
    nothing is done if the destination already exists.
    """
    done = []
    target = data_home() / APP
    captures, dataset = project_root / "engine" / "captures", project_root / "engine" / "dataset"
    if captures.is_dir() and not captures.is_symlink() and not (target / "captures").exists():
        target.mkdir(parents=True, exist_ok=True)
        shutil.move(str(captures), target / "captures")
        done.append(f"{captures} → {target / 'captures'} (moved)")
    if (dataset / "labels.toml").is_file() and not dataset.is_symlink() and not (target / "dataset").exists():
        shutil.copytree(dataset, target / "dataset", symlinks=False)
        done.append(f"{dataset} → {target / 'dataset'} (copied; the repository's copy stays)")
    return done
