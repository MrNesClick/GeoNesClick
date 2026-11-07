"""Expérience : moyenner StreetCLIP sur plusieurs recadrages améliore-t-il le niveau 1 ?

Compare, sur le jeu de test étiqueté, une prédiction sur l'image entière et la moyenne des
probabilités sur plusieurs vues (entière, moitié gauche, centre, moitié droite).

Usage : .venv/bin/python spikes/streetclip_tta.py
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch  # noqa: E402
from PIL import Image  # noqa: E402

from geonesclick.config import load_config  # noqa: E402
from geonesclick.streetclip import StreetClip  # noqa: E402

DATASET = Path(__file__).resolve().parent.parent / "dataset"
VIEWS = {  # fractions [gauche, haut, droite, bas]
    "entière": (0.0, 0.0, 1.0, 1.0),
    "gauche": (0.0, 0.0, 0.55, 1.0),
    "centre": (0.225, 0.0, 0.775, 1.0),
    "droite": (0.45, 0.0, 1.0, 1.0),
}


def probs(clip: StreetClip, img: Image.Image) -> torch.Tensor:
    with torch.inference_mode():
        x = clip.processor(images=img, return_tensors="pt").to(clip.device, clip.model.dtype)
        emb = clip.model.get_image_features(**x).pooler_output
        emb = emb / emb.norm(dim=-1, keepdim=True)
        return (clip.model.logit_scale.exp() * emb @ clip.text_emb.T).softmax(dim=-1)[0].float()


def rank_of(p: torch.Tensor, idx: int) -> int:
    return int((p > p[idx]).sum()) + 1


def main() -> None:
    cfg = load_config()
    clip = StreetClip(cfg.streetclip)
    codes = list(cfg.streetclip.countries.values())
    labels = tomllib.loads((DATASET / "labels.toml").read_text())["capture"]
    stats = {k: [0, 0, 0.0] for k in ("simple", "moyenne")}  # top-1, top-3, proba du bon pays
    for item in labels:
        img = Image.open(DATASET / "images" / item["file"]).convert("RGB")
        w, h = img.size
        per_view = {
            name: probs(clip, img.crop((int(a * w), int(b * h), int(c * w), int(d * h))))
            for name, (a, b, c, d) in VIEWS.items()
        }
        truth = codes.index(item["country"])
        for key, p in (("simple", per_view["entière"]), ("moyenne", torch.stack(list(per_view.values())).mean(0))):
            r = rank_of(p, truth)
            stats[key][0] += r == 1
            stats[key][1] += r <= 3
            stats[key][2] += float(p[truth])
            top = ", ".join(f"{codes[i]} {float(p[i]):.0%}" for i in p.topk(3).indices.tolist())
            print(f"{item['country']}  {key:<8} rang {r:>2}  ({float(p[truth]):.0%})  top : {top}")
    n = len(labels)
    print(f"\nSur {n} captures :")
    for key, (t1, t3, pr) in stats.items():
        print(f"  {key:<8} top-1 {t1}/{n}  top-3 {t3}/{n}  proba moyenne du bon pays {pr / n:.0%}")


if __name__ == "__main__":
    main()
