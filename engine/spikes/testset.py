"""The labelled test set as the benches read it (dataset/labels.toml and dataset/images/).

Rounds played by Claude in Chrome (source = "claude") carry what a player's capture never shows: Chrome's
"debugging" bar (French text, which StreetCLIP reads), the extension's "Claude is working here" badge and an orange
frame around the page. Where that bar sits depends on the browser layout (60 or 181 px from the top), and on some
captures a black band follows the frame at the bottom, so no fixed crop fits them all: the benches get the page inside
the frame, found on each image, with the badge blacked out. These rounds therefore have no browser bars at all, unlike
a player's whole window. The files stay as captured.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

DATASET = Path(__file__).resolve().parent.parent / "dataset"
ORANGE = np.array([198, 97, 63])  # the extension's frame and badge
FRAME = 4  # the frame is 3 px wide, plus one px of blending
BADGE = (110, 47)  # half width and height of the badge, at the top centre of the page (Chrome at scale 1)


def labels() -> list[dict]:
    return tomllib.loads((DATASET / "labels.toml").read_text())["capture"]


def is_claude(item: dict) -> bool:
    return item.get("source") == "claude"


def page_in_frame(img: Image.Image) -> tuple[int, int, int, int]:
    """The page inside the extension's orange frame (left, top, right, bottom), from its left edge."""
    edge = np.asarray(img.convert("RGB"), dtype=int)[:, 1]
    rows = np.flatnonzero((np.abs(edge - ORANGE) < 20).all(axis=1))
    if rows.size == 0 or rows.size < 0.95 * (rows[-1] - rows[0] + 1):
        raise ValueError("no orange frame on the left edge of this capture")
    return FRAME, int(rows[0]) + FRAME, img.width - FRAME, int(rows[-1]) + 1 - FRAME


def image(item: dict) -> Image.Image:
    """The capture of a label; for Claude's rounds, the page inside the frame with the badge blacked out."""
    img = Image.open(DATASET / "images" / item["file"]).convert("RGB")
    if not is_claude(item):
        return img
    page = img.crop(page_in_frame(img))
    half, height = BADGE
    ImageDraw.Draw(page).rectangle((page.width // 2 - half, 0, page.width // 2 + half, height), fill=(0, 0, 0))
    return page
