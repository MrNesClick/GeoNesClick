"""Configuration : valeurs par défaut du paquet, surchargées par le fichier utilisateur."""

from __future__ import annotations

import os
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "geonesclick"
USER_CONFIG = CONFIG_DIR / "config.toml"
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # engine/src/geonesclick → racine du dépôt

Rect = list[float]


def _check_rect(rect: Rect, name: str) -> Rect:
    """Rectangle en fractions [gauche, haut, droite, bas], avec 0 ≤ gauche < droite ≤ 1 (idem en hauteur)."""
    if len(rect) != 4:
        raise ValueError(f"{name} : 4 valeurs attendues [gauche, haut, droite, bas], {len(rect)} reçues")
    left, top, right, bottom = rect
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError(f"{name} : fractions entre 0 et 1 attendues, avec gauche < droite et haut < bas")
    return rect


class ServerConfig(BaseModel):
    host: str
    port: int
    allowed_origins: list[str]


class CaptureConfig(BaseModel):
    source: Literal["window", "monitor", "both"]
    notify: bool
    sound: bool
    save_to_disk: bool
    directory: str
    crop: Rect = Field(default_factory=list)
    masks: list[Rect] = Field(default_factory=list)

    @field_validator("crop")
    @classmethod
    def _crop(cls, v: Rect) -> Rect:
        return _check_rect(v, "capture.crop") if v else v  # liste vide = image entière

    @field_validator("masks")
    @classmethod
    def _masks(cls, v: list[Rect]) -> list[Rect]:
        return [_check_rect(m, f"capture.masks[{i}]") for i, m in enumerate(v)]

    @property
    def path(self) -> Path:
        return Path(self.directory).expanduser() if self.directory else PROJECT_ROOT / "engine" / "captures"


class CoachConfig(BaseModel):
    default_level: int = Field(ge=1, le=2)


class StreetClipConfig(BaseModel):
    enabled: bool
    model: str
    device: str
    prompt: str
    top_k: int = Field(ge=1, le=20)
    countries: dict[str, str]


class VisionConfig(BaseModel):
    enabled: bool
    base_url: str
    api_key_env: str
    model: str
    thinking: bool
    timeout_s: float
    max_tokens: int
    temperature: float
    max_side_px: int
    prompt: str


class Config(BaseModel):
    server: ServerConfig
    capture: CaptureConfig
    coach: CoachConfig
    streetclip: StreetClipConfig
    vision: VisionConfig


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Fusion récursive : les tables sont fusionnées, les autres valeurs remplacées."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path = USER_CONFIG) -> Config:
    data = tomllib.loads(resources.files(__package__).joinpath("default_config.toml").read_text())
    if path.exists():
        data = _merge(data, tomllib.loads(path.read_text()))
    return Config.model_validate(data)


def read_secret(name: str) -> str | None:
    """Lit un secret dans l'environnement, sinon dans le .env à la racine du projet."""
    if value := os.environ.get(name):
        return value
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip("\"'") or None
    return None
