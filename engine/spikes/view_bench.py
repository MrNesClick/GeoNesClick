"""Does the coach read the view better without the browser around it, and without the game's interface?

Three variants of every capture of the test set:
- window: what the coach receives today (the whole browser window; the Claude in Chrome artefacts are cut, see
  testset.py, so for those rounds part of the browser bar is gone too);
- page: the game page only, the browser's bars removed (the page top is found as a manual calibration would);
- page + masks: the page with GeoGuessr's interface blacked out (logo, compass, score, controls, mini-map,
  Google attribution).
For each: StreetCLIP right first, in the top 3, its "clear leader" from 70 % right or wrong; with --vision, the
vision model's conclusion on the window and on page + masks.

    cd engine && .venv/bin/python spikes/view_bench.py [--vision] [--sheet out.png]
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter

import numpy as np
from PIL import Image, ImageDraw

from geonesclick.config import load_config
from geonesclick.i18n import set_language
from geonesclick.streetclip import StreetClip
from geonesclick.vision import VisionClient, VisionError

import testset  # spikes/testset.py

# Page top in pixels, by browser layout: tabs + address + bookmarks bars (121), plus Chrome's debugging bar on the
# rounds played by Claude in Chrome (181), or that bar alone in full screen (60).
CHROME_ONLY, CHROME_AND_DEBUG, DEBUG_ONLY = 121, 181, 60
# GeoGuessr's interface, in fractions of the page [left, top, right, bottom].
UI = {
    "logo": (0.0, 0.0, 0.09, 0.05),
    "compass": (0.43, 0.0, 0.57, 0.05),
    "score": (0.76, 0.0, 1.0, 0.12),
    "controls": (0.0, 0.62, 0.07, 1.0),
    "minimap": (0.81, 0.70, 1.0, 1.0),
    "attribution": (0.0, 0.975, 1.0, 1.0),
}


def page_top(img: Image.Image, claude: bool) -> int:
    """Where the game page starts: the extension's orange border on Claude's rounds, the bookmarks bar otherwise."""
    if not claude:
        return CHROME_ONLY
    a = np.asarray(img.convert("RGB"), dtype=int)[:, 0]
    orange = (abs(a[:, 0] - 198) < 16) & (abs(a[:, 1] - 97) < 16) & (abs(a[:, 2] - 63) < 16)
    return int(np.argmax(orange)) if orange.any() else DEBUG_ONLY


def variants(item: dict) -> tuple[dict[str, Image.Image], tuple]:
    """The three variants, and the layout (window size, page top) they were cut with."""
    raw = Image.open(testset.DATASET / "images" / item["file"]).convert("RGB")
    claude = item.get("source") == "claude"
    w, h = raw.size
    top = page_top(raw, claude)
    edge = 4 if claude else 0  # the extension's border
    page = raw.crop((edge, top + edge, w - edge, h - edge))
    masked = page.copy()
    draw, (pw, ph) = ImageDraw.Draw(masked), page.size
    for l, t, r, b in UI.values():
        draw.rectangle((l * pw, t * ph, r * pw, b * ph), fill=(0, 0, 0))
    return {"window": testset.image(item), "page": page, "page + masks": masked}, (raw.size, top)


def conclusion(fiche: dict | None, known: set[str]) -> str:
    c = (fiche or {}).get("conclusion")
    country = str(c.get("country") or "").strip().upper() if isinstance(c, dict) else ""
    return country if country in known else ""


async def main(with_vision: bool, sheet: str | None) -> None:
    cfg = load_config()
    set_language(cfg.coach.language)
    clip = StreetClip(cfg.streetclip)
    labels = testset.labels()
    known = set(cfg.streetclip.countries.values())
    stats: dict[str, Counter] = {}
    examples = []
    vision = VisionClient(cfg.vision) if with_vision else None
    sem = asyncio.Semaphore(3)

    async def ask(img: Image.Image) -> str:
        async with sem:
            try:
                return conclusion((await vision.describe(img))[0], known)
            except VisionError:
                return "error"

    for item in labels:
        views, layout = variants(item)
        if layout not in {e[0] for e in examples}:  # one masked page per layout
            examples.append((layout, views["page + masks"]))
        truth = item["country"]
        for name, img in views.items():
            scores, _ = clip.predict(img)
            codes = [s.code for s in scores]
            s = stats.setdefault(name, Counter())
            s["first"] += codes[0] == truth
            s["top3"] += truth in codes[:3]
            s["prob"] += next((x.probability for x in scores if x.code == truth), 0.0)
            if scores[0].probability >= cfg.coach.leader_min:
                s["leader right" if codes[0] == truth else "leader WRONG"] += 1
        if vision:
            for name in ("window", "page + masks"):
                ai = await ask(views[name])
                s = stats[name]
                s["AI right" if ai == truth else "AI none" if not ai else "AI error" if ai == "error" else "AI WRONG"] += 1

    n = len(labels)
    print(f"Over {n} captures (leader from {cfg.coach.leader_min:.0%}):")
    for name, s in stats.items():
        line = (f"  {name:<13} first {s['first']}/{n}  top-3 {s['top3']}/{n}  mean prob. {s['prob'] / n:.0%}"
                f"  clear leader right/wrong {s['leader right']}/{s['leader WRONG']}")
        if vision:
            line += f"  | AI right/wrong/none {s['AI right']}/{s['AI WRONG']}/{s['AI none']} (errors {s['AI error']})"
        print(line)
    if sheet:  # the masked pages, to check that the masks fall on the interface
        tiles = [img.resize((640, int(640 * img.size[1] / img.size[0]))) for _, img in examples]
        out = Image.new("RGB", (1280, sum(t.size[1] for t in tiles[::2]) + 10 * len(tiles)), (255, 0, 255))
        y = 0
        for i in range(0, len(tiles), 2):
            for j, t in enumerate(tiles[i:i + 2]):
                out.paste(t, (j * 640, y))
            y += tiles[i].size[1] + 10
        out.save(sheet)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--vision", action="store_true", help="also ask the vision model (two calls per capture)")
    p.add_argument("--sheet", help="save a contact sheet of masked pages")
    args = p.parse_args()
    asyncio.run(main(args.vision, args.sheet))
