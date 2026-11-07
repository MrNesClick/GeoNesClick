"""Expérience : PLONK (CVPR 2025) sur nos captures, branché sur le StreetCLIP déjà chargé par le moteur.

PLONK_OSV_5M conditionne un petit réseau (~36 M paramètres) sur le jeton [CLS] de StreetCLIP et tire des
points GPS sur la sphère. On compare, sur le jeu de test étiqueté : le pays réel selon StreetCLIP seul et
selon la part des points PLONK tombés dans chaque pays ; on mesure aussi la dispersion du nuage, le temps
et la mémoire graphique.

Prérequis : scripts/setup-plonk-spike.sh (code PLONK figé, dépendances et frontières dans spikes/.vendor/,
hors du venv du moteur).

Usage : .venv/bin/python spikes/plonk_bench.py [échantillons]   (512 par défaut)
Le premier lancement télécharge nicolas-dufour/PLONK_OSV_5M depuis Hugging Face (safetensors, 144 Mo).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import tomllib
import types
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from geonesclick.config import load_config
from geonesclick.streetclip import StreetClip

DATASET = Path(__file__).resolve().parent.parent / "dataset"
VENDOR = Path(__file__).resolve().parent / ".vendor"  # rempli par scripts/setup-plonk-spike.sh
BORDERS = VENDOR / "ne_50m_admin_0_countries.geojson"
MODEL_ID = "nicolas-dufour/PLONK_OSV_5M"
EARTH_KM = 6371.0


def load_borders(path: Path) -> list[tuple[str, np.ndarray, list[np.ndarray]]]:
    """(code ISO, boîte englobante, anneaux extérieurs) par pays ; ISO_A2_EH corrige France et Norvège (-99)."""
    out = []
    for feat in json.loads(path.read_text())["features"]:
        code = feat["properties"].get("ISO_A2_EH") or feat["properties"].get("ISO_A2")
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        rings = [np.asarray(p[0], dtype=np.float64) for p in polys]  # trous ignorés (enclaves rares)
        allpts = np.concatenate(rings)
        out.append((code, np.r_[allpts.min(0), allpts.max(0)], rings))
    return out


def inside(ring: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Test du rayon (pair-impair), vectorisé sur les points."""
    x0, y0 = ring[:-1, 0][:, None], ring[:-1, 1][:, None]
    x1, y1 = ring[1:, 0][:, None], ring[1:, 1][:, None]
    cross = (y0 > lat) != (y1 > lat)
    with np.errstate(divide="ignore", invalid="ignore"):
        xint = x0 + (lat - y0) * (x1 - x0) / (y1 - y0)
    return ((cross & (lon < xint)).sum(0) % 2) == 1


def countries_of(borders, lat: np.ndarray, lon: np.ndarray) -> list[str]:
    found = np.full(lat.shape, "", dtype=object)
    for code, (bx0, by0, bx1, by1), rings in borders:
        cand = (found == "") & (lon >= bx0) & (lon <= bx1) & (lat >= by0) & (lat <= by1)
        if not cand.any():
            continue
        idx = np.nonzero(cand)[0]
        hit = np.zeros(idx.shape, dtype=bool)
        for ring in rings:
            hit |= inside(ring, lon[idx], lat[idx])
        found[idx[hit]] = code
    return [c or "mer" for c in found]


def haversine(lat1, lon1, lat2, lon2) -> np.ndarray:
    p1, p2, dl = np.radians(lat1), np.radians(lat2), np.radians(lon2 - lon1)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def bare_plonk_package() -> None:
    """Rend `plonk` importable sans exécuter son __init__ (qui tire pipe.py, torchvision et DINOv2)."""
    sys.path[:0] = [str(VENDOR / "plonk"), str(VENDOR / "deps")]
    spec = importlib.util.find_spec("plonk")
    if spec is None or not spec.submodule_search_locations:
        sys.exit("Code PLONK introuvable : lance d'abord scripts/setup-plonk-spike.sh.")
    pkg = types.ModuleType("plonk")
    pkg.__path__ = list(spec.submodule_search_locations)
    sys.modules["plonk"] = pkg


