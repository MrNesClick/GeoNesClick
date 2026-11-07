"""Configuration : valeurs par défaut du paquet, surchargées par le fichier utilisateur."""

from __future__ import annotations

import os
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator

from .metas import CATEGORIES
from .paths import CONFIG_DIR, DATA_DIR  # un seul endroit pour les dossiers de l'application
from .plonkit import DATA_DIR as PLONKIT_DATA_DIR

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
    # Un pays ne s'affiche en réponse que s'il se détache : au moins leader_min, et leader_margin d'avance
    # sur le 2ᵉ. Sinon le coach parle d'hésitation entre les premiers, au lieu d'un faux gagnant.
    leader_min: float = Field(ge=0, le=1)
    leader_margin: float = Field(ge=0, le=1)


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
    ai_model: str = Field(max_length=120, pattern=r"^$|^[\w.\-]+/[\w.\-]+$")  # vide = le modèle du niveau 2
    ai_batch: int = Field(ge=5, le=50)  # astuces par appel
    ai_pause_s: float = Field(ge=0.0, le=60.0)  # pause entre deux appels (limites du palier gratuit)
    translate: bool  # traduire les astuces affichées dans la langue du coach (à la demande, en cache)
    translate_timeout_s: float = Field(ge=5.0, le=120.0)  # au-delà, le lot reste en anglais (pas de nouvel essai)
    pretranslate: bool  # traduire d'avance toute la base en arrière-plan, après les analyses en cours

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
    device: str = Field(pattern=r"^(auto|cpu|cuda(:\d+)?)$")
    prompt: str = Field(min_length=5, max_length=300)
    top_k: int = Field(ge=1, le=20)
    countries: dict[str, str]  # nom anglais (prompt) → code ISO à 2 lettres
    exclude_countries: list[str] = []  # codes retirés de la liste (la fusion des fichiers ne sait qu'ajouter)
    _all_countries: dict[str, str] = PrivateAttr(default_factory=dict)  # avant exclusion (écran Réglages)

    @field_validator("prompt")
    @classmethod
    def _placeholder(cls, v: str) -> str:
        # Passé à str.format : une seule accolade {} et aucune autre (ni champ nommé, ni largeur géante).
        if v.count("{}") != 1 or "{" in v.replace("{}", "") or "}" in v.replace("{}", ""):
            raise ValueError("le prompt doit contenir une fois {} (le nom du pays) et aucune autre accolade")
        return v

    @field_validator("countries")
    @classmethod
    def _codes(cls, v: dict[str, str]) -> dict[str, str]:
        if bad := [code for code in v.values() if not (len(code) == 2 and code.isalpha() and code.isupper())]:
            raise ValueError(f"codes pays invalides (2 lettres majuscules attendues) : {', '.join(bad)}")
        return v

    @model_validator(mode="after")
    def _exclude(self) -> StreetClipConfig:
        self._all_countries = dict(self.countries)
        excluded = {c.upper() for c in self.exclude_countries}
        self.countries = {name: code for name, code in self.countries.items() if code.upper() not in excluded}
        if len(self.countries) < 2:
            raise ValueError("il faut au moins 2 pays candidats")
        return self

    @property
    def all_countries(self) -> dict[str, str]:
        return self._all_countries


class PlonkConfig(BaseModel):
    # Nuage de positions probables pour la carte (PLONK sur le vecteur de StreetCLIP), jamais un vote de pays.
    enabled: bool
    model: str
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")  # commit Hugging Face des poids : version mesurée, figée
    steps: int = Field(ge=10, le=250)  # pas du flot : 50 suffisent (mesuré), 25 dégradent le nuage
    points: int = Field(ge=64, le=2048)
    zone_share: float = Field(gt=0.2, le=1.0)  # part des points (les plus denses) que les zones englobent
    zone_link_km: float = Field(ge=20, le=1000)  # deux points plus proches que ça sont dans la même zone
    zone_min_part: float = Field(ge=0.01, le=0.5)  # part minimale des points pour qu'une zone soit montrée


class MapConfig(BaseModel):
    # Carte du coach (niveau 3 et plus) : pays probables, nuage PLONK. Fond de carte en ligne.
    enabled: bool
    # Serveur de tuiles. Un autre serveur doit AUSSI être autorisé dans la CSP (img-src) de
    # app/src-tauri/tauri.conf.json ; sinon ses tuiles sont bloquées.
    tile_url: str = Field(pattern=r"^https://[^\s\"'<>]+\{z\}[^\s\"'<>]*$")
    attribution: str = Field(min_length=1, max_length=200)  # texte simple, affiché en permanence sur la carte
    attribution_url: str = Field(pattern=r"^https://[^\s\"'<>]+$")
    tile_filter: str = Field(max_length=200, pattern=r"^[a-z0-9().%,\s-]*$")  # filtre CSS des tuiles (thème sombre)
    # De près (rues, villages), l'inversion des couleurs devient illisible : autre filtre à partir de close_zoom.
    tile_filter_close: str = Field(max_length=200, pattern=r"^[a-z0-9().%,\s-]*$")
    close_zoom: int = Field(ge=2, le=19)
    max_zoom: int = Field(ge=2, le=19)


