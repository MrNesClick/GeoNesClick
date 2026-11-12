"""One-time conversion of the files written by GeoNesClick 0.1 (French ids) to the current ids (English), at the
engine's start and before the first-launch assistant writes the settings. The
files are converted once, the code then knows a single set of names; the test set is never rewritten (it is read
through the old names, see vision.py). Each step does nothing once done, and keeps a backup of what it rewrites.

  my-metas.toml   was mes-metas.toml: categories renamed, seed clues settled by their id (seed = "...")
  config.toml     category names in [metas] category_looks / category_weights and [plonkit] keywords; a vision or
                  marks prompt written for 0.1 (French answer keys) is removed: the default one applies again
  plonkit.sqlite  categories and classification sources of the Plonk It tips (the AI's work is kept)

The French names below exist only to read those old files.
"""

from __future__ import annotations

import shutil
import sqlite3
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.exceptions import TOMLKitError

from . import paths
from .plonkit import DATA_DIR as PLONKIT_DIR

OLD_CATEGORIES = {
    "langue": "language", "conduite": "driving", "marquage": "road_lines", "poteaux": "poles", "bornes": "bollards",
    "plaques": "plates", "panneaux": "signs", "domaine": "domains", "voiture": "car", "autre": "other",
}
OLD_SOURCES = {"etiquette": "tag", "mots-cles": "keywords", "aucune": "none", "ia": "ai"}  # Plonk It classification
OLD_METAS_FILE = "mes-metas.toml"
METAS_FILE = "my-metas.toml"
# The seed's clues as 0.1 wrote them (French), to recognise the player's verdicts: seed id → old hint.
OLD_SEED_HINTS = {
    "language_se": "Suédois : å, ä, ö ; « väg », « gatan »",
    "language_no": "Norvégien : æ, ø, å ; « vei » ou « veg », « gate »",
    "language_dk": "Danois : æ, ø, å ; « vej », « gade »",
    "language_fi": "Finnois : ä, ö, lettres doublées (« katu », « tie ») ; parfois bilingue avec le suédois",
    "language_ee": "Estonien : õ (propre à l'estonien dans la région), ä, ö, ü ; « tee », « tänav »",
    "language_lv": "Letton : voyelles longues à macron (ā, ē, ī, ū), ļ, ņ, ķ, ģ ; « iela »",
    "language_lt": "Lituanien : ą, ę, ė, į, ų, ū ; « gatvė »",
    "language_pl": "Polonais : ł, ą, ę, ś, ź, ż, ń ; « ulica » (ul.)",
    "language_cz": "Tchèque : ř, ů, ě ; « ulice »",
    "language_sk": "Slovaque : ä, ľ, ĺ, ŕ, ô ; « ulica »",
    "language_hu": "Hongrois : ő, ű (doubles accents aigus) ; « utca »",
    "language_si": "Slovène : č, š, ž mais ni ć ni đ ; « cesta », « ulica »",
    "language_hr": "Croate : alphabet latin seul, avec č, ć, đ, š, ž",
    "language_rs": "Serbe : cyrillique, souvent accompagné du latin (đ, ć, č)",
    "language_me_mk": "Cyrillique et latin possibles (comme en Serbie)",
    "language_bg": "Bulgare : cyrillique, avec un ъ très fréquent",
    "language_ua": "Ukrainien : cyrillique avec і, ї, є",
    "language_ru": "Russe : cyrillique avec ы, э",
    "language_ro": "Roumain : ă, â, î, ș, ț ; « strada »",
    "language_de_at": "Allemand avec ß ; « Straße »",
    "language_ch": "Allemand sans ß, français ou italien selon la région",
    "language_nl": "Néerlandais : « ij », « straat », « weg »",
    "language_fr": "Français : « rue », « avenue », é, è, à",
    "language_be": "Français ou néerlandais selon la région",
    "language_es": "Espagnol : ñ ; « calle » (parfois catalan, basque ou galicien)",
    "language_pt": "Portugais : ã, õ, ç ; « rua »",
    "language_it": "Italien : « via », « strada »",
    "language_gr": "Alphabet grec",
    "language_tr": "Turc : ı (i sans point), ğ, ş, ç ; « cadde », « sokak »",
    "driving_left": "Circulation à gauche",
    "driving_right": "Circulation à droite",
    "road_lines_yellow": "Ligne centrale jaune",
    "road_lines_white": "Ligne centrale blanche",
    "domains_se": ".se",
    "domains_no": ".no",
    "domains_fi": ".fi",
    "domains_ee": ".ee",
    "domains_lv": ".lv",
    "domains_lt": ".lt",
    "domains_pl": ".pl",
    "domains_cz": ".cz",
    "domains_sk": ".sk",
    "domains_hu": ".hu",
    "domains_si": ".si",
    "domains_hr": ".hr",
    "domains_rs": ".rs",
    "domains_de": ".de",
    "domains_at": ".at",
    "domains_dk": ".dk",
    "domains_ro": ".ro",
    "domains_bg": ".bg",
}


def _write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)  # atomic


def _backup(path: Path) -> None:
    copy = path.with_name(path.name + ".before-0.2")
    if not copy.exists():
        shutil.copy2(path, copy)


def _seed_texts() -> dict[str, dict[str, Any]]:
    seed = tomllib.loads(resources.files(__package__).joinpath("metas_amorce.toml").read_text())
    return {m["id"]: m for m in seed["meta"]}


