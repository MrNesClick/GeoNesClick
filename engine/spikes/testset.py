"""The labelled test set as the benches read it (dataset/labels.toml and dataset/images/).

Rounds played by Claude in Chrome (source = "claude") carry what a player's capture never shows: Chrome's
"debugging" bar (French text, which StreetCLIP reads), the extension's "Claude is working here" badge and an orange
frame around the page. Where that bar sits depends on the browser layout (60 or 181 px from the top), and on some
captures a black band follows the frame at the bottom, so no fixed crop fits them all: the benches get the page inside
the frame, found on each image, with the badge blacked out. These rounds therefore have no browser bars at all, unlike
a player's whole window. Every capture first loses the black padding the engine trims at capture time (a window
resized during the sharing; capture.trim_padding), so the benches read what the engine reads. The files stay as
captured.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from geonesclick.capture import trim_padding

DATASET = Path(__file__).resolve().parent.parent / "dataset"
ORANGE = np.array([198, 97, 63])  # the extension's frame and badge
BADGE = (110, 47)  # half width and height of the badge, at the top centre of the page (Chrome at scale 1)
BADGE_ZONE = (300, 120)  # where the badge is looked for, grown by the page zoom: half width and height


def labels() -> list[dict]:
    return tomllib.loads((DATASET / "labels.toml").read_text())["capture"]


def is_claude(item: dict) -> bool:
    return item.get("source") == "claude"


def page_in_frame(img: Image.Image) -> tuple[int, int, int, int]:
    """The page inside the extension's orange frame (left, top, right, bottom), from its left edge. The frame is 3 px
    wide at page zoom 100 % and grows with the zoom, and a window resized during the sharing keeps a dark 1 px border:
    the width of both is measured on the image, plus one px of blending."""
    a = np.asarray(img.convert("RGB"), dtype=int)
    orange = (np.abs(a - ORANGE) < 20).all(axis=2)
    rows = np.flatnonzero(orange[:, 1])
    if rows.size == 0 or rows.size < 0.95 * (rows[-1] - rows[0] + 1):
        raise ValueError("no orange frame on the left edge of this capture")
    middle = a[(rows[0] + rows[-1]) // 2]
    edge = orange[(rows[0] + rows[-1]) // 2] | (middle.max(axis=1) <= 8)  # the frame, or the window's dark border
    frame = int(np.argmin(edge)) + 1  # those columns from the left edge, then one more for the blending
    return frame, int(rows[0]) + frame, img.width - frame, int(rows[-1]) + 1 - frame


def image(item: dict) -> Image.Image:
    """The capture of a label; for Claude's rounds, the page inside the frame with the badge blacked out."""
    img = trim_padding(Image.open(DATASET / "images" / item["file"]).convert("RGB"))
    if not is_claude(item):
        return img
    page = img.crop(page_in_frame(img))
    half, height = BADGE
    box = (page.width // 2 - half, 0, page.width // 2 + half, height)
    zone_half, zone_height = BADGE_ZONE
    left = page.width // 2 - zone_half
    zone = np.asarray(page.crop((left, 0, page.width // 2 + zone_half, zone_height)), dtype=int)
    ys, xs = np.nonzero((np.abs(zone - ORANGE) < 20).all(axis=2))
    if ys.size:  # the badge grows with the page zoom: black out what is found, at least the usual box
        box = (min(box[0], left + int(xs.min())), 0, max(box[2], left + int(xs.max()) + 1), max(box[3], int(ys.max()) + 2))
    ImageDraw.Draw(page).rectangle(box, fill=(0, 0, 0))
    return page
