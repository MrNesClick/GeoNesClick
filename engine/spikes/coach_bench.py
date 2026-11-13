"""What the coach answers at level 4, without marks, against the true country of the test set.

Same code and settings as the engine (crop and masks, StreetCLIP, the vision model's sheet of the whole view, the
leader thresholds), on every capture of dataset/labels.toml. Without marks, no local rule confirms a reading: the
coach is never "certain" (app/src/engine.ts, certainProof); the country it puts first is the AI's conclusion, as
"very likely". The bench counts:
- StreetCLIP: right first, and its "clear leader" (leader_min / leader_margin) right or wrong;
- the AI's conclusion: right, wrong or absent, by the certainty it claims; "strong" but wrong is what the coach
  must never turn into a certainty (it does not, without a local rule);
- when the AI and StreetCLIP agree, how often they are right.

Sends each capture to the configured vision model (NVIDIA), as the coach does at each capture.

    cd engine && .venv/bin/python spikes/coach_bench.py [--json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter

from PIL import Image

from geonesclick.capture import apply_crop_and_masks
from geonesclick.config import load_config
from geonesclick.i18n import set_language
from geonesclick.streetclip import StreetClip
from geonesclick.vision import VisionClient, VisionError

import testset  # spikes/testset.py: labels and images, Claude in Chrome artefacts cropped out



def conclusion(fiche: dict, known: set[str]) -> tuple[str, str]:
    """(country, certainty) of the sheet's conclusion, as engine.ts conclusionOf reads it; ("", "") if none."""
    c = fiche.get("conclusion")
    if not isinstance(c, dict):
        return "", ""
    country = str(c.get("country") or "").strip().upper()
    certainty = str(c.get("certainty") or "").strip().lower()
    return (country, certainty) if country in known else ("", "")


async def main(as_json: bool) -> None:
    cfg = load_config()
    set_language(cfg.coach.language)
    clip, vision = StreetClip(cfg.streetclip), VisionClient(cfg.vision)
    if not vision.ready:
        raise SystemExit("No NVIDIA API key: the vision model cannot be asked.")
    known = set(cfg.streetclip.countries.values())
    labels = testset.labels()
    sem = asyncio.Semaphore(3)  # free tier rate limit

    async def ask(view: Image.Image) -> tuple[dict | None, str]:
        async with sem:
            try:
                return (await vision.describe(view))[0], ""
            except VisionError as exc:
                return None, str(exc)

    views = [apply_crop_and_masks(testset.image(item),
                                  cfg.capture.crop, cfg.capture.masks) for item in labels]
    sheets = await asyncio.gather(*(ask(v) for v in views))
    rows = []
    for item, view, (fiche, error) in zip(labels, views, sheets, strict=True):
        scores, _ = clip.predict(view)
        first, second = scores[0], scores[1] if len(scores) > 1 else None
        clear = first.probability >= cfg.coach.leader_min and \
            first.probability - (second.probability if second else 0) >= cfg.coach.leader_margin
        ai, certainty = conclusion(fiche, known) if fiche else ("", "")
        rows.append({"file": item["file"], "truth": item["country"], "clip": first.code,
                     "clip_p": round(first.probability, 2), "clear": clear, "ai": ai, "certainty": certainty,
                     "error": error})

    n = len(rows)
    count = lambda pred: sum(1 for r in rows if pred(r))  # noqa: E731
    summary = {
        "captures": n,
        "StreetCLIP first right": count(lambda r: r["clip"] == r["truth"]),
        "StreetCLIP clear leader right/wrong": f"{count(lambda r: r['clear'] and r['clip'] == r['truth'])}"
                                                f"/{count(lambda r: r['clear'] and r['clip'] != r['truth'])}",
        "AI conclusion right/wrong/none": f"{count(lambda r: r['ai'] and r['ai'] == r['truth'])}"
                                           f"/{count(lambda r: r['ai'] and r['ai'] != r['truth'])}"
                                           f"/{count(lambda r: not r['ai'])}",
        "AI 'strong' right/wrong": f"{count(lambda r: r['certainty'] == 'strong' and r['ai'] == r['truth'])}"
                                    f"/{count(lambda r: r['certainty'] == 'strong' and r['ai'] and r['ai'] != r['truth'])}",
        "AI and StreetCLIP agree, right/wrong": f"{count(lambda r: r['ai'] == r['clip'] == r['truth'])}"
                                                 f"/{count(lambda r: r['ai'] and r['ai'] == r['clip'] != r['truth'])}",
        "vision errors": count(lambda r: r["error"]),
        "certainties claimed": dict(Counter(r["certainty"] or "-" for r in rows)),
    }
    if as_json:
        print(json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=1))
        return
    for r in rows:
        mark = lambda code: "ok" if code == r["truth"] else "--" if not code else "XX"  # noqa: E731
        print(f"{r['file']}  {r['truth']}  StreetCLIP {r['clip']} {r['clip_p']:.0%} {mark(r['clip'])}"
              f"{' (clear)' if r['clear'] else ''}  |  AI {r['ai'] or '-'} {r['certainty'] or ''} {mark(r['ai'])}"
              f"{'  ERROR ' + r['error'][:60] if r['error'] else ''}")
    print()
    for key, value in summary.items():
        print(f"{key:<38} {value}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    asyncio.run(main(p.parse_args().json))
