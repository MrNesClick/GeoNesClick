"""Coach storage: what it keeps on disk, its size, and how to empty it (Settings › Storage).

- each item is shown with its size and can be emptied by hand;
- the maximum size ([storage] max_cache_mb) only applies to the caches THAT GROW on their own (villages per
  country; later streets per city and Nominatim): the least recently used go first;
- the BASE (GeoNames index, Plonk It database) never goes on its own: otherwise each start would download it again;
- the test set, your metas and your config are NEVER touched; nor are the model weights (Hugging Face).

Security: only KNOWN FILES are deleted (patterns below), never a whole folder: the folders are
configurable, and a misconfigured path (~) must not be erasable.
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

from .i18n import t
from .places import ARCHIVE, DB_NAME, OLD_DBS, REGIONS

VILLAGES = "detail-*.sqlite"
PLONKIT_FILES = ("plonkit.sqlite", "plonkit.sqlite-wal", "plonkit.sqlite-shm", "index.json", "checked_at")
CAPTURE_FILES = ("capture-*.png", "capture-*.json", "mark-*.png")


@dataclass
class Item:
    id: str
    label: str
    kind: str  # "cache" (grows, limited), "base" (emptied by hand only), "history"
    size: int  # bytes
    detail: str  # what it contains, in plain words
    effect: str  # what "Empty" costs
    confirm: bool = False  # emptying asks for a confirmation (costly loss)


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
        Item("villages", t("storage.item.villages"), "cache", size_of(villages),
             ", ".join(countries) if countries else t("storage.item.villages.detail_none"),
             t("storage.item.villages.effect")),
        Item("places", t("storage.item.places"), "base", size_of(base_place_files(places_dir)),
             t("storage.item.places.detail"), t("storage.item.places.effect")),
        Item("plonkit", t("storage.item.plonkit"), "base", size_of(plonkit_files(plonkit_dir)),
             t("storage.item.plonkit.detail"), t("storage.item.plonkit.effect"), confirm=True),
        Item("captures", t("storage.item.captures"), "history", size_of(captures),
             t("storage.item.captures.detail", n=shots), t("storage.item.captures.effect")),
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
    """Caches that grow beyond the limit: the least recently used go first.

    keep: countries never to remove now (the one of the current round). Returns the countries removed.
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
    """Marks a cache as used (modification date): it goes last for deletion."""
    try:
        os.utime(path)
    except OSError:
        pass


# --- "Erase everything" (right to erasure, GDPR) -------------------------------------------------------------
# Everything about you goes: API key, settings, your metas, captures and logs, test set, Plonk It guides and
# translations, places index, GNOME shortcuts (the UI erases its own state). Separately, on request: the
# downloaded models (nothing personal). Always KNOWN files: in a folder set by hand, only the
# app's files go, never the folder.
MODEL_ID = re.compile(r"[\w.\-]+/[\w.\-]+")  # "geolocal/StreetCLIP": never a ".." or an extra "/"
SHORTCUT_PATHS = ("/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/geonesclick/",
                  "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/geonesclick-mark/")
MEDIA_KEYS = "org.gnome.settings-daemon.plugins.media-keys"


def account_files(config_dir: Path, settings: Path, metas: Path) -> list[Path]:
    """API key, settings, your metas, screen-sharing permission (known files only)."""
    named = [settings, metas, config_dir / "screencast.token"]
    return sorted({p for p in named if p.is_file() and not p.is_symlink()} | set(files_of(config_dir, ["*.key", "*.tmp"])))


def dataset_files(dataset_dir: Path) -> list[Path]:
    return (files_of(dataset_dir, ["labels.toml"]) + files_of(dataset_dir / "images", ["capture-*.png"])
            + files_of(dataset_dir / "rounds", ["*.json"]))


def model_dirs(hub_cache: Path, model_ids: Iterable[str]) -> list[Path]:
    """Folders of the Hugging Face cache for OUR models only (those of other software stay)."""
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
    out = [{"id": key, "label": t(f"storage.group.{key}"), "files": len(files), "size": size_of(files),
            "precious": key == "dataset",
            "optional": False} for key, files in groups.items()]
    out.append({"id": "models", "label": t("storage.group.models"), "files": len(models),
                "size": sum(dir_size(m) for m in models), "precious": False, "optional": True})
    return out


def _gsettings(args: list[str]) -> str:
    """The system's gsettings (replaced in the tests: they never touch your shortcuts)."""
    return subprocess.run(["/usr/bin/gsettings", *args], capture_output=True, text=True, timeout=10,
                          check=False).stdout.strip()


def remove_shortcuts(run: Callable[[list[str]], str] | None = None) -> int:
    """Removes the app's GNOME shortcuts. Returns the number removed."""
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
    """Deletes the listed files (and, if asked, our model folders); then the app's emptied folders."""
    freed = sum(remove(files) for files in groups.values())
    if with_models:
        for path in models:
            freed += dir_size(path)
            shutil.rmtree(path, ignore_errors=True)
    for folder in sorted(empty_dirs, key=lambda p: -len(p.parts)):  # deepest first
        try:
            folder.rmdir()  # only if it is empty: an unknown file keeps it
        except OSError:
            pass
    return freed
