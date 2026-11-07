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
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .places import ARCHIVE, DB_NAME, OLD_DBS

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
    return files_of(places_dir, [DB_NAME, ARCHIVE, *OLD_DBS])


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
