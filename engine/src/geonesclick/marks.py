"""Marques : indices que le joueur entoure sur la vue figée (panneau, plaque de rue, enseigne…).

Chaque marque est un élément de preuve : sa zone dans l'image brute, sa découpe agrandie si elle est petite,
et ce que le modèle de vision y a lu, mot pour mot. Le modèle transcrit seulement ; les conclusions viendront
des règles locales du coach, qui citeront les marques qui les justifient.
"""

from __future__ import annotations

import math
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field, field_validator

from .config import Rect, _check_rect

MAX_PER_ANALYSIS = 20  # numérotation ① à ⑳, toutes images figées confondues
MAX_LINES, MAX_CHARS = 30, 300  # une réponse démesurée du modèle est tronquée, jamais affichée en entier



class DeleteRequest(BaseModel):
    """Retirer une marque (lecture fausse, découpe ratée) : elle ne compte plus dans la conclusion."""

    id: str = Field(max_length=32)  # analyse
    n: int = Field(ge=1, le=1000)


def uses(scripts: bool, letters: bool, places: bool) -> tuple[list[str], list[str]]:
    """Ce que le coach tire d'une marque, et ce qu'il n'en tire pas (encore), selon les règles actives."""
    on = ["le texte, lu mot pour mot : panneaux, plaques de rue, enseignes, plaques d'immatriculation"]
    off = []
    for active, text in (
        (scripts, "l'alphabet, qui écarte les pays qui ne l'écrivent pas"),
        (letters, "les lettres et mots de rue propres à une langue (ъ, ő, ș, « utca »…)"),
        (places, "les noms de lieux (GeoNames, villages du pays en tête compris) : un lieu seul n'est qu'un indice, "
                 "il faut une autre preuve ; les noms de rue (Via…, Rue…) ne comptent pas"),
    ):
        (on if active else off).append(text + ("" if active else " (désactivé dans les réglages)"))
    off.append("poteaux, bornes, marquage au sol, végétation : décrits par l'IA, pas encore interprétés")
    return on, off


class MarksRequest(BaseModel):
    """Rectangles tracés sur une image figée, en fractions [gauche, haut, droite, bas] de l'image brute."""

    id: str = Field(max_length=32)  # image figée
    rects: list[Rect] = Field(min_length=1, max_length=MAX_PER_ANALYSIS)

    @field_validator("rects")
    @classmethod
    def _rects(cls, v: list[Rect]) -> list[Rect]:
        return [_check_rect(r, f"rects[{i}]") for i, r in enumerate(v)]


class FrameRequest(BaseModel):
    id: str = Field(max_length=32)


def crop_mark(frame: Image.Image, rect: Rect, upscale_to: int, max_upscale: float) -> tuple[Image.Image, float]:
    """Découpe la zone en pleine résolution, puis l'agrandit si son plus grand côté est sous upscale_to.

    Mesuré : un panneau de 140×130 px est lu déformé tel quel, exact une fois agrandi ×3.
    """
    w, h = frame.size
    left, top, right, bottom = rect
    box = (math.floor(left * w), math.floor(top * h), max(math.ceil(right * w), 1), max(math.ceil(bottom * h), 1))
    crop = frame.crop(box)
    longest = max(crop.size)
    scale = min(max_upscale, upscale_to / longest) if longest < upscale_to else 1.0
    if scale > 1.0:
        size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
        crop = crop.resize(size, Image.Resampling.LANCZOS)
    return crop, scale


def _text(value: Any, limit: int = MAX_CHARS) -> str:
    return str(value).strip()[:limit] if value is not None else ""


def reading(fiche: dict[str, Any]) -> dict[str, Any]:
    """Lecture d'une marque, dans une forme fixe quelle que soit la réponse du modèle."""
    raw = fiche.get("texte")
    lines = raw if isinstance(raw, list) else [raw] if isinstance(raw, str) else []
    text = [t for t in (_text(line) for line in lines[:MAX_LINES]) if t]
    unreadable = fiche.get("illisible")
    return {
        "text": text,
        "unreadable": unreadable is True or (isinstance(unreadable, str) and unreadable.lower() in ("true", "oui")),
        "object": _text(fiche.get("objet"), 120),
        "script": _text(fiche.get("alphabet"), 40),
    }
