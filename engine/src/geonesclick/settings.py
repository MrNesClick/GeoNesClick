"""Réglages modifiables depuis l'interface, écrits dans ~/.config/geonesclick/config.toml.

Tout est configurable. L'écran Réglages modifie tout ce qui est dans EDITABLE ; seuls les réglages de
FILE_ONLY restent réservés au fichier, par sécurité : une requête qui contournerait les contrôles ne doit
pas pouvoir rediriger la clé API, ouvrir le moteur au réseau, charger un modèle piégé ou faire écrire
ailleurs sur le disque. L'écran les affiche en lecture seule, avec la raison. Un test vérifie que chaque
clé de la configuration est dans l'un des deux.
"""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path
from typing import Any

import tomlkit
from pydantic import ValidationError
from tomlkit.exceptions import TOMLKitError

from .config import USER_CONFIG, Config, merge

EDITABLE: dict[str, tuple[str, ...]] = {
    "coach": ("help_level", "trust_proof", "language", "leader_min", "leader_margin"),
    "capture": ("source", "notify", "sound", "save_to_disk", "keep_last", "crop", "masks"),
    "dataset": ("enabled", "ask_guessed", "max_confusions"),
    "metas": (
        "enabled", "include_seed", "min_probability", "max_candidates", "max_categories", "show_looks", "max_looks",
        "judge_buttons", "category_looks", "category_weights",
    ),
    "plonkit": (
        "enabled", "refresh_days", "delay_s", "similar_tips", "similar_per_country", "keywords", "ai_classify",
        "ai_model", "ai_batch", "ai_pause_s", "translate",
    ),
    "streetclip": ("enabled", "device", "prompt", "top_k", "countries", "exclude_countries"),
    "plonk": ("enabled", "steps", "points", "zone_share", "zone_link_km", "zone_min_part"),
    "map": ("enabled", "attribution", "tile_filter", "max_zoom"),
    "vision": (
        "enabled", "model", "thinking", "timeout_s", "max_tokens", "temperature", "max_side_px", "prompt",
    ),
    "debug": ("enabled",),
}

_NETWORK = "réseau du moteur : il ne doit écouter que ta machine et ta fenêtre du coach"
_KEY = "redirigerait ta clé API vers un autre serveur"
_DISK = "chemin sur le disque : une requête ne doit pas pouvoir faire écrire ailleurs"
_MODEL = "modèle téléchargé puis exécuté sur ta machine : un modèle piégé pourrait exécuter du code"
_CSP = "doit aussi être autorisé dans la fenêtre (CSP et autorisations de Tauri)"
FILE_ONLY: dict[str, dict[str, str]] = {
    "server": {"host": _NETWORK, "port": _NETWORK, "allowed_origins": _NETWORK},
    "capture": {"directory": _DISK},
    "dataset": {"directory": _DISK},
    "metas": {"user_file": _DISK},
    "plonkit": {"data_dir": _DISK},
    "streetclip": {"model": _MODEL},
    "plonk": {"model": _MODEL, "revision": _MODEL},
    "map": {"tile_url": _CSP, "attribution_url": _CSP},
    "vision": {"base_url": _KEY, "api_key_env": _KEY},
}

# Pris en compte au prochain démarrage seulement (le reste s'applique tout de suite).
RESTART: dict[str, tuple[str, ...]] = {
    "capture": ("source",),  # ou « Changer de fenêtre », qui rouvre le sélecteur de GNOME
    "streetclip": ("enabled", "device"),
}


class SettingsError(ValueError):
    pass


def current(cfg: Config) -> dict[str, dict[str, Any]]:
    out = {section: {key: getattr(getattr(cfg, section), key) for key in keys} for section, keys in EDITABLE.items()}
    out["streetclip"]["countries"] = cfg.streetclip.all_countries  # liste complète : on peut en remettre un
    return out


def file_only(cfg: Config) -> dict[str, dict[str, dict[str, Any]]]:
    """Réglages réservés au fichier, pour l'affichage en lecture seule : valeur et raison."""
    return {
        section: {key: {"value": getattr(getattr(cfg, section), key), "why": why} for key, why in keys.items()}
        for section, keys in FILE_ONLY.items()
    }


HEADER = (
    "# Tes réglages GeoNesClick : ils remplacent les valeurs par défaut clé par clé.\n"
    "# Modifiable à la main ou depuis l'écran Réglages du coach (tes commentaires sont conservés).\n\n"
)


def save(changes: dict[str, dict[str, Any]], path: Path = USER_CONFIG) -> Config:
    """Valide et enregistre des réglages ; renvoie la nouvelle configuration complète.

    Le fichier est modifié en place (tomlkit) : commentaires et ordre conservés. Une valeur n'y est écrite
    que si elle change : une valeur laissée telle quelle continue de suivre la valeur par défaut.
    """
    for section, values in changes.items():
        if section not in EDITABLE or not isinstance(values, dict):
            raise SettingsError(f"section non modifiable depuis l'interface : {section}")
        if forbidden := set(values) - set(EDITABLE[section]):
            raise SettingsError(f"réglages non modifiables depuis l'interface : {', '.join(sorted(forbidden))}")
    text = path.read_text() if path.exists() else HEADER
    defaults = tomllib.loads(resources.files(__package__).joinpath("default_config.toml").read_text())
    try:
        doc = tomlkit.parse(text)
        before = merge(defaults, doc.unwrap())
        for section, values in changes.items():
            for key, value in values.items():
                if value != before.get(section, {}).get(key):
                    doc.setdefault(section, tomlkit.table())[key] = value
        cfg = Config.model_validate(merge(defaults, doc.unwrap()))
    except ValidationError as exc:
        first = exc.errors()[0]
        raise SettingsError(f"{'.'.join(map(str, first['loc']))} : {first['msg']}") from exc
    except (TOMLKitError, TypeError, AttributeError) as exc:  # fichier illisible, ou section qui n'est pas une table
        raise SettingsError(f"{path.name} illisible, corrige-le à la main : {exc}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(tomlkit.dumps(doc))
    tmp.replace(path)  # écriture atomique : jamais de fichier à moitié écrit
    return cfg
