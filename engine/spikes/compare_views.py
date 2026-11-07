"""Expérience : que gagne-t-on à recadrer la vue et à masquer l'interface du jeu ?

Compare trois variantes sur le jeu de test étiqueté (dataset/labels.toml) :
  fenetre  la fenêtre du navigateur entière
  cadre    la vue Street View seule (sans la barre du navigateur)
  masques  la vue, avec l'interface GeoGuessr masquée (logo, boussole, scores, boutons, mini-carte)
Mesure, pour chaque variante : rang et probabilité du bon pays selon StreetCLIP, et pour le modèle de
vision, les noms de pays recopiés depuis l'image (fuite de la mini-carte).

Usage : .venv/bin/python spikes/compare_views.py [--no-vision]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tomllib
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # StreetCLIP déjà en cache : aucun appel réseau

from PIL import Image  # noqa: E402

from geonesclick.capture import apply_crop_and_masks  # noqa: E402
from geonesclick.config import load_config  # noqa: E402
from geonesclick.streetclip import StreetClip  # noqa: E402
from geonesclick.vision import VisionClient, VisionError  # noqa: E402

DATASET = Path(__file__).resolve().parent.parent / "dataset"

# Mise en page « partie classique, fenêtre de navigateur 1920x1200 », mesurée sur les captures.
CROP = [0.0, 122 / 1200, 1.0, 1.0]
MASKS = [
    [0.00, 0.00, 0.08, 0.05],   # logo
    [0.42, 0.00, 0.58, 0.05],   # boussole
    [0.76, 0.00, 1.00, 0.14],   # scores
    [0.00, 0.15, 0.05, 0.96],   # boutons
    [0.80, 0.69, 1.00, 1.00],   # mini-carte + bouton « placez votre épingle »
    [0.00, 0.975, 1.00, 1.00],  # bandeau Google du bas
]
VARIANTS = {"fenetre": ([], []), "cadre": (CROP, []), "masques": (CROP, MASKS)}

# Noms de pays visibles sur la mini-carte (en français) et leurs équivalents anglais.
MAP_NAMES = ["Norvège", "Finlande", "Suède", "Pologne", "Ukraine", "Roumanie", "France", "Allemagne",
             "Royaume-Uni", "Autriche", "Espagne", "Italie", "Norway", "Finland", "Sweden", "Poland",
             "Romania", "Germany", "Lettonie", "Lituanie", "Serbie", "Latvia", "Lithuania", "Serbia"]


def leaked_names(fiche: dict) -> list[str]:
    text = json.dumps(fiche, ensure_ascii=False)
    return sorted({n for n in MAP_NAMES if re.search(rf"\b{re.escape(n)}\b", text, re.IGNORECASE)})


async def main(with_vision: bool) -> None:
    labels = tomllib.loads((DATASET / "labels.toml").read_text())["capture"]
    cfg = load_config()
    clip = StreetClip(cfg.streetclip.model_copy(update={"top_k": 20}))  # rang du bon pays jusqu'à 20
    vision = VisionClient(cfg.vision) if with_vision else None
    code_to_name = {v: k for k, v in cfg.streetclip.countries.items()}
    sem = asyncio.Semaphore(3)  # limite de débit du palier gratuit

    async def describe(img):
        async with sem:
            try:
                fiche, s = await vision.describe(img)
                return fiche, s, None
            except VisionError as exc:
                return None, 0, str(exc)

    summary = {v: {"top1": 0, "top3": 0, "proba": 0.0, "fuites": 0} for v in VARIANTS}
    for item in labels:
        frame = Image.open(DATASET / "images" / item["file"]).convert("RGB")
        truth = item["country"]
        print(f"\n=== {item['file']}  →  {code_to_name.get(truth, truth)} ({truth})")
        views = {name: apply_crop_and_masks(frame, c, m) for name, (c, m) in VARIANTS.items()}
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
            line = f"  {name:<8} StreetCLIP rang {rank or '>20'}  ({proba:.0%})  top : {top}"
            if vision:
                fiche, secs, err = await tasks[name]
                if err:
                    line += f"  | vision : ERREUR {err[:60]}"
                else:
                    leaks = leaked_names(fiche)
                    summary[name]["fuites"] += bool(leaks)
                    line += f"  | vision {secs:4.1f} s, noms de pays recopiés : {', '.join(leaks) or 'aucun'}"
            print(line)

    n = len(labels)
    print(f"\n=== Synthèse sur {n} captures")
    print(f"  {'variante':<8} {'top-1':>6} {'top-3':>6} {'proba moy.':>11} {'fuites':>7}")
    for name, s in summary.items():
        fuites = f"{s['fuites']}/{n}" if with_vision else "-"
        print(f"  {name:<8} {s['top1']:>4}/{n} {s['top3']:>4}/{n} {s['proba'] / n:>10.0%} {fuites:>7}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--no-vision", action="store_true", help="StreetCLIP seulement (sans appel réseau)")
    sys.exit(asyncio.run(main(not p.parse_args().no_vision)))
