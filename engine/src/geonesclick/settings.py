"""Réglages modifiables depuis l'interface, écrits dans ~/.config/geonesclick/config.toml.

Seuls les réglages qui s'appliquent à chaud sont exposés. Par sécurité, l'adresse de l'API
(vision.base_url), le nom de la variable de la clé, les origines autorisées et le port ne sont
modifiables que dans le fichier : une requête qui contournerait les contrôles ne pourrait pas
rediriger la clé API vers un autre serveur.
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
    "coach": ("default_level", "reveal_countries"),
    "capture": ("notify", "sound", "save_to_disk", "keep_last"),
    "dataset": ("ask_guessed", "max_confusions"),
    "metas": (
        "include_seed", "min_probability", "max_candidates", "max_categories", "show_looks", "max_looks",
        "judge_buttons",
    ),
    "plonkit": ("enabled", "refresh_days", "similar_tips", "similar_per_country", "ai_classify"),
    "streetclip": ("top_k",),
    "vision": ("enabled", "model", "thinking", "timeout_s", "max_tokens", "temperature", "max_side_px"),
}


class SettingsError(ValueError):
    pass


def current(cfg: Config) -> dict[str, dict[str, Any]]:
    return {section: {key: getattr(getattr(cfg, section), key) for key in keys} for section, keys in EDITABLE.items()}


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
