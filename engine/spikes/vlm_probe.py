"""Essai d'un modèle de vision NVIDIA : image → fiche d'indices structurée (JSON).

Usage : .venv/bin/python spikes/vlm_probe.py [--model ID] [--crop G,H,D,B] image.png

Le modèle ne fait que DÉCRIRE ce qu'il voit (rôle « vision » de l'architecture) : aucun pays n'est
demandé ici. La clé est lue dans le fichier .env à la racine du projet (variable NVAPI).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import time
from pathlib import Path

from openai import OpenAI
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "z-ai/glm-5.3-flash"
MAX_SIDE = 1280  # px : compromis entre détails lisibles et taille de requête

PROMPT = """Tu es l'œil d'un coach GeoGuessr. Décris UNIQUEMENT ce qui est visible dans cette vue
Street View, sans deviner de pays. Réponds par un objet JSON valide, en français, avec ces clés :
- "sens_circulation": "droite" | "gauche" | "indéterminé", avec la preuve dans "preuve_circulation"
- "marquage_routier": lignes (couleur, continues/discontinues, centrales/de rive) ou "aucun"
- "poteaux": matériau, forme, trous, marquages, couleurs
- "bornes_et_glissieres": bornes kilométriques, délinéateurs, glissières
- "panneaux_et_texte": textes lus mot pour mot, alphabet, langue probable
- "plaques_immatriculation": couleurs, forme, bande latérale
- "architecture": style, toits, matériaux, clôtures
- "vegetation_et_sol": espèces reconnaissables, couleur du sol, climat apparent
- "relief": plat, collines, montagnes
- "camera_et_voiture_google": génération de caméra, partie visible du véhicule, antenne
- "autres_indices": tout autre détail discriminant
- "confiance": "faible" | "moyenne" | "élevée" sur la qualité globale de l'observation
Si un élément n'est pas visible, mets "non visible". Ignore l'interface du jeu (boutons, boussole, carte)."""


def load_key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("NVAPI="):
            key = line.split("=", 1)[1].strip().strip("\"'")
            if key:
                return key
    raise SystemExit("NVAPI absente ou vide dans .env")


def encode(path: Path, crop: tuple[int, int, int, int] | None) -> str:
    img = Image.open(path).convert("RGB")
    if crop:
        img = img.crop(crop)
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("image", type=Path)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--crop", help="gauche,haut,droite,bas en pixels")
    args = p.parse_args()
    crop = tuple(int(v) for v in args.crop.split(",")) if args.crop else None

    client = OpenAI(base_url=BASE_URL, api_key=load_key(), timeout=90, max_retries=0)
    b64 = encode(args.image, crop)
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=args.model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        temperature=0.2,
        max_tokens=4000,  # les modèles à raisonnement consomment des jetons avant de répondre
    )
    elapsed = time.perf_counter() - t0
    text = resp.choices[0].message.content or ""
    tokens = resp.usage.total_tokens if resp.usage else "?"
    print(f"Modèle : {args.model}  |  latence : {elapsed:.1f} s  |  jetons : {tokens}\n")
    start, end = text.find("{"), text.rfind("}")
    try:
        print(json.dumps(json.loads(text[start:end + 1]), ensure_ascii=False, indent=2))
    except ValueError:
        print("[réponse non JSON]\n" + text)


if __name__ == "__main__":
    main()
