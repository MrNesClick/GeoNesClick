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
HEADER = (
    "# Jeu de test étiqueté. Les images (dataset/images/) restent locales et ne sont pas versionnées.\n"
    "# Une entrée par capture : pays réel (ISO 3166-1 alpha-2), zone si connue, mode de jeu et mise en page.\n"
)


class DatasetError(ValueError):
    pass


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


def _toml_value(value: str | bool) -> str:
    # Une chaîne ou un booléen JSON est une valeur TOML valide (mêmes échappements, true/false).
    return json.dumps(value, ensure_ascii=False)


class Dataset:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.images = directory / "images"
        self.labels_file = directory / "labels.toml"
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
        )
        with self._lock:
            self.images.mkdir(parents=True, exist_ok=True)
            frame.save(self.images / label.file)
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
