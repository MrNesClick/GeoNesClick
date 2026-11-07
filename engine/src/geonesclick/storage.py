"""Stockage du coach : ce qu'il garde sur le disque, sa taille, et comment le vider (Réglages › Stockage).

Décidé avec l'utilisateur le 2026-11-07 :
- chaque élément s'affiche avec sa taille et peut être vidé à la main ;
- la taille maximale ([storage] max_cache_mb) ne s'applique qu'aux caches QUI GROSSISSENT tout seuls (villages par
  pays ; plus tard rues par ville et Nominatim) : les moins récemment utilisés partent d'abord ;
- le SOCLE (index GeoNames, base Plonk It) ne part jamais tout seul : sinon chaque démarrage le retéléchargerait ;
- le jeu de test, tes metas et ta config ne sont JAMAIS touchés ; les poids des modèles (Hugging Face) non plus.

Sécurité : on ne supprime que des FICHIERS CONNUS (motifs ci-dessous), jamais un dossier entier : les dossiers sont
réglables, et un chemin mal configuré (~) ne doit pas pouvoir être effacé.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .places import ARCHIVE, DB_NAME, OLD_DBS, REGIONS

VILLAGES = "detail-*.sqlite"
PLONKIT_FILES = ("plonkit.sqlite", "plonkit.sqlite-wal", "plonkit.sqlite-shm", "index.json", "checked_at")
CAPTURE_FILES = ("capture-*.png", "capture-*.json", "mark-*.png")


@dataclass
class Item:
    id: str
    label: str
    kind: str  # "cache" (grossit, limité), "socle" (vidé à la main seulement), "historique"
    size: int  # octets
    detail: str  # ce qu'il contient, en clair
    effect: str  # ce que « Vider » coûte
    confirm: bool = False  # vider demande une confirmation (perte coûteuse)


def files_of(directory: Path, patterns: Iterable[str]) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted({p for pattern in patterns for p in directory.glob(pattern) if p.is_file() and not p.is_symlink()})


def size_of(files: Iterable[Path]) -> int:
    total = 0
    for f in files:
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return total


def village_files(places_dir: Path) -> list[Path]:
    return files_of(places_dir, [VILLAGES])


def base_place_files(places_dir: Path) -> list[Path]:
    return files_of(places_dir, [DB_NAME, ARCHIVE, REGIONS, *OLD_DBS])


def plonkit_files(plonkit_dir: Path) -> list[Path]:
    return files_of(plonkit_dir, PLONKIT_FILES) + files_of(plonkit_dir / "raw", ["*.json"])


def capture_files(capture_dir: Path) -> list[Path]:
    return files_of(capture_dir, CAPTURE_FILES)


def inventory(places_dir: Path, plonkit_dir: Path, capture_dir: Path) -> list[dict[str, Any]]:
    villages = village_files(places_dir)
    countries = sorted(f.name.split("-")[1] for f in villages)
    captures = capture_files(capture_dir)
    shots = sum(1 for f in captures if f.name.startswith("capture-") and f.suffix == ".png")
    items = [
        Item("villages", "Villages des pays rencontrés", "cache", size_of(villages),
             ", ".join(countries) if countries else "aucun pays pour l'instant",
             "Retéléchargés quand le pays revient en tête (France : 7,3 Mo)."),
        Item("lieux", "Répertoire des lieux (GeoNames)", "socle", size_of(base_place_files(places_dir)),
             "localités de plus de 1 000 habitants, toutes langues",
             "Noms de lieux indisponibles jusqu'au prochain démarrage, qui le retélécharge (~11 Mo) ; vide aussi "
             "les villages."),
        Item("plonkit", "Guides Plonk It", "socle", size_of(plonkit_files(plonkit_dir)),
             "guides, vecteurs, classement et traductions", "Recollectés au prochain démarrage (~3 min), mais "
             "les traductions d'avance sont à refaire : des heures d'appels à l'API.", confirm=True),
        Item("captures", "Captures et journaux de débogage", "historique", size_of(captures),
             f"{shots} captures, découpes des marques, journaux", "Perdues ; le jeu de test n'est pas touché."),
    ]
    return [asdict(i) for i in items]


def remove(files: Iterable[Path]) -> int:
    freed = 0
    for f in files:
        try:
            size = f.stat().st_size
            f.unlink()
            freed += size
        except OSError:
            pass
    return freed


def evict(places_dir: Path, max_bytes: int, keep: set[str] = frozenset()) -> list[str]:
    """Caches qui grossissent au-delà de la limite : les moins récemment utilisés partent d'abord.

    keep : pays à ne jamais retirer maintenant (celui de la manche en cours). Renvoie les pays retirés.
    """
    files = village_files(places_dir)
    total = size_of(files)
    removed = []
    for f in sorted(files, key=lambda p: p.stat().st_mtime):
        if total <= max_bytes:
            break
        country = f.name.split("-")[1]
        if country in keep:
            continue
        total -= remove([f])
        removed.append(country)
    return removed


def touch(path: Path) -> None:
    """Marque un cache comme utilisé (date de modification) : il passe en dernier pour la suppression."""
    try:
        os.utime(path)
    except OSError:
        pass


# --- « Tout effacer » (droit à l'effacement, RGPD ; décidé avec l'utilisateur le 2026-11-07) -------------------
# Tout ce qui te concerne part : clé API, réglages, tes metas, captures et journaux, jeu de test, guides Plonk It et
# traductions, index des lieux, raccourcis GNOME (l'interface efface son propre état). À part, sur demande : les
# modèles téléchargés (rien de personnel). Toujours des fichiers CONNUS : dans un dossier réglé à la main, seuls les
# fichiers de l'app partent, jamais le dossier.
MODEL_ID = re.compile(r"[\w.\-]+/[\w.\-]+")  # « geolocal/StreetCLIP » : jamais de « .. » ni de « / » en trop
SHORTCUT_PATHS = ("/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/geonesclick/",
                  "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/geonesclick-mark/")
MEDIA_KEYS = "org.gnome.settings-daemon.plugins.media-keys"


def account_files(config_dir: Path, settings: Path, metas: Path) -> list[Path]:
    """Clé API, réglages, tes metas, autorisation de partage d'écran (fichiers connus seulement)."""
    named = [settings, metas, config_dir / "screencast.token"]
    return sorted({p for p in named if p.is_file() and not p.is_symlink()} | set(files_of(config_dir, ["*.key", "*.tmp"])))