class Plonk:
    def __init__(self, device: str) -> None:
        bare_plonk_package()
        from plonk.models.postprocessing import CartesiantoGPS
        from plonk.models.preconditioning import DDPMPrecond
        from plonk.models.pretrained_models import Plonk as Net
        from plonk.models.samplers.riemannian_flow_sampler import riemannian_flow_sampler
        from plonk.models.schedulers import SigmoidScheduler

        self.net = Net.from_pretrained(MODEL_ID).to(device).requires_grad_(False).eval()
        self.precond, self.sampler = DDPMPrecond(), riemannian_flow_sampler
        self.scheduler = SigmoidScheduler(-7, 3, 1.0, 1e-9)  # réglages par défaut de PlonkPipeline
        self.to_gps, self.device = CartesiantoGPS(), device

    def sample(self, cls: torch.Tensor, n: int, steps: int, seed: int = 0) -> np.ndarray:
        gen = torch.Generator(device=self.device).manual_seed(seed)
        batch = {"y": torch.randn(n, 3, device=self.device, generator=gen),
                 "emb": cls.float().repeat(n, 1)}
        with torch.inference_mode():
            out = self.sampler(lambda b: self.precond(self.net, b), batch, conditioning_keys="emb",
                               scheduler=self.scheduler, num_steps=steps, generator=gen)
        return np.degrees(self.to_gps(out).cpu().numpy())  # (n, 2) : lat, lon


def encode(clip: StreetClip, img: Image.Image) -> tuple[torch.Tensor, torch.Tensor]:
    """Une seule passe du ViT : probabilités par pays (comme le moteur) ET jeton [CLS] pour PLONK."""
    with torch.inference_mode():
        x = clip.processor(images=img, return_tensors="pt").to(clip.device, clip.model.dtype)
        vis = clip.model.vision_model(pixel_values=x["pixel_values"])
        emb = clip.model.visual_projection(vis.pooler_output)
        emb = emb / emb.norm(dim=-1, keepdim=True)
        probs = (clip.model.logit_scale.exp() * emb @ clip.text_emb.T).softmax(dim=-1)[0].float()
    return probs, vis.last_hidden_state[:, 0]


def check_cls(clip: StreetClip, img: Image.Image, cls16: torch.Tensor) -> float:
    """PLONK a été entraîné sur le [CLS] en fp32 de CLIPVisionModel ; notre moteur tourne en fp16."""
    from transformers import CLIPVisionModel

    ref = CLIPVisionModel.from_pretrained(clip.cfg.model).eval()  # CPU, fp32
    with torch.inference_mode():
        px = clip.processor(images=img, return_tensors="pt")["pixel_values"]
        cls32 = ref(pixel_values=px).last_hidden_state[:, 0]
    del ref
    return float(torch.nn.functional.cosine_similarity(cls32, cls16.float().cpu()))


def rank(ordered: list[str], code: str) -> str:
    return str(ordered.index(code) + 1) if code in ordered else "-"


STEPS = (250, 100, 50, 25)  # 250 = défaut du papier ; combien de pas peut-on retirer sans perdre le nuage ?


