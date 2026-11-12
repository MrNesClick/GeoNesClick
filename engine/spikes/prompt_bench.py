"""Prompt bench: the 0.1 French prompts against the English ones (answers in English, in French).

    .venv/bin/python spikes/prompt_bench.py [--repeats 3] [--out results.json] [--only 162401-349 ...]

Uses your NVIDIA key and your local captures (~/.local/share/geonesclick). Two measures:
- vision (whole view): valid JSON, no false conclusion, driving side, words of the visible sign that are read;
- marks (enlarged crop): words of the sign read exactly (accents included), invented words, and on an unreadable
  crop, whether the model admits it instead of making text up.
The reference words were read by eye on each image; on a full view, a small sign may be unreadable for everyone:
the comparison between prompts is what counts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import tomllib
import unicodedata
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from geonesclick.config import load_config  # noqa: E402
from geonesclick.paths import DATA_DIR  # noqa: E402
from geonesclick.vision import VisionClient, VisionError  # noqa: E402

CAPTURES = DATA_DIR / "captures"
DATASET = DATA_DIR / "dataset" / "images"

# Whole views: (file, real country, words of a sign visible in the view).
VIEWS = [
    (DATASET / "capture-20261107-080023-137.png", "LV", []),
    (DATASET / "capture-20261107-080103-604.png", "RS", []),
    (DATASET / "capture-20261107-080120-934.png", "SE", []),
    (DATASET / "capture-20261107-080139-261.png", "NO", []),
    (DATASET / "capture-20261107-080158-646.png", "LT", []),
    (CAPTURES / "capture-20261107-162401-349.png", "BG", ["Гърмен", "Гоце", "Делчев", "Благоевград", "София"]),
    (CAPTURES / "capture-20261107-171805-069.png", "FR", ["HOPITAL", "ORION", "SAUVETERRE", "BÉARN", "ORTHEZ"]),
    (CAPTURES / "capture-20261107-172730-962.png", "IT", ["università", "VIA", "PAOLO", "MANTO"]),
    (CAPTURES / "capture-20261107-185135-509.png", "CZ", ["BOŠOV", "LIBKOVICE", "JEŘEN"]),
    (CAPTURES / "capture-20261107-190119-944.png", "DE", ["Kleine", "Oker", "Waldschwimmbad", "Tennisplätze",
                                                          "Okerteich"]),
    (CAPTURES / "capture-20261107-190950-641.png", "RU", ["САРАНСК", "SARANSK", "СТАРЫЙ", "ГОРОД"]),
    (CAPTURES / "capture-20261107-191727-546.png", "DK", ["Ørsted", "Faaborg", "Glamsbjerg"]),
]
# Mark crops: (file, words read by eye; empty = unreadable: any word read is invented).
MARKS = [
    ("mark-20261107-162401-349-1.png", ["Гърмен", "Гоце", "Делчев", "Благоевград", "София", "197", "219", "109"]),
    ("mark-20261107-162401-349-2.png", []),
    ("mark-20261107-171805-069-1.png", ["D", "23", "HOPITAL", "ORION", "SAUVETERRE", "BÉARN", "ORTHEZ"]),
    ("mark-20261107-171805-069-3.png", ["HÔTEL", "RESTAURANT", "LAAS"]),
    ("mark-20261107-172730-962-1.png", ["università", "PALERMO"]),
    ("mark-20261107-172730-962-2.png", ["VIA", "PAOLO", "LO", "MANTO"]),
    ("mark-20261107-185135-509-1.png", ["194", "BOŠOV", "6", "5", "LIBKOVICE", "1", "JEŘEN"]),
    ("mark-20261107-190119-944-1.png", ["Kleine", "Oker", "Waldschwimmbad", "Tennisplätze", "Okerteich"]),
    ("mark-20261107-190950-641-1.png", ["САРАНСК", "SARANSK", "162", "СТАРЫЙ", "ГОРОД", "11", "10"]),
    ("mark-20261107-191727-546-1.png", ["Ørsted", "329", "10", "5"]),
    ("mark-20261107-191727-546-2.png", ["329", "Faaborg", "28", "Glamsbjerg", "3"]),
    ("mark-20261107-172531-811-2.png", ["HÚSGAGNA", "HÖLLIN"]),
]


def old_prompts() -> dict[str, str]:
    """The 0.1 prompts, from the commit before the English rewrite."""
    text = subprocess.run(["git", "show", "7f68d25:engine/src/geonesclick/default_config.toml"], capture_output=True,
                          text=True, check=True, cwd=Path(__file__).parent).stdout
    cfg = tomllib.loads(text)
    return {"vision": cfg["vision"]["prompt"], "marks": cfg["marks"]["prompt"]}


def new_prompts(language: str) -> dict[str, str]:
    cfg = tomllib.loads((Path(__file__).parents[1] / "src/geonesclick/default_config.toml").read_text())
    return {k: cfg[k]["prompt"].replace("{language}", language) for k in ("vision", "marks")}


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFC", text))


def as_text(value) -> str:
    if isinstance(value, list):
        return " ".join(map(str, value))
    return str(value or "")


def score_view(fiche: dict, country: str, sign: list[str], old: bool) -> dict:
    concl = fiche.get("conclusion") if isinstance(fiche.get("conclusion"), dict) else {}
    found = str(concl.get("pays" if old else "country", "")).upper()
    side = str(fiche.get("sens_circulation" if old else "driving_side", "")).lower()
    text = as_text(fiche.get("panneaux_et_texte" if old else "signs_and_text"))
    read = {w.casefold() for w in words(text)}
    return {"false_conclusion": bool(found) and found != country, "right_conclusion": found == country,
            "driving_ok": side in ("droite", "right"),
            "sign_words": sum(w.casefold() in read for w in sign), "sign_total": len(sign)}


def score_mark(fiche: dict, truth: list[str], old: bool) -> dict:
    lines = fiche.get("texte" if old else "text") or []
    read = words(as_text(lines))
    expected = {w.casefold() for w in truth}
    unreadable = bool(fiche.get("illisible" if old else "unreadable"))
    return {"exact": sum(w.casefold() in {r.casefold() for r in read} for w in truth), "total": len(truth),
            "invented": sum(r.casefold() not in expected for r in read), "admits_unreadable": unreadable}


async def run(repeats: int, only: list[str]) -> dict:
    cfg = load_config()
    client = VisionClient(cfg.vision)
    if not client.client:
        sys.exit("no NVIDIA key: enter it in the Settings first")
    variants = {"fr-0.1": (old_prompts(), True), "en→en": (new_prompts("English"), False),
                "en→fr": (new_prompts("French"), False)}
    slots = asyncio.Semaphore(3)
    results: dict = {v: {"vision": [], "marks": []} for v in variants}

    async def ask(variant, kind, img, prompt, max_tokens):
        async with slots:
            try:
                fiche, seconds = await client.ask(img, prompt, cfg.vision.model, max_tokens)
                return fiche, round(seconds, 1), None
            except VisionError as exc:
                return None, None, str(exc)

    async def one_view(variant, path, country, sign):
        prompts, old = variants[variant]
        fiche, seconds, error = await ask(variant, "vision", Image.open(path).convert("RGB"), prompts["vision"],
                                          cfg.vision.max_tokens)
        row = {"file": path.name, "seconds": seconds, "error": error, "fiche": fiche}
        if fiche is not None:
            row |= score_view(fiche, country, sign, old)
        results[variant]["vision"].append(row)

    async def one_mark(variant, name, truth):
        prompts, old = variants[variant]
        fiche, seconds, error = await ask(variant, "marks", Image.open(CAPTURES / name).convert("RGB"),
                                          prompts["marks"], cfg.marks.max_tokens)
        row = {"file": name, "seconds": seconds, "error": error, "fiche": fiche}
        if fiche is not None:
            row |= score_mark(fiche, truth, old)
        results[variant]["marks"].append(row)

    views = [x for x in VIEWS if not only or any(o in x[0].name for o in only)]
    marks = [x for x in MARKS if not only or any(o in x[0] for o in only)]
    jobs = [one_view(v, p, c, s) for _ in range(repeats) for v in variants for p, c, s in views]
    jobs += [one_mark(v, n, t) for _ in range(repeats) for v in variants for n, t in marks]
    await asyncio.gather(*jobs)
    return results


def summary(results: dict) -> None:
    for variant, r in results.items():
        v = [x for x in r["vision"] if x["fiche"] is not None]
        m = [x for x in r["marks"] if x["fiche"] is not None]
        unreadable = [x for x in m if x["total"] == 0]
        readable = [x for x in m if x["total"]]
        print(f"\n{variant}")
        print(f"  vision: {len(v)}/{len(r['vision'])} valid answers; false conclusions "
              f"{sum(x['false_conclusion'] for x in v)}; right conclusions {sum(x['right_conclusion'] for x in v)};"
              f" driving side right {sum(x['driving_ok'] for x in v)}/{len(v)}; sign words read "
              f"{sum(x['sign_words'] for x in v)}/{sum(x['sign_total'] for x in v)}")
        print(f"  marks:  {len(m)}/{len(r['marks'])} valid; exact words {sum(x['exact'] for x in readable)}/"
              f"{sum(x['total'] for x in readable)}; invented words {sum(x['invented'] for x in readable)};"
              f" unreadable crop: admitted {sum(x['admits_unreadable'] for x in unreadable)}/{len(unreadable)},"
              f" invented words {sum(x['invented'] for x in unreadable)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--only", nargs="*", default=[], help="parts of file names (subset to measure)")
    args = parser.parse_args()
    results = asyncio.run(run(args.repeats, args.only))
    if args.out:
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    summary(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
