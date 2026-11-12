"""Marks: clues the player circles on the frozen view (road sign, street sign, shop sign…).

Each mark is a piece of evidence: its zone in the raw image, its crop enlarged if small,
and what the vision model read there, word for word. The model only transcribes; the conclusions will come
from the coach's local rules, which will cite the marks that justify them.
"""

from __future__ import annotations

import math
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field, field_validator

from .i18n import t
from .config import Rect, _check_rect

MAX_PER_ANALYSIS = 20  # numbering ① to ⑳, across all frozen images
MAX_LINES, MAX_CHARS = 30, 300  # an oversized model response is truncated, never shown in full



class DeleteRequest(BaseModel):
    """Remove a mark (wrong reading, failed crop): it no longer counts in the conclusion."""

    id: str = Field(max_length=32)  # analysis
    n: int = Field(ge=1, le=1000)


def uses(scripts: bool, letters: bool, places: bool) -> tuple[list[str], list[str]]:
    """What the coach draws from a mark, and what it does not draw (yet), according to the active rules."""
    on = [t("marks.uses.text")]
    off = []
    for active, key in ((scripts, "marks.uses.scripts"), (letters, "marks.uses.letters"), (places, "marks.uses.places")):
        (on if active else off).append(t(key) + ("" if active else t("marks.uses.off_suffix")))
    off.append(t("marks.uses.not_yet"))
    return on, off


class MarksRequest(BaseModel):
    """Rectangles drawn on a frozen image, as fractions [left, top, right, bottom] of the raw image."""

    id: str = Field(max_length=32)  # frozen image
    rects: list[Rect] = Field(min_length=1, max_length=MAX_PER_ANALYSIS)

    @field_validator("rects")
    @classmethod
    def _rects(cls, v: list[Rect]) -> list[Rect]:
        return [_check_rect(r, f"rects[{i}]") for i, r in enumerate(v)]


class FrameRequest(BaseModel):
    id: str = Field(max_length=32)


def crop_mark(frame: Image.Image, rect: Rect, upscale_to: int, max_upscale: float) -> tuple[Image.Image, float]:
    """Crops the zone at full resolution, then enlarges it if its longest side is below upscale_to.

    Measured: a 140×130 px sign is read distorted as is, exact once enlarged ×3.
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
    """Reading of a mark, in a fixed shape whatever the model's response."""
    raw = fiche.get("text")
    lines = raw if isinstance(raw, list) else [raw] if isinstance(raw, str) else []
    text = [line for line in (_text(line) for line in lines[:MAX_LINES]) if line]
    unreadable = fiche.get("unreadable")
    return {
        "text": text,
        "unreadable": unreadable is True or (isinstance(unreadable, str) and unreadable.lower() == "true"),
        "object": _text(fiche.get("object"), 120),
        "script": _text(fiche.get("script"), 40).lower(),
    }