class VisionConfig(BaseModel):
    enabled: bool
    base_url: str
    api_key_env: str
    model: str = Field(min_length=3, max_length=120, pattern=r"^[\w.\-]+/[\w.\-]+$")
    thinking: bool
    timeout_s: float = Field(ge=5, le=300)
    max_tokens: int = Field(ge=100, le=16000)
    temperature: float = Field(ge=0, le=2)
    max_side_px: int = Field(ge=256, le=4096)  # au-delà, la requête devient lourde sans gain mesuré
    prompt: str = Field(min_length=20, max_length=20000)


class MarksConfig(BaseModel):
    # Marques : sur la vue figée, le joueur entoure des indices (panneau, plaque…) ; chacun est découpé dans
    # l'image brute, agrandi s'il est petit, puis transcrit par le modèle de vision.
    enabled: bool
    max_marks: int = Field(ge=1, le=20)  # marques par image figée (numérotées ① à ⑳)
    # Agrandissement : le plus grand côté de la découpe est porté à upscale_to_px, sans dépasser max_upscale.
    upscale_to_px: int = Field(ge=64, le=2048)
    max_upscale: float = Field(ge=1.0, le=8.0)
    parallel: int = Field(ge=1, le=8)  # lectures simultanées (limites de l'API)
    model: str = Field(max_length=120, pattern=r"^$|^[\w.\-]+/[\w.\-]+$")  # vide = le modèle du niveau 2
    max_tokens: int = Field(ge=50, le=4000)
    prompt: str = Field(min_length=20, max_length=5000)


class RulesConfig(BaseModel):
    # Règles locales appliquées au texte des marques (evidence.py) : elles concluent à la place du modèle.
    scripts: bool  # l'alphabet écarte les pays qui ne l'écrivent pas
    letters: bool  # lettres et mots de rue propres à une langue
    places: bool  # noms de lieux (GeoNames)
    place_min_len: int = Field(ge=3, le=20)  # noms plus courts ignorés (sigles, mots courants)
    place_max_spread_km: float = Field(ge=50, le=3000)  # lieux d'une même manche : voisins, sinon homonymes lointains
    prior_min: float = Field(ge=0, le=1)  # un lieu seul est confirmé si StreetCLIP donne son pays à ce seuil
    detail: bool  # répertoire complet (villages) du pays en tête, téléchargé une fois par pays
    places_url: str = Field(pattern=r"^https://[^\s\"'<>]+$")
    detail_url: str = Field(pattern=r"^https://[^\s\"'<>{}]*\{\}[^\s\"'<>{}]*$")  # {} = code du pays
    regions_url: str = Field(pattern=r"^https://[^\s\"'<>]+$")  # noms des régions (verrou Région)
    places_dir: str

    @property
    def places_path(self) -> Path:
        return Path(self.places_dir).expanduser() if self.places_dir else DATA_DIR / "places"


class LocksConfig(BaseModel):
    # Verrous pays › région › ville (décidés avec l'utilisateur le 2026-11-07) : chaque niveau verrouillé restreint
    # la recherche du suivant. Le coach ne verrouille seul que le « certain » ; tu peux toujours rejeter (✕) ou
    # verrouiller toi-même. Ils durent une capture : une nouvelle capture remet tout à zéro.
    enabled: bool
    auto_country: bool  # le coach verrouille le pays quand les marques le rendent certain
    auto_region: bool  # … et la région quand la position estimée est nette et tombe dans une seule région
    propose_city: bool  # le coach PROPOSE une ville (un clic pour la verrouiller), jamais seul
    region_radius_km: float = Field(ge=1, le=100)  # lieux autour du point qui doivent tous être de la même région
    region_places_km: float = Field(ge=5, le=300)  # sans point : 2 lieux lus de la même région, à moins de ça


class StorageConfig(BaseModel):
    # Taille maximale des caches QUI GROSSISSENT (villages par pays, plus tard rues et Nominatim) ; le socle
    # (index GeoNames, Plonk It) ne part jamais tout seul. Réglages › Stockage : tailles et boutons « Vider ».
    max_cache_mb: int = Field(ge=50, le=100000)


class DebugConfig(BaseModel):
    # Mode débogage : journal JSON de chaque analyse à côté de sa capture, pour relire une manche après coup.
    enabled: bool


class Config(BaseModel):
    server: ServerConfig
    capture: CaptureConfig
    coach: CoachConfig
    dataset: DatasetConfig
    metas: MetasConfig
    plonkit: PlonkitConfig
    streetclip: StreetClipConfig
    plonk: PlonkConfig
    map: MapConfig
    vision: VisionConfig
    marks: MarksConfig
    rules: RulesConfig
    locks: LocksConfig
    storage: StorageConfig
    debug: DebugConfig


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
