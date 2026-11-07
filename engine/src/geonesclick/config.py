"""Configuration : valeurs par défaut du paquet, surchargées par le fichier utilisateur."""

from __future__ import annotations

import os
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .metas import CATEGORIES
from .plonkit import DATA_DIR as PLONKIT_DATA_DIR

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
    keep_last: int = Field(ge=0)
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
    # Ce qui s'affiche sans clic : 1 où regarder, 2 + ce que voit l'IA, 3 + pays probables et indices,
    # 4 + synthèse de la réponse (pays, région si un texte la nomme, preuve).
    help_level: int = Field(ge=1, le=4)
    # Une preuve lue par l'IA avec une certitude forte (texte nommant un lieu…) met ce pays en tête et
    # écarte les autres, au lieu des seuls pourcentages de StreetCLIP.
    trust_proof: bool
    language: Literal["fr", "en", "es", "de", "it", "pt"]  # langue des traductions (l'interface suivra)


class DatasetConfig(BaseModel):
    enabled: bool
    directory: str
    ask_guessed: bool  # demander le pays répondu (sinon : « Tu l'avais trouvé ? » Oui / Non)
    max_confusions: int = Field(ge=0, le=10)  # 0 = confusions masquées

    @property
    def path(self) -> Path:
        return Path(self.directory).expanduser() if self.directory else PROJECT_ROOT / "engine" / "dataset"


class MetasConfig(BaseModel):
    enabled: bool
    include_seed: bool
    user_file: str
    min_probability: float = Field(ge=0, le=1)
    max_candidates: int = Field(ge=2, le=20)
    max_categories: int = Field(ge=1, le=12)
    show_looks: bool  # consignes « Regarde… » avant de révéler les pays
    max_looks: int = Field(ge=1, le=5)
    judge_buttons: bool  # boutons « Juste » / « Faux » sur les indices de l'amorce
    category_looks: dict[str, str] = {}  # remplace la consigne par défaut d'une catégorie
    category_weights: dict[str, float] = {}  # remplace le poids d'une catégorie dans le départage

    @field_validator("category_looks", "category_weights")
    @classmethod
    def _known_categories(cls, value: dict) -> dict:
        if unknown := set(value) - set(CATEGORIES):
            raise ValueError(f"catégories inconnues : {', '.join(sorted(unknown))}")
        return value

    @field_validator("category_weights")
    @classmethod
    def _positive_weights(cls, value: dict[str, float]) -> dict[str, float]:
        if any(w < 0 for w in value.values()):
            raise ValueError("un poids doit être positif ou nul")
        return value

    @property
    def user_path(self) -> Path:
        return Path(self.user_file).expanduser() if self.user_file else CONFIG_DIR / "mes-metas.toml"


class PlonkitConfig(BaseModel):
    enabled: bool  # collecter et utiliser les guides Plonk It (base locale, jamais redistribuée)
    data_dir: str  # vide = ~/.local/share/geonesclick/plonkit
    refresh_days: int = Field(ge=1, le=365)  # contrôle de la liste des guides au plus tous les N jours
    delay_s: float = Field(ge=1.0, le=60.0)  # pause entre deux pages lors d'une collecte
    similar_tips: bool  # « les astuces qui ressemblent à ta vue », pour chaque pays candidat
    similar_per_country: int = Field(ge=1, le=5)
    keywords: dict[str, list[str]] = {}  # remplace les mots-clés de classement d'une catégorie
    ai_classify: bool  # faire classer par l'IA les astuces restées sans catégorie (une fois par texte)
    ai_model: str  # vide = le modèle du niveau 2
    ai_batch: int = Field(ge=5, le=50)  # astuces par appel
    ai_pause_s: float = Field(ge=0.0, le=60.0)  # pause entre deux appels (limites du palier gratuit)
    translate: bool  # traduire les astuces affichées dans la langue du coach (à la demande, en cache)

    @field_validator("keywords")
    @classmethod
    def _known_categories(cls, value: dict) -> dict:
        if unknown := set(value) - set(CATEGORIES):
            raise ValueError(f"catégories inconnues : {', '.join(sorted(unknown))}")
        return value

    @property
    def path(self) -> Path:
        return Path(self.data_dir).expanduser() if self.data_dir else PLONKIT_DATA_DIR


class StreetClipConfig(BaseModel):
    enabled: bool
    model: str
    device: str
    prompt: str
    top_k: int = Field(ge=1, le=20)
    countries: dict[str, str]  # nom anglais (prompt) → code ISO à 2 lettres
    exclude_countries: list[str] = []  # codes retirés de la liste (la fusion des fichiers ne sait qu'ajouter)

    @model_validator(mode="after")
    def _exclude(self) -> StreetClipConfig:
        excluded = {c.upper() for c in self.exclude_countries}
        self.countries = {name: code for name, code in self.countries.items() if code.upper() not in excluded}
        if len(self.countries) < 2:
            raise ValueError("il faut au moins 2 pays candidats")
        return self


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
    dataset: DatasetConfig
    metas: MetasConfig
    plonkit: PlonkitConfig
    streetclip: StreetClipConfig
    vision: VisionConfig


def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Fusion récursive : les tables sont fusionnées, les autres valeurs remplacées."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path = USER_CONFIG) -> Config:
    data = tomllib.loads(resources.files(__package__).joinpath("default_config.toml").read_text())
    if path.exists():
        data = merge(data, tomllib.loads(path.read_text()))
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
