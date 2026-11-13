"""The labelled test set as the benches read it (dataset/labels.toml and dataset/images/).

Rounds played by Claude in Chrome (source = "claude") carry what a player's capture never shows: Chrome's
"debugging" bar (French text, which StreetCLIP reads), the extension's "Claude is working here" badge and an orange
border. The benches see them cropped out (CLAUDE_CROP, fractions [left, top, right, bottom]); the files stay as
captured.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from PIL import Image

DATASET = Path(__file__).resolve().parent.parent / "dataset"
CLAUDE_CROP = (0.01, 0.10, 0.99, 0.99)


def labels() -> list[dict]:
    return tomllib.loads((DATASET / "labels.toml").read_text())["capture"]


def image(item: dict) -> Image.Image:
    """The capture of a label, without the Claude in Chrome artefacts when it has them."""
    img = Image.open(DATASET / "images" / item["file"]).convert("RGB")
    if item.get("source") == "claude":
        w, h = img.size
        l, t, r, b = CLAUDE_CROP
        img = img.crop((int(l * w), int(t * h), int(r * w), int(b * h)))
    return img