def dataset_files(dataset_dir: Path) -> list[Path]:
    return (files_of(dataset_dir, ["labels.toml"]) + files_of(dataset_dir / "images", ["capture-*.png"])
            + files_of(dataset_dir / "rounds", ["*.json"]))


def model_dirs(hub_cache: Path, model_ids: Iterable[str]) -> list[Path]:
    """Dossiers du cache Hugging Face de NOS modèles seulement (ceux d'autres logiciels restent)."""
    out = []
    for model in model_ids:
        if not MODEL_ID.fullmatch(model):
            continue
        path = hub_cache / f"models--{model.replace('/', '--')}"
        if path.is_dir() and not path.is_symlink() and path.parent == hub_cache:
            out.append(path)
    return out


def dir_size(path: Path) -> int:
    return size_of(p for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def erase_plan(groups: dict[str, list[Path]], models: list[Path]) -> list[dict[str, Any]]:
    labels = {"compte": "Clé API, réglages, tes metas", "captures": "Captures et journaux",
              "jeu": "Jeu de test (manches, images, banc)", "plonkit": "Guides Plonk It et traductions",
              "lieux": "Lieux GeoNames et villages"}
    out = [{"id": key, "label": labels[key], "files": len(files), "size": size_of(files), "precious": key == "jeu",
            "optional": False} for key, files in groups.items()]
    out.append({"id": "modeles", "label": "Modèles téléchargés (StreetCLIP, PLONK)", "files": len(models),
                "size": sum(dir_size(m) for m in models), "precious": False, "optional": True})
    return out


def _gsettings(args: list[str]) -> str:
    """gsettings du système (remplacé dans les tests : ils ne touchent jamais tes raccourcis)."""
    return subprocess.run(["/usr/bin/gsettings", *args], capture_output=True, text=True, timeout=10,
                          check=False).stdout.strip()


def remove_shortcuts(run: Callable[[list[str]], str] | None = None) -> int:
    """Retire les raccourcis GNOME de l'app. Renvoie le nombre retiré."""
    run = run or _gsettings
    current = run(["get", MEDIA_KEYS, "custom-keybindings"])
    keys = re.findall(r"'([^']+)'", current)
    kept = [k for k in keys if k not in SHORTCUT_PATHS]
    if len(kept) == len(keys):
        return 0
    run(["set", MEDIA_KEYS, "custom-keybindings", str(kept)])
    for path in SHORTCUT_PATHS:
        run(["reset-recursively", f"{MEDIA_KEYS}.custom-keybinding:{path}"])
    return len(keys) - len(kept)


def erase(groups: dict[str, list[Path]], models: list[Path], with_models: bool, empty_dirs: Iterable[Path]) -> int:
    """Supprime les fichiers listés (et, si demandé, nos dossiers de modèles) ; puis les dossiers de l'app vidés."""
    freed = sum(remove(files) for files in groups.values())
    if with_models:
        for path in models:
            freed += dir_size(path)
            shutil.rmtree(path, ignore_errors=True)
    for folder in sorted(empty_dirs, key=lambda p: -len(p.parts)):  # les plus profonds d'abord
        try:
            folder.rmdir()  # seulement s'il est vide : un fichier inconnu le garde
        except OSError:
            pass
    return freed
