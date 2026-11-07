"""Clé API du modèle de vision, hors du dépôt : ~/.config/geonesclick/<nom>.key, lisible par toi seul (0600).

Décidé avec l'utilisateur le 2026-11-07 (« clé API pas dans le .env » ; fichier protégé préféré au trousseau du
système). Ordre de lecture : la variable d'environnement (tests, usages avancés), puis le fichier. Saisie depuis
Réglages › Analyse ; l'interface n'en voit jamais que les 4 derniers caractères. L'ancien .env du dépôt est migré
une fois au démarrage : la clé est DÉPLACÉE vers le fichier, puis sa ligne retirée du .env (le reste est gardé).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import paths

NAME = re.compile(r"[A-Z][A-Z0-9_]{0,63}")  # nom de la variable (« NVAPI ») : sert aussi de nom de fichier
VALUE = re.compile(r"[\x21-\x7e]{8,300}")  # caractères imprimables, sans espace ni retour à la ligne


class ApiKeyError(ValueError):
    pass


def key_file(name: str) -> Path:
    if not NAME.fullmatch(name):
        raise ApiKeyError(f"nom de clé invalide : {name!r}")
    return paths.CONFIG_DIR / f"{name.lower()}.key"


def _write_private(path: Path, text: str) -> None:
    """Écriture atomique d'un fichier lisible par toi seul (créé directement en 0600, jamais visible autrement)."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def read(name: str) -> str | None:
    if value := os.environ.get(name):
        return value
    path = key_file(name)
    try:
        value = path.read_text().strip()
    except OSError:
        return None
    return value or None


def save(name: str, value: str) -> None:
    value = value.strip()
    if not VALUE.fullmatch(value):
        raise ApiKeyError("clé invalide : 8 à 300 caractères, sans espace")
    _write_private(key_file(name), value + "\n")


def forget(name: str) -> None:
    key_file(name).unlink(missing_ok=True)


def hint(name: str) -> dict[str, str] | None:
    """Ce que l'interface peut montrer : d'où vient la clé et ses 4 derniers caractères, jamais la clé."""
    value = read(name)
    if not value:
        return None
    return {"source": "variable d'environnement" if os.environ.get(name) else "fichier", "end": value[-4:]}


def migrate_env(name: str, env_file: Path) -> bool:
    """Ancien .env du dépôt : la clé est déplacée vers le fichier protégé, puis sa ligne retirée du .env."""
    if not env_file.is_file() or key_file(name).exists():
        return False
    lines = env_file.read_text().splitlines(keepends=True)
    found = [ln.partition("=")[2].strip().strip("\"'") for ln in lines if ln.partition("=")[0].strip() == name]
    if not found or not found[-1]:
        return False
    save(name, found[-1])  # d'abord la copie protégée…
    kept = "".join(ln for ln in lines if ln.partition("=")[0].strip() != name)
    _write_private(env_file, kept)  # … puis seulement la ligne retirée
    return True
