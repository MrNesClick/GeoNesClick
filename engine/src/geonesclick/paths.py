"""Shared paths, without heavy dependencies (imported by the keyboard shortcut client).

App name: GeoNesClick (decided with the user on 2026-11-07, after their handle MrNesClick).
"""

import os
import shutil
from pathlib import Path

APP = "geonesclick"


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


CONFIG_DIR = config_home() / APP  # config.toml, mes-metas.toml, screencast.token
DATA_DIR = data_home() / APP  # places/ (GeoNames), plonkit/ (guides and translations)
SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / f"{APP}.sock"


def hf_hub_cache() -> Path:
    """Hugging Face model cache (StreetCLIP, PLONK), without importing the library."""
    hf_home = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")
    return Path(os.environ.get("HF_HUB_CACHE") or hf_home / "hub")


def migrate_repo_data(project_root: Path) -> list[str]:
    """Captures and the test set move out of the code folder (read-only in an AppImage) to DATA_DIR.

    Decided on 2026-11-07: the captures are MOVED (ignored by git); the test set is COPIED, so that
    the copy tracked by git in the repository (and the spikes/ benches that read it) stays intact. Only once:
    nothing is done if the destination already exists.
    """
    done = []
    target = data_home() / APP
    captures, dataset = project_root / "engine" / "captures", project_root / "engine" / "dataset"
    if captures.is_dir() and not captures.is_symlink() and not (target / "captures").exists():
        target.mkdir(parents=True, exist_ok=True)
        shutil.move(str(captures), target / "captures")
        done.append(f"{captures} → {target / 'captures'} (déplacées)")
    if (dataset / "labels.toml").is_file() and not dataset.is_symlink() and not (target / "dataset").exists():
        shutil.copytree(dataset, target / "dataset", symlinks=False)
        done.append(f"{dataset} → {target / 'dataset'} (copié ; l'exemplaire du dépôt reste)")
    return done
