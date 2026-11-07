"""Chemins partagés, sans dépendance lourde (importé par le client du raccourci clavier).

Nom de l'application : GeoNesClick (décidé avec l'utilisateur le 2026-11-07, d'après son pseudo MrNesClick ;
« GeoNesClick » était trop proche de la marque GeoGuessr). Les dossiers de l'ancien nom sont DÉPLACÉS une fois
vers les nouveaux au démarrage (migrate_legacy), jamais supprimés : réglages, metas, index des lieux, et des heures
de traductions Plonk It.
"""

import os
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