def cloud(borders, pts: np.ndarray) -> tuple[Counter, list[str], tuple[float, float], float]:
    """Part des points par pays, pays classés, mode du nuage et dispersion médiane autour de lui (km).

    Mode : le point qui a le plus de voisins à moins de 300 km.
    """
    lat, lon = pts[:, 0], pts[:, 1]
    share = Counter(countries_of(borders, lat, lon))
    d = haversine(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    mode = int((d < 300).sum(1).argmax())
    return share, [c for c, _ in share.most_common() if c != "mer"], (lat[mode], lon[mode]), float(np.median(d[mode]))


def timed(plonk: Plonk, cls: torch.Tensor, n: int, steps: int) -> tuple[np.ndarray, float]:
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    pts = plonk.sample(cls, n, steps)
    torch.cuda.synchronize()
    return pts, (time.perf_counter() - t0) * 1000


def main(borders_path: Path, n: int) -> None:
    cfg = load_config()
    torch.cuda.reset_peak_memory_stats()
    clip = StreetClip(cfg.streetclip)
    base = torch.cuda.max_memory_allocated() / 2**20
    os.environ.pop("HF_HUB_OFFLINE", None)  # téléchargement des poids PLONK au premier lancement
    plonk = Plonk(clip.device)
    print(f"VRAM : StreetCLIP {base:.0f} Mio, + PLONK {torch.cuda.max_memory_allocated() / 2**20 - base:.0f} Mio")

    codes = list(cfg.streetclip.countries.values())
    borders = load_borders(borders_path)
    labels = tomllib.loads((DATASET / "labels.toml").read_text())["capture"]
    keys = ["StreetCLIP"] + [f"PLONK {s} pas" for s in STEPS]
    totals = {k: [0, 0] for k in keys}  # top-1, top-3
    drift = {s: [] for s in STEPS}  # écart du mode au mode à 250 pas (km)
    cost = {s: [] for s in STEPS}  # temps (ms)
    small = []  # temps pour 128 points à 50 pas : le nombre de points compte-t-il ?

    for i, item in enumerate(labels):
        img = Image.open(DATASET / "images" / item["file"]).convert("RGB")
        probs, cls = encode(clip, img)
        if i == 0:
            print(f"Cosinus [CLS] fp16 GPU / fp32 CPU : {check_cls(clip, img, cls):.5f}")
        sc_order = [codes[j] for j in probs.argsort(descending=True).tolist()]
        truth = item["country"]
        totals["StreetCLIP"][0] += sc_order[:1] == [truth]
        totals["StreetCLIP"][1] += truth in sc_order[:3]
        top_sc = ", ".join(f"{codes[j]} {probs[j]:.0%}" for j in probs.argsort(descending=True)[:3].tolist())
        print(f"\n{item['file']}  réel {truth} ({item.get('area', '')})")
        print(f"  StreetCLIP     rang {rank(sc_order, truth):>2} | {top_sc}")

        ref = None
        for steps in STEPS:
            pts, ms = timed(plonk, cls, n, steps)
            share, order, mode, spread = cloud(borders, pts)
            ref = ref or mode
            gap = float(haversine(mode[0], mode[1], ref[0], ref[1]))
            key = f"PLONK {steps} pas"
            totals[key][0] += order[:1] == [truth]
            totals[key][1] += truth in order[:3]
            drift[steps].append(gap)
            cost[steps].append(ms)
            top_pl = ", ".join(f"{c} {k / n:.0%}" for c, k in share.most_common(4))
            print(f"  PLONK {steps:>3} pas  rang {rank(order, truth):>2} | {top_pl:<34} | mode {mode[0]:.2f},"
                  f" {mode[1]:.2f} ({gap:.0f} km du mode à {STEPS[0]} pas) | dispersion {spread:.0f} km | {ms:.0f} ms")
        small.append(timed(plonk, cls, 128, 50)[1])

    print(f"\nSur {len(labels)} captures ({n} points) :")
    for key in keys:
        t1, t3 = totals[key]
        extra = ""
        if key != "StreetCLIP":
            s = int(key.split()[1])
            extra = f" | écart moyen du mode {np.mean(drift[s]):.0f} km | {np.mean(cost[s]):.0f} ms"
        print(f"  {key:<15} top-1 {t1}/{len(labels)}  top-3 {t3}/{len(labels)}{extra}")
    print(f"128 points à 50 pas : {np.mean(small):.0f} ms (contre {np.mean(cost[50]):.0f} ms pour {n})")
    print(f"Pic VRAM : {torch.cuda.max_memory_allocated() / 2**20:.0f} Mio")


if __name__ == "__main__":
    if not BORDERS.exists():
        sys.exit(__doc__)
    main(BORDERS, int(sys.argv[1]) if len(sys.argv) > 1 else 512)
