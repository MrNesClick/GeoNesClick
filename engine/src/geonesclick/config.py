"""Configuration: the package's default values, overridden by the user file."""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator

from .metas import CATEGORIES
from .paths import CONFIG_DIR, DATA_DIR  # a single place for the app's folders
from .plonkit import DATA_DIR as PLONKIT_DATA_DIR

USER_CONFIG = CONFIG_DIR / "config.toml"
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # engine/src/geonesclick → repository root

Rect = list[float]


def _check_rect(rect: Rect, name: str) -> Rect:
    """Rectangle as fractions [left, top, right, bottom], with 0 ≤ left < right ≤ 1 (same for the height)."""
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
        return _check_rect(v, "capture.crop") if v else v  # empty list = whole image

    @field_validator("masks")
    @classmethod
    def _masks(cls, v: list[Rect]) -> list[Rect]:
        return [_check_rect(m, f"capture.masks[{i}]") for i, m in enumerate(v)]

    @property
    def path(self) -> Path:
        return Path(self.directory).expanduser() if self.directory else DATA_DIR / "captures"


class CoachConfig(BaseModel):
    # What is shown without a click: 1 where to look, 2 + what the AI sees, 3 + likely countries and clues,
    # 4 + synthesis of the answer (country, region if a text names it, proof).
    help_level: int = Field(ge=1, le=4)
    # A proof read by the AI with strong certainty (text naming a place…) puts that country first and
    # rules out the others, instead of StreetCLIP's percentages alone.
    trust_proof: bool
    # The coach's language: the whole UI in en and fr (i18n.UI_LANGUAGES); es, de, it, pt translate the tips only.
    language: Literal["en", "fr", "es", "de", "it", "pt"]
    # A country is shown as the answer only if it stands out: at least leader_min, and a leader_margin lead
    # over the 2nd. Otherwise the coach talks of hesitation between the first ones, instead of a false winner.
    leader_min: float = Field(ge=0, le=1)
    leader_margin: float = Field(ge=0, le=1)


class DatasetConfig(BaseModel):
    enabled: bool
    directory: str
    ask_guessed: bool  # ask for the answered country (otherwise: "Had you found it?" Yes / No)
    max_confusions: int = Field(ge=0, le=10)  # 0 = confusions hidden

    @property
    def path(self) -> Path:
        return Path(self.directory).expanduser() if self.directory else DATA_DIR / "dataset"


class MetasConfig(BaseModel):
    enabled: bool
    include_seed: bool
    user_file: str
    min_probability: float = Field(ge=0, le=1)
    max_candidates: int = Field(ge=2, le=20)
    max_categories: int = Field(ge=1, le=12)
    show_looks: bool  # "Look…" instructions before revealing the countries
    max_looks: int = Field(ge=1, le=5)
    judge_buttons: bool  # "Right" / "Wrong" buttons on the seed clues
    category_looks: dict[str, str] = {}  # replaces a category's default instruction
    category_weights: dict[str, float] = {}  # replaces a category's weight in the tie-break

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
    enabled: bool  # collect and use the Plonk It guides (local database, never redistributed)
    data_dir: str  # empty = ~/.local/share/geonesclick/plonkit
    refresh_days: int = Field(ge=1, le=365)  # check the list of guides at most every N days
    delay_s: float = Field(ge=1.0, le=60.0)  # pause between two pages during a collection
    similar_tips: bool  # "the tips that look like your view", for each candidate country
    similar_per_country: int = Field(ge=1, le=5)
    keywords: dict[str, list[str]] = {}  # replaces a category's ranking keywords
    ai_classify: bool  # have the AI classify the tips left without a category (once per text)
    ai_model: str = Field(max_length=120, pattern=r"^$|^[\w.\-]+/[\w.\-]+$")  # empty = the level 2 model
    ai_batch: int = Field(ge=5, le=50)  # tips per call
    ai_pause_s: float = Field(ge=0.0, le=60.0)  # pause between two calls (free tier limits)
    translate: bool  # translate the displayed tips into the coach's language (on demand, cached)
    translate_timeout_s: float = Field(ge=5.0, le=120.0)  # beyond this, the batch stays in English (no new attempt)
    pretranslate: bool  # translate the whole database ahead of time in the background, after the running analyses

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
    model: str = Field(pattern=r"^[\w.\-]+/[\w.\-]+$")
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")  # pinned version of the weights (safetensors): the one measured
    device: str = Field(pattern=r"^(auto|cpu|cuda(:\d+)?)$")
    prompt: str = Field(min_length=5, max_length=300)
    top_k: int = Field(ge=1, le=20)
    countries: dict[str, str]  # English name (prompt) → 2-letter ISO code
    exclude_countries: list[str] = []  # codes removed from the list (merging the files can only add)
    _all_countries: dict[str, str] = PrivateAttr(default_factory=dict)  # before exclusion (Settings screen)

    @field_validator("prompt")
    @classmethod
    def _placeholder(cls, v: str) -> str:
        # Passed to str.format: a single {} brace and no other (no named field, no giant width).
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
    # Cloud of likely positions for the map (PLONK on StreetCLIP's vector), never a country vote.
    enabled: bool
    model: str = Field(pattern=r"^[\w.\-]+/[\w.\-]+$")
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")  # Hugging Face commit of the weights: measured version, pinned
    steps: int = Field(ge=10, le=250)  # flow steps: 50 are enough (measured), 25 degrade the cloud
    points: int = Field(ge=64, le=2048)
    zone_share: float = Field(gt=0.2, le=1.0)  # share of the points (the densest) that the zones enclose
    zone_link_km: float = Field(ge=20, le=1000)  # two points closer than this are in the same zone
    zone_min_part: float = Field(ge=0.01, le=0.5)  # minimum share of the points for a zone to be shown


