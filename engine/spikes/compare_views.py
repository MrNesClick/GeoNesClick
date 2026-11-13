"""Experiment: what do we gain by cropping the view and masking the game's UI?

Compares three variants on the labelled test set (dataset/labels.toml):
  window   the whole browser window
  frame    the Street View view alone (without the browser bar)
  masks    the view, with the GeoGuessr UI masked (logo, compass, scores, buttons, mini-map)
Measures, for each variant: rank and probability of the right country according to StreetCLIP, and for the
vision model, the country names copied from the image (mini-map leak).

Usage: .venv/bin/python spikes/compare_views.py [--no-vision]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # StreetCLIP already cached: no network call

from geonesclick.capture import apply_crop_and_masks  # noqa: E402
from geonesclick.config import load_config  # noqa: E402
from geonesclick.streetclip import StreetClip  # noqa: E402
from geonesclick.vision import VisionClient, VisionError  # noqa: E402

import testset  # spikes/testset.py: labels and images, Claude in Chrome artefacts cropped out


# Layout "classic game, 1920x1200 browser window", measured on the captures.
CROP = [0.0, 122 / 1200, 1.0, 1.0]
MASKS = [
    [0.00, 0.00, 0.08, 0.05],   # logo
    [0.42, 0.00, 0.58, 0.05],   # compass
    [0.76, 0.00, 1.00, 0.14],   # scores
    [0.00, 0.15, 0.05, 0.96],   # buttons
    [0.80, 0.69, 1.00, 1.00],   # mini-map + "placez votre épingle" (place your pin) button
    [0.00, 0.975, 1.00, 1.00],  # Google banner at the bottom
]
VARIANTS = {"window": ([], []), "frame": (CROP, []), "masks": (CROP, MASKS)}

# Country names visible on the game's mini-map (data: the captures were taken with GeoGuessr in French) and their
# English equivalents.
MAP_NAMES = ["Norvège", "Finlande", "Suède", "Pologne", "Ukraine", "Roumanie", "France", "Allemagne",
             "Royaume-Uni", "Autriche", "Espagne", "Italie", "Norway", "Finland", "Sweden", "Poland",
             "Romania", "Germany", "Lettonie", "Lituanie", "Serbie", "Latvia", "Lithuania", "Serbia"]


def leaked_names(fiche: dict) -> list[str]:
    text = json.dumps(fiche, ensure_ascii=False)
    return sorted({n for n in MAP_NAMES if re.search(rf"\b{re.escape(n)}\b", text, re.IGNORECASE)})


async def main(with_vision: bool) -> None:
    labels = testset.labels()
    cfg = load_config()
    clip = StreetClip(cfg.streetclip.model_copy(update={"top_k": 20}))  # rank of the right country, up to 20
    vision = VisionClient(cfg.vision) if with_vision else None
    code_to_name = {v: k for k, v in cfg.streetclip.countries.items()}
    sem = asyncio.Semaphore(3)  # free tier rate limit

    async def describe(img):
        async with sem:
            try:
                fiche, s = await vision.describe(img)
                return fiche, s, None
            except VisionError as exc:
                return None, 0, str(exc)

    summary = {v: {"top1": 0, "top3": 0, "proba": 0.0, "fuites": 0} for v in VARIANTS}
    for item in labels:
        frame = testset.image(item)
        truth = item["country"]
        print(f"\n=== {item['file']}  →  {code_to_name.get(truth, truth)} ({truth})")
        # Claude's rounds are already the page alone (testset.py): only a player's window loses its browser bars.
        views = {name: apply_crop_and_masks(frame, [] if testset.is_claude(item) else c, m)
                 for name, (c, m) in VARIANTS.items()}
        tasks = {name: asyncio.create_task(describe(img)) for name, img in views.items()} if vision else {}
        for name, img in views.items():
            scores, _ = clip.predict(img)
            codes = [s.code for s in scores]
            rank = codes.index(truth) + 1 if truth in codes else None
            proba = next((s.probability for s in scores if s.code == truth), 0.0)
            summary[name]["top1"] += rank == 1
            summary[name]["top3"] += rank is not None and rank <= 3
            summary[name]["proba"] += proba
            top = ", ".join(f"{s.code} {s.probability:.0%}" for s in scores[:3])
            line = f"  {name:<8} StreetCLIP rank {rank or '>20'}  ({proba:.0%})  top: {top}"
            if vision:
                fiche, secs, err = await tasks[name]
                if err:
                    line += f"  | vision: ERROR {err[:60]}"
                else:
                    leaks = leaked_names(fiche)
                    summary[name]["fuites"] += bool(leaks)
                    line += f"  | vision {secs:4.1f} s, country names copied: {', '.join(leaks) or 'none'}"
            print(line)

    n = len(labels)
    print(f"\n=== Summary over {n} captures")
    print(f"  {'variant':<8} {'top-1':>6} {'top-3':>6} {'mean prob.':>11} {'leaks':>7}")
    for name, s in summary.items():
        fuites = f"{s['fuites']}/{n}" if with_vision else "-"
        print(f"  {name:<8} {s['top1']:>4}/{n} {s['top3']:>4}/{n} {s['proba'] / n:>10.0%} {fuites:>7}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--no-vision", action="store_true", help="StreetCLIP only (no network call)")
    sys.exit(asyncio.run(main(not p.parse_args().no_vision)))