def convert_metas(text: str) -> str:
    """The content of an old metas file with the current ids (comments and order kept)."""
    doc = tomlkit.parse(text)
    seed = _seed_texts()
    by_old_hint = {hint: i for i, hint in OLD_SEED_HINTS.items()}
    for entry in doc.get("meta", []):
        category = str(entry.get("category", ""))
        if category in OLD_CATEGORIES:
            entry["category"] = OLD_CATEGORIES[category]
        found = by_old_hint.get(str(entry.get("hint", "")).strip())
        if found and "seed" not in entry:  # a verified copy of a seed clue: linked by its id, English text
            entry["seed"] = found
            entry["hint"] = seed[found]["hint"]
            if seed[found].get("look"):
                entry["look"] = seed[found]["look"]
    if "rejected" in doc and any("seed" not in entry for entry in doc["rejected"]):  # 0.1 format: category + hint
        kept = tomlkit.aot()
        for entry in doc["rejected"]:
            found = entry.get("seed") or by_old_hint.get(str(entry.get("hint", "")).strip())
            if found:  # a dismissal no longer matching any seed clue has nothing left to dismiss
                table = tomlkit.table()
                table["seed"] = found
                kept.append(table)
        doc["rejected"] = kept
    return tomlkit.dumps(doc)


def _user_config(config_dir: Path) -> dict[str, Any]:
    path = config_dir / "config.toml"
    try:
        return tomllib.loads(path.read_text()) if path.is_file() else {}
    except tomllib.TOMLDecodeError:
        return {}  # unreadable: left to the settings' own error message


def migrate_metas(config_dir: Path, user_file: str = "") -> str | None:
    if user_file:  # a file the player chose: converted in place
        path = Path(user_file).expanduser()
        if not path.is_file():
            return None
        text = path.read_text()
        new = convert_metas(text)
        if new == text:
            return None
        _backup(path)
        _write(path, new)
        return f"{path}: converted to the current ids (backup: {path.name}.before-0.2)"
    old, new_path = config_dir / OLD_METAS_FILE, config_dir / METAS_FILE
    if not old.is_file() or new_path.exists():
        return None
    _write(new_path, convert_metas(old.read_text()))
    old.rename(old.with_name(old.name + ".before-0.2"))
    return f"{old} → {new_path} (converted; backup: {old.name}.before-0.2)"


def migrate_config(config_dir: Path) -> str | None:
    path = config_dir / "config.toml"
    if not path.is_file():
        return None
    text = path.read_text()
    try:
        doc = tomlkit.parse(text)
    except TOMLKitError:
        return None  # unreadable: left to the settings' own error message
    for section, key in (("metas", "category_looks"), ("metas", "category_weights"), ("plonkit", "keywords")):
        part = doc.get(section, {})
        table = part.get(key) if hasattr(part, "get") else None
        if hasattr(table, "keys"):
            for old in [k for k in table.keys() if k in OLD_CATEGORIES]:
                new = OLD_CATEGORIES[old]
                value = table.pop(old)
                if new not in table:
                    table[new] = value
    # A prompt written for 0.1 asks for the French answer keys, which the coach no longer reads: back to the default.
    for section, old_key in (("vision", "panneaux_et_texte"), ("marks", "illisible")):
        part = doc.get(section)
        if hasattr(part, "get") and old_key in str(part.get("prompt", "")):
            del part["prompt"]
    new_text = tomlkit.dumps(doc)
    if new_text == text:
        return None
    _backup(path)
    _write(path, new_text)
    return f"{path}: converted to the current names (backup: config.toml.before-0.2)"


def migrate_plonkit(plonkit_dir: Path) -> str | None:
    db = plonkit_dir / "plonkit.sqlite"
    if not db.is_file():
        return None
    con = sqlite3.connect(db)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "tip" not in tables:
            return None
        changed = 0
        with con:
            for old, new in OLD_CATEGORIES.items():
                changed += con.execute("UPDATE tip SET category = ? WHERE category = ?", (new, old)).rowcount
                if "ai_category" in tables:
                    changed += con.execute("UPDATE ai_category SET category = ? WHERE category = ?", (new, old)).rowcount
            for old, new in OLD_SOURCES.items():
                changed += con.execute("UPDATE tip SET category_source = ? WHERE category_source = ?", (new, old)).rowcount
    finally:
        con.close()
    return f"{db}: {changed} categories converted" if changed else None


def run(config_dir: Path | None = None, plonkit_dir: Path | None = None) -> list[str]:
    """Every conversion still to do; returns what was done (English, for the log). Never raises: a file that cannot
    be converted (unreadable, damaged) is left as it is, and the usual error messages report it."""
    config_dir = config_dir or paths.CONFIG_DIR
    cfg = _user_config(config_dir)
    metas, plonkit = cfg.get("metas"), cfg.get("plonkit")
    user_file = str(metas.get("user_file", "") or "") if isinstance(metas, dict) else ""
    data_dir = str(plonkit.get("data_dir", "") or "") if isinstance(plonkit, dict) else ""
    plonkit_dir = plonkit_dir or (Path(data_dir).expanduser() if data_dir else PLONKIT_DIR)
    done = []
    for step, args in ((migrate_metas, (config_dir, user_file)), (migrate_config, (config_dir,)),
                       (migrate_plonkit, (plonkit_dir,))):
        try:
            done.append(step(*args))
        except (OSError, ValueError, TOMLKitError, sqlite3.Error, AttributeError, TypeError) as exc:
            done.append(f"{step.__name__}: left as it is ({type(exc).__name__}: {exc})")
    return [d for d in done if d]