class MapConfig(BaseModel):
    # Coach's map (level 3 and up): likely countries, PLONK cloud. Online map background.
    enabled: bool
    # Tile server. Another server must ALSO be allowed in the CSP (img-src) of
    # app/src-tauri/tauri.conf.json; otherwise its tiles are blocked.
    tile_url: str = Field(pattern=r"^https://[^\s\"'<>]+\{z\}[^\s\"'<>]*$")
    attribution: str = Field(min_length=1, max_length=200)  # plain text, always shown on the map
    attribution_url: str = Field(pattern=r"^https://[^\s\"'<>]+$")
    tile_filter: str = Field(max_length=200, pattern=r"^[a-z0-9().%,\s-]*$")  # CSS filter for the tiles (dark theme)
    # Up close (streets, villages), colour inversion becomes unreadable: another filter from close_zoom on.
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
    max_side_px: int = Field(ge=256, le=4096)  # beyond this, the request gets heavy with no measured gain
    prompt: str = Field(min_length=20, max_length=20000)


class MarksConfig(BaseModel):
    # Marks: on the frozen view, the player circles clues (sign, plate…); each is cropped from
    # the raw image, enlarged if small, then transcribed by the vision model.
    enabled: bool
    max_marks: int = Field(ge=1, le=20)  # marks per frozen image (numbered ① to ⑳)
    # Enlargement: the longest side of the crop is brought to upscale_to_px, without exceeding max_upscale.
    upscale_to_px: int = Field(ge=64, le=2048)
    max_upscale: float = Field(ge=1.0, le=8.0)
    parallel: int = Field(ge=1, le=8)  # simultaneous readings (API limits)
    model: str = Field(max_length=120, pattern=r"^$|^[\w.\-]+/[\w.\-]+$")  # empty = the level 2 model
    max_tokens: int = Field(ge=50, le=4000)
    prompt: str = Field(min_length=20, max_length=5000)


class RulesConfig(BaseModel):
    # Local rules applied to the text of the marks (evidence.py): they conclude instead of the model.
    scripts: bool  # the alphabet rules out the countries that do not write it
    letters: bool  # letters and street words specific to a language
    places: bool  # place names (GeoNames)
    place_min_len: int = Field(ge=3, le=20)  # shorter names ignored (acronyms, common words)
    place_max_spread_km: float = Field(ge=50, le=3000)  # a round's places are neighbours; else distant namesakes
    prior_min: float = Field(ge=0, le=1)  # a lone place is confirmed if StreetCLIP gives its country at this threshold
    detail: bool  # full directory (villages) of the leading country, downloaded once per country
    places_url: str = Field(pattern=r"^https://[^\s\"'<>]+$")
    detail_url: str = Field(pattern=r"^https://[^\s\"'<>{}]*\{\}[^\s\"'<>{}]*$")  # {} = country code
    regions_url: str = Field(pattern=r"^https://[^\s\"'<>]+$")  # region names (Region lock)
    places_dir: str

    @property
    def places_path(self) -> Path:
        return Path(self.places_dir).expanduser() if self.places_dir else DATA_DIR / "places"


class LocksConfig(BaseModel):
    # Country › region › city locks (decided with the user on 2026-11-07): each locked level narrows down
    # the search of the next one. The coach locks on its own only what is "certain"; you can always reject (✕) or
    # lock yourself. They last one capture: a new capture resets everything.
    enabled: bool
    auto_country: bool  # the coach locks the country when the marks make it certain
    auto_region: bool  # … and the region when the estimated position is sharp and falls in a single region
    propose_city: bool  # the coach SUGGESTS a city (one click to lock it), never on its own
    region_radius_km: float = Field(ge=1, le=100)  # places around the point that must all be in the same region
    region_places_km: float = Field(ge=5, le=300)  # no point: 2 places read in one region, closer than this


class StorageConfig(BaseModel):
    # Maximum size of the caches THAT GROW (villages per country, later streets and Nominatim); the base
    # (GeoNames index, Plonk It) never goes on its own. Settings › Storage: sizes and "Empty" buttons.
    max_cache_mb: int = Field(ge=50, le=100000)


class DebugConfig(BaseModel):
    # Debug mode: JSON log of each analysis next to its capture, to replay a round afterwards.
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
    """Recursive merge: tables are merged, other values replaced."""
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
    """API key: environment variable, otherwise the protected file ~/.config/geonesclick/<name>.key (apikey.py)."""
    from .apikey import read

    return read(name)
