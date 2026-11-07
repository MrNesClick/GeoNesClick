"""Jeu de test étiqueté : captures brutes (fenêtre entière) + pays réel, saisis depuis le coach.

Les images vont dans dataset/images/ (non versionnées), les étiquettes dans dataset/labels.toml.
On garde l'image BRUTE, avant recadrage et masques, pour pouvoir rejouer les expériences de recadrage.
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

CAPTURE_ID = re.compile(r"^\d{8}-\d{6}-\d{3}$")  # format produit par Engine.analyse()
# Coordonnées du vrai lieu dans un lien Google Maps (écran de fin de GeoGuessr) ou tapées « 54.65, 43.22 ».
# Le lien n'est JAMAIS ouvert : on lit seulement ses chiffres. Du plus précis au moins précis.
_LAT, _LON = r"(-?\d{1,2}(?:\.\d+)?)", r"(-?\d{1,3}(?:\.\d+)?)"
COORDS = [re.compile(p) for p in (
    rf"!3d{_LAT}!4d{_LON}",  # repère d'un lieu
    rf"[?&](?:cbll|viewpoint)={_LAT}(?:,|%2C){_LON}",  # position de la photo Street View
    rf"@{_LAT},{_LON}",  # position de la vue
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
    """(latitude, longitude) lues dans un lien Google Maps ou « lat, lon » ; None si absentes ou impossibles."""
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
    found: bool | None = None  # le joueur avait-il trouvé le pays ?
    predicted: str = ""  # premier pays proposé par StreetCLIP au moment de la capture
    guessed: str = ""  # pays répondu par le joueur ; s'il est connu, « found » en découle
    lat: float | None = None  # vrai lieu (lien Google Maps de l'écran de fin) : le banc mesure l'erreur en km
    lon: float | None = None
    region: str = ""  # code GeoNames de sa région (« RU.46 »), déduit de la position


def _toml_value(value: str | bool | float) -> str:
    # Une chaîne, un nombre ou un booléen JSON est une valeur TOML valide (mêmes échappements, true/false).
    return json.dumps(value, ensure_ascii=False)


class Dataset:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.images = directory / "images"
        self.labels_file = directory / "labels.toml"
        self.rounds = directory / "rounds"  # une manche par fichier : marques lues, conclusion, choix du joueur
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
        """Enregistre (ou ré-étiquette) une capture. Lève DatasetError si l'identifiant est invalide."""
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
            if round_data is not None:  # ce que le coach avait lu et conclu : le corpus du banc (bench.py)
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
    country: str  # pays réel
    guessed: str  # pays répondu à la place
    count: int


@dataclass
class Progress:
    """Ta progression, calculée sur les captures étiquetées où tu as indiqué si tu avais trouvé."""

    rounds: int
    found: int
    by_country: dict[str, tuple[int, int]]  # pays → (manches, trouvées)
    model_top1: int  # manches où StreetCLIP avait mis le bon pays en premier
    model_rounds: int
    confusions: list[Confusion] = field(default_factory=list)  # les plus fréquentes d'abord


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
