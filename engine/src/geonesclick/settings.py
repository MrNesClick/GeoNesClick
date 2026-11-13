"""Settings editable from the UI, written to ~/.config/geonesclick/config.toml.

Everything is configurable. The Settings screen edits everything in EDITABLE; only the FILE_ONLY
settings stay file-only, for security: a request that bypassed the checks must not
be able to redirect the API key, open the engine to the network, load a booby-trapped model or write
elsewhere on the disk. The screen shows them read-only, with the reason. A test checks that each
configuration key is in one of the two.
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
from .i18n import set_language, t

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
        "ai_model", "ai_batch", "ai_pause_s", "translate", "translate_timeout_s", "pretranslate",
    ),
    "streetclip": ("enabled", "device", "prompt", "top_k", "countries", "exclude_countries"),
    "plonk": ("enabled", "steps", "points", "zone_share", "zone_link_km", "zone_min_part"),
    "map": ("enabled", "attribution", "tile_filter", "tile_filter_close", "close_zoom", "max_zoom"),
    "vision": (
        "enabled", "model", "thinking", "timeout_s", "max_tokens", "temperature", "max_side_px", "prompt",
    ),
    "marks": ("enabled", "max_marks", "upscale_to_px", "max_upscale", "parallel", "model", "max_tokens", "prompt"),
    "rules": ("scripts", "letters", "places", "place_min_len", "place_max_spread_km", "prior_min", "detail"),
    "locks": ("enabled", "auto_country", "auto_region", "propose_city", "region_radius_km", "region_places_km"),
    "storage": ("max_cache_mb",),
    "updates": ("check",),
    "debug": ("enabled",),
}

# Why each one is file-only: the catalog key of the reason (settings.why.<reason>).
_NETWORK, _KEY, _DISK, _MODEL, _CSP, _SOURCE = "network", "key", "disk", "model", "csp", "source"
FILE_ONLY: dict[str, dict[str, str]] = {
    "server": {"host": _NETWORK, "port": _NETWORK, "allowed_origins": _NETWORK},
    "capture": {"directory": _DISK},
    "dataset": {"directory": _DISK},
    "metas": {"user_file": _DISK},
    "plonkit": {"data_dir": _DISK},
    "streetclip": {"model": _MODEL, "revision": _MODEL},
    "plonk": {"model": _MODEL, "revision": _MODEL},
    "map": {"tile_url": _CSP, "attribution_url": _CSP},
    "vision": {"base_url": _KEY, "api_key_env": _KEY},
    "rules": {"places_url": _SOURCE, "detail_url": _SOURCE, "regions_url": _SOURCE, "places_dir": _DISK},
}

# Taken into account at the next start only (the rest applies right away).
RESTART: dict[str, tuple[str, ...]] = {
    "capture": ("source",),  # or "Change window", which reopens the GNOME picker
    "streetclip": ("enabled", "device"),
}


class SettingsError(ValueError):
    pass


def current(cfg: Config) -> dict[str, dict[str, Any]]:
    out = {section: {key: getattr(getattr(cfg, section), key) for key in keys} for section, keys in EDITABLE.items()}
    out["streetclip"]["countries"] = cfg.streetclip.all_countries  # full list: one can be put back
    return out


def file_only(cfg: Config) -> dict[str, dict[str, dict[str, Any]]]:
    """File-only settings, for the read-only display: value and reason."""
    return {
        section: {key: {"value": getattr(getattr(cfg, section), key), "why": t(f"settings.why.{why}")}
                  for key, why in keys.items()}
        for section, keys in FILE_ONLY.items()
    }


def save(changes: dict[str, dict[str, Any]], path: Path = USER_CONFIG) -> Config:
    """Validates and saves settings; returns the new full configuration.

    The file is edited in place (tomlkit): comments and order are kept. A value is written to it only
    if it changes: a value left as is keeps following the default value.
    """
    for section, values in changes.items():
        if section not in EDITABLE or not isinstance(values, dict):
            raise SettingsError(t("settings.section_locked", section=section))
        if forbidden := set(values) - set(EDITABLE[section]):
            raise SettingsError(t("settings.keys_locked", list=", ".join(sorted(forbidden))))
    text = path.read_text() if path.exists() else t("settings.header")
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
        raise SettingsError(t("settings.invalid", field=".".join(map(str, first["loc"])), message=first["msg"])) from exc
    except (TOMLKitError, TypeError, AttributeError) as exc:  # unreadable file, or section that is not a table
        raise SettingsError(t("settings.unreadable", file=path.name, error=exc)) from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(tomlkit.dumps(doc))
    tmp.replace(path)  # atomic write: never a half-written file
    return cfg


def main() -> int:
    """python -m geonesclick.settings < choices.json: saves the first-launch assistant's choices BEFORE
    the engine's first start (otherwise it would download declined options). Same checks as the screen."""
    import json
    import sys

    from . import migrate

    for converted in migrate.run():  # an update's assistant runs before the engine: 0.1's files first
        print(f"GeoNesClick: {converted}", file=sys.stderr)
    try:
        changes = json.loads(sys.stdin.read() or "{}")
        if not isinstance(changes, dict):
            raise SettingsError(t("settings.json_expected"))
        coach = changes.get("coach")
        set_language(str(coach.get("language", "en")) if isinstance(coach, dict) else "en")  # errors in its language
        save(changes)
    except (ValueError, SettingsError) as exc:
        print(f"settings refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
