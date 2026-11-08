"""Labelled test set: raw captures (whole window) + real country, entered from the coach.

The images go to dataset/images/ (not versioned), the labels to dataset/labels.toml.
The RAW image is kept, before cropping and masks, so that the cropping experiments can be replayed.
"""

from __future__ import annotations

import json
import re
import threading
import tomllib
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image

CAPTURE_ID = re.compile(r"^\d{8}-\d{6}-\d{3}$")  # format produced by Engine.analyse()
# Coordinates of the true place in a Google Maps link (GeoGuessr end screen) or typed as "54.65, 43.22".
# The link is NEVER opened: only its digits are read. From most to least precise.
_LAT, _LON = r"(-?\d{1,2}(?:\.\d+)?)", r"(-?\d{1,3}(?:\.\d+)?)"
COORDS = [re.compile(p) for p in (
    rf"!3d{_LAT}!4d{_LON}",  # marker of a place
    rf"[?&](?:cbll|viewpoint)={_LAT}(?:,|%2C){_LON}",  # position of the Street View photo
    rf"@{_LAT},{_LON}",  # position of the view
    rf"[?&](?:q|query|ll)={_LAT}(?:,|%2C)\s*{_LON}",
    rf"^\s*{_LAT}\s*[,;]\s*{_LON}\s*$",
)]
HEADER = (
    "# Jeu de test étiqueté. Les images (dataset/images/) restent locales et ne sont pas versionnées.\n"
    "# Une entrée par capture : pays réel (ISO 3166-1 alpha-2), zone si connue, mode de jeu et mise en page.\n"
)


class DatasetError(ValueError):
    pass


def coords_of(text: str) -> tuple[float, float] | None:
    """(latitude, longitude) read from a Google Maps link or "lat, lon"; None if missing or impossible."""
    for pattern in COORDS:
        found = pattern.search(text.strip())
        if found:
            lat, lon = float(found.group(1)), float(found.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0.0, 0.0):
                return lat, lon
    return None


@dataclass
class Label:
    file: str
    country: str
    area: str = ""
    mode: str = "classique"
    layout: str = ""
    found: bool | None = None  # had the player found the country?
    predicted: str = ""  # first country suggested by StreetCLIP at capture time
    guessed: str = ""  # country answered by the player; if known, "found" follows from it
    lat: float | None = None  # true place (Google Maps link from the end screen): the bench measures the error in km
    lon: float | None = None
    region: str = ""  # GeoNames code of its region ("RU.46"), derived from the position


def _toml_value(value: str | bool | float) -> str:
    # A JSON string, number or boolean is a valid TOML value (same escapes, true/false).
    return json.dumps(value, ensure_ascii=False)


class Dataset:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.images = directory / "images"
        self.labels_file = directory / "labels.toml"
        self.rounds = directory / "rounds"  # one round per file: marks read, conclusion, player's choices
        self._lock = threading.Lock()

    def labels(self) -> list[Label]:
        if not self.labels_file.exists():
            return []
        return [Label(**entry) for entry in tomllib.loads(self.labels_file.read_text()).get("capture", [])]

    def add(
        self,
        capture_id: str,
        frame: Image.Image,
        country: str,
        *,
        found: bool | None = None,
        predicted: str = "",
        guessed: str = "",
        area: str = "",
        mode: str = "classique",
        lat: float | None = None,
        lon: float | None = None,
        region: str = "",
        round_data: dict | None = None,
    ) -> Label:
        """Saves (or relabels) a capture. Raises DatasetError if the identifier is invalid."""
        if not CAPTURE_ID.fullmatch(capture_id):
            raise DatasetError("identifiant de capture invalide")
        if guessed:
            found = guessed == country
        label = Label(
            file=f"capture-{capture_id}.png",
            country=country,
            area=area.strip()[:200],
            mode=mode,
            layout=f"fenêtre {frame.width}x{frame.height}",
            found=found,
            predicted=predicted,
            guessed=guessed,
            lat=round(lat, 6) if lat is not None else None,
            lon=round(lon, 6) if lon is not None else None,
            region=region,
        )
        with self._lock:
            self.images.mkdir(parents=True, exist_ok=True)
            frame.save(self.images / label.file)
            if round_data is not None:  # what the coach had read and concluded: the bench's corpus (bench.py)
                self.rounds.mkdir(parents=True, exist_ok=True)
                (self.rounds / f"{capture_id}.json").write_text(json.dumps(round_data, ensure_ascii=False, indent=1))
            entries = [e for e in self.labels() if e.file != label.file] + [label]
            blocks = [
                "[[capture]]\n"
                + "".join(f"{k} = {_toml_value(v)}\n" for k, v in asdict(e).items() if v not in (None, ""))
                for e in entries
            ]
            self.labels_file.write_text(HEADER + "\n" + "\n".join(blocks))
        return label


@dataclass
class Confusion:
    country: str  # real country
    guessed: str  # country answered instead
    count: int


@dataclass
class Progress:
    """Your progress, computed on the labelled captures where you said whether you had found it."""

    rounds: int
    found: int
    by_country: dict[str, tuple[int, int]]  # country → (rounds, found)
    model_top1: int  # rounds where StreetCLIP had put the right country first
    model_rounds: int
    confusions: list[Confusion] = field(default_factory=list)  # most frequent first


def progress(labels: list[Label]) -> Progress:
    answered = [lb for lb in labels if lb.found is not None]
    by_country: dict[str, tuple[int, int]] = {}
    for lb in answered:
        n, ok = by_country.get(lb.country, (0, 0))
        by_country[lb.country] = (n + 1, ok + bool(lb.found))
    with_model = [lb for lb in labels if lb.predicted]
    return Progress(
        rounds=len(answered),
        found=sum(bool(lb.found) for lb in answered),
        by_country=by_country,
        model_top1=sum(lb.predicted == lb.country for lb in with_model),
        model_rounds=len(with_model),
        confusions=[
            Confusion(country, guessed, n)
            for (country, guessed), n in Counter(
                (lb.country, lb.guessed) for lb in labels if lb.guessed and lb.guessed != lb.country
            ).most_common()
        ],
    )
