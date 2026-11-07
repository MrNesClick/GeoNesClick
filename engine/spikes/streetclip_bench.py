"""Test de faisabilité n°3 : StreetCLIP sur la carte graphique locale (RTX 3050 Ti, 4 Go).

Usage : .venv/bin/python spikes/streetclip_bench.py [image.png ...]
Sans argument, prend la dernière capture de engine/captures/.

Mesure : mémoire GPU utilisée, temps de chargement, latence par image (à chaud) et top 5 des pays.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

MODEL_ID = "geolocal/StreetCLIP"
PROMPT = "A Street View photo in {}."  # sera configurable

# Pays couverts par Google Street View utilisés couramment dans GeoGuessr (liste à affiner).
COUNTRIES = [
    "Albania", "Andorra", "Argentina", "Australia", "Austria", "Bangladesh", "Belgium", "Bhutan",
    "Bolivia", "Botswana", "Brazil", "Bulgaria", "Cambodia", "Canada", "Chile", "Colombia",
    "Croatia", "Czechia", "Denmark", "Dominican Republic", "Ecuador", "Estonia", "Eswatini",
    "Finland", "France", "Germany", "Ghana", "Greece", "Guatemala", "Hungary", "Iceland", "India",
    "Indonesia", "Ireland", "Israel", "Italy", "Japan", "Jordan", "Kenya", "Kyrgyzstan", "Latvia",
    "Lesotho", "Lithuania", "Luxembourg", "Malaysia", "Malta", "Mexico", "Mongolia", "Montenegro",
    "Netherlands", "New Zealand", "Nigeria", "North Macedonia", "Norway", "Panama", "Peru",
    "Philippines", "Poland", "Portugal", "Romania", "Russia", "Rwanda", "Senegal", "Serbia",
    "Singapore", "Slovakia", "Slovenia", "South Africa", "South Korea", "Spain", "Sri Lanka",
    "Sweden", "Switzerland", "Taiwan", "Thailand", "Tunisia", "Turkey", "Uganda", "Ukraine",
    "United Arab Emirates", "United Kingdom", "United States", "Uruguay", "Vietnam",
]


def gpu_mib() -> float:
    return torch.cuda.max_memory_allocated() / 2**20


def main(paths: list[Path]) -> None:
    if not paths:
        captures = sorted((Path(__file__).resolve().parent.parent / "captures").glob("*.png"))
        if not captures:
            sys.exit("Aucune image : passe un chemin en argument ou fais d'abord une capture.")
        paths = [captures[-1]]

    assert torch.cuda.is_available(), "CUDA indisponible"
    print(f"GPU : {torch.cuda.get_device_name(0)}  |  torch {torch.__version__}")

    t0 = time.perf_counter()
    model = CLIPModel.from_pretrained(MODEL_ID, torch_dtype=torch.float16).to("cuda").eval()
    processor = CLIPProcessor.from_pretrained(MODEL_ID)
    print(f"Chargement : {time.perf_counter() - t0:.1f} s  |  VRAM modèle : {gpu_mib():.0f} Mio")

    # Les embeddings texte des pays sont calculés une seule fois au démarrage.
    with torch.inference_mode():
        text_in = processor(text=[PROMPT.format(c) for c in COUNTRIES], return_tensors="pt", padding=True).to("cuda")
        text_emb = model.get_text_features(**text_in).pooler_output  # Transformers 5 : objet de sortie
        text_emb = text_emb / text_emb.norm(dim=-1, keepdim=True)

    for path in paths:
        image = Image.open(path).convert("RGB")
        timings = []
        for _ in range(4):  # 1 passe de chauffe + 3 mesures
            torch.cuda.synchronize()
            t = time.perf_counter()
            with torch.inference_mode():
                img_in = processor(images=image, return_tensors="pt").to("cuda", torch.float16)
                img_emb = model.get_image_features(**img_in).pooler_output
                img_emb = img_emb / img_emb.norm(dim=-1, keepdim=True)
                probs = (model.logit_scale.exp() * img_emb @ text_emb.T).softmax(dim=-1)[0]
            torch.cuda.synchronize()
            timings.append((time.perf_counter() - t) * 1000)
        top = probs.float().topk(5)
        print(f"\n{path.name}  |  latence à chaud : {min(timings[1:]):.0f} ms (froid {timings[0]:.0f} ms)")
        for p, i in zip(top.values.tolist(), top.indices.tolist(), strict=True):
            print(f"  {COUNTRIES[i]:<22} {p:6.1%}")

    print(f"\nPic VRAM : {gpu_mib():.0f} Mio")


if __name__ == "__main__":
    main([Path(p) for p in sys.argv[1:]])
