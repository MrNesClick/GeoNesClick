"""Does the coach read the view better without the browser around it, and without the game's interface?

Three variants of every capture of the test set:
- window: what the coach receives today (the whole browser window; Claude in Chrome's rounds are the page alone,
  see testset.py, so this variant is a mix);
- page: the game page only, the browser's bars removed;
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

from PIL import Image, ImageDraw

from geonesclick.config import load_config
from geonesclick.i18n import set_language
from geonesclick.streetclip import StreetClip
from geonesclick.vision import VisionClient, VisionError

import testset  # spikes/testset.py

# Page top in pixels on a player's window: tabs, address and bookmarks bars (Chrome at scale 1).
CHROME_BARS = 121
# GeoGuessr's interface, in fractions of the page [left, top, right, bottom].
UI = {
    "logo": (0.0, 0.0, 0.09, 0.05),
    "compass": (0.43, 0.0, 0.57, 0.05),
    "score": (0.76, 0.0, 1.0, 0.12),
    "controls": (0.0, 0.62, 0.07, 1.0),
    "minimap": (0.81, 0.70, 1.0, 1.0),
    "attribution": (0.0, 0.975, 1.0, 1.0),
}


def variants(item: dict) -> tuple[dict[str, Image.Image], tuple]:
    """The three variants, and the layout (source, page size) they were cut with."""
    window = testset.image(item)
    # Claude's rounds are already the page alone (testset.py): their "window" and "page" are the same image.
    page = window if testset.is_claude(item) else window.crop((0, CHROME_BARS, window.width, window.height))
    masked = page.copy()
    draw, (pw, ph) = ImageDraw.Draw(masked), page.size
    for l, t, r, b in UI.values():
        draw.rectangle((l * pw, t * ph, r * pw, b * ph), fill=(0, 0, 0))
    return {"window": window, "page": page, "page + masks": masked}, (item.get("source", ""), page.size)


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
