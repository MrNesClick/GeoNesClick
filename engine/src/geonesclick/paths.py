"""Chemins partagés, sans dépendance lourde (importé par le client du raccourci clavier).

Nom de l'application : GeoNesClick (décidé avec l'utilisateur le 2026-11-07, d'après son pseudo MrNesClick ;
« GeoNesClick » était trop proche de la marque GeoGuessr). Les dossiers de l'ancien nom sont DÉPLACÉS une fois
vers les nouveaux au démarrage (migrate_legacy), jamais supprimés : réglages, metas, index des lieux, et des heures
de traductions Plonk It.
"""

import os
import shutil
from pathlib import Path

APP = "geonesclick"
LEGACY = "geonesclick"  # ancien nom des dossiers


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


CONFIG_DIR = config_home() / APP  # config.toml, mes-metas.toml, screencast.token
DATA_DIR = data_home() / APP  # places/ (GeoNames), plonkit/ (guides et traductions)
SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / f"{APP}.sock"


def hf_hub_cache() -> Path:
    """Cache des modèles Hugging Face (StreetCLIP, PLONK), sans importer la bibliothèque."""
    hf_home = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")
    return Path(os.environ.get("HF_HUB_CACHE") or hf_home / "hub")


def migrate_legacy() -> list[str]:
    """Déplace les dossiers de l'ancien nom vers les nouveaux, s'ils n'existent pas encore ; ne supprime jamais.

    Si les deux existent, rien n'est touché (l'ancien reste là, à vérifier à la main). Renvoie ce qui a été déplacé.
    """
    moved = []
    for base in (config_home(), data_home()):
        old, new = base / LEGACY, base / APP
        if old.is_dir() and not old.is_symlink() and not new.exists():
            old.rename(new)  # même système de fichiers : instantané, rien n'est copié ni perdu
            moved.append(f"{old} → {new}")
    return moved


def migrate_repo_data(project_root: Path) -> list[str]:
    """Captures et jeu de test sortent du dossier du code (en lecture seule dans une AppImage) vers DATA_DIR.

    Décidé le 2026-11-07 : les captures sont DÉPLACÉES (ignorées par git) ; le jeu de test est COPIÉ, pour que
    l'exemplaire suivi par git dans le dépôt (et les bancs de spikes/ qui le lisent) reste intact. Une seule fois :
    rien n'est fait si la destination existe déjà.
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
