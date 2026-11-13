"""Experiment: PLONK (CVPR 2025) on our captures, plugged into the StreetCLIP already loaded by the engine.

PLONK_OSV_5M conditions a small network (~36 M parameters) on StreetCLIP's [CLS] token and samples
GPS points on the sphere. On the labelled test set, we compare: the real country according to StreetCLIP alone and
according to the share of PLONK points falling in each country; we also measure the spread of the cloud, the time
and the graphics memory.

Prerequisite: scripts/setup-plonk-spike.sh (pinned PLONK code, dependencies and borders in spikes/.vendor/,
outside the engine's venv).

Usage: .venv/bin/python spikes/plonk_bench.py [samples]   (512 by default)
The first run downloads nicolas-dufour/PLONK_OSV_5M from Hugging Face (safetensors, 144 MB).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import types
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from geonesclick.config import load_config
from geonesclick.streetclip import StreetClip

import testset  # spikes/testset.py: labels and images, Claude in Chrome artefacts cropped out

VENDOR = Path(__file__).resolve().parent / ".vendor"  # filled by scripts/setup-plonk-spike.sh
BORDERS = VENDOR / "ne_50m_admin_0_countries.geojson"
MODEL_ID = "nicolas-dufour/PLONK_OSV_5M"
EARTH_KM = 6371.0


def load_borders(path: Path) -> list[tuple[str, np.ndarray, list[np.ndarray]]]:
    """(ISO code, bounding box, outer rings) per country; ISO_A2_EH fixes France and Norway (-99)."""
    out = []
    for feat in json.loads(path.read_text())["features"]:
        code = feat["properties"].get("ISO_A2_EH") or feat["properties"].get("ISO_A2")
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        rings = [np.asarray(p[0], dtype=np.float64) for p in polys]  # holes ignored (rare enclaves)
        allpts = np.concatenate(rings)
        out.append((code, np.r_[allpts.min(0), allpts.max(0)], rings))
    return out


def inside(ring: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Ray test (even-odd), vectorised over the points."""
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
    """Makes `plonk` importable without running its __init__ (which pulls in pipe.py, torchvision and DINOv2)."""
    sys.path[:0] = [str(VENDOR / "plonk"), str(VENDOR / "deps")]
    spec = importlib.util.find_spec("plonk")
    if spec is None or not spec.submodule_search_locations:
        sys.exit("PLONK code not found: run scripts/setup-plonk-spike.sh first.")
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
        self.scheduler = SigmoidScheduler(-7, 3, 1.0, 1e-9)  # PlonkPipeline default settings
        self.to_gps, self.device = CartesiantoGPS(), device

    def sample(self, cls: torch.Tensor, n: int, steps: int, seed: int = 0) -> np.ndarray:
        gen = torch.Generator(device=self.device).manual_seed(seed)
        batch = {"y": torch.randn(n, 3, device=self.device, generator=gen),
                 "emb": cls.float().repeat(n, 1)}
        with torch.inference_mode():
            out = self.sampler(lambda b: self.precond(self.net, b), batch, conditioning_keys="emb",
                               scheduler=self.scheduler, num_steps=steps, generator=gen)
        return np.degrees(self.to_gps(out).cpu().numpy())  # (n, 2): lat, lon


def encode(clip: StreetClip, img: Image.Image) -> tuple[torch.Tensor, torch.Tensor]:
    """A single ViT pass: probabilities per country (like the engine) AND the [CLS] token for PLONK."""
    with torch.inference_mode():
        x = clip.processor(images=img, return_tensors="pt").to(clip.device, clip.model.dtype)
        vis = clip.model.vision_model(pixel_values=x["pixel_values"])
        emb = clip.model.visual_projection(vis.pooler_output)
        emb = emb / emb.norm(dim=-1, keepdim=True)
        probs = (clip.model.logit_scale.exp() * emb @ clip.text_emb.T).softmax(dim=-1)[0].float()
    return probs, vis.last_hidden_state[:, 0]


def check_cls(clip: StreetClip, img: Image.Image, cls16: torch.Tensor) -> float:
    """PLONK was trained on the fp32 [CLS] of CLIPVisionModel; our engine runs in fp16."""
    from transformers import CLIPVisionModel

    ref = CLIPVisionModel.from_pretrained(clip.cfg.model).eval()  # CPU, fp32
    with torch.inference_mode():
        px = clip.processor(images=img, return_tensors="pt")["pixel_values"]
        cls32 = ref(pixel_values=px).last_hidden_state[:, 0]
    del ref
    return float(torch.nn.functional.cosine_similarity(cls32, cls16.float().cpu()))


def rank(ordered: list[str], code: str) -> str:
    return str(ordered.index(code) + 1) if code in ordered else "-"


STEPS = (250, 100, 50, 25)  # 250 = the paper's default; how many steps can we remove without losing the cloud?


def cloud(borders, pts: np.ndarray) -> tuple[Counter, list[str], tuple[float, float], float]:
    """Share of points per country, ranked countries, mode of the cloud and median spread around it (km).

    Mode: the point with the most neighbours within 300 km.
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
    os.environ.pop("HF_HUB_OFFLINE", None)  # download of the PLONK weights on first run
    plonk = Plonk(clip.device)
    print(f"VRAM: StreetCLIP {base:.0f} MiB, + PLONK {torch.cuda.max_memory_allocated() / 2**20 - base:.0f} MiB")

    codes = list(cfg.streetclip.countries.values())
    borders = load_borders(borders_path)
    labels = testset.labels()
    keys = ["StreetCLIP"] + [f"PLONK {s} steps" for s in STEPS]
    totals = {k: [0, 0] for k in keys}  # top-1, top-3
    drift = {s: [] for s in STEPS}  # distance from the mode to the mode at 250 steps (km)
    cost = {s: [] for s in STEPS}  # time (ms)
    small = []  # time for 128 points at 50 steps: does the number of points matter?
    error = {s: [] for s in STEPS}  # distance from the mode to the true place (km), labels with coordinates only
    held = {s: 0 for s in STEPS}  # true place within the spread around the mode

    for i, item in enumerate(labels):
        img = testset.image(item)
        probs, cls = encode(clip, img)
        if i == 0:
            print(f"Cosine [CLS] fp16 GPU / fp32 CPU: {check_cls(clip, img, cls):.5f}")
        sc_order = [codes[j] for j in probs.argsort(descending=True).tolist()]
        truth = item["country"]
        totals["StreetCLIP"][0] += sc_order[:1] == [truth]
        totals["StreetCLIP"][1] += truth in sc_order[:3]
        top_sc = ", ".join(f"{codes[j]} {probs[j]:.0%}" for j in probs.argsort(descending=True)[:3].tolist())
        print(f"\n{item['file']}  real {truth} ({item.get('area', '')})")
        print(f"  StreetCLIP     rank {rank(sc_order, truth):>2} | {top_sc}")

        ref = None
        for steps in STEPS:
            pts, ms = timed(plonk, cls, n, steps)
            share, order, mode, spread = cloud(borders, pts)
            ref = ref or mode
            gap = float(haversine(mode[0], mode[1], ref[0], ref[1]))
            key = f"PLONK {steps} steps"
            totals[key][0] += order[:1] == [truth]
            totals[key][1] += truth in order[:3]
            drift[steps].append(gap)
            if "lat" in item:
                error[steps].append((float(haversine(mode[0], mode[1], item["lat"], item["lon"])), order[:1] == [truth]))
                held[steps] += error[steps][-1][0] <= spread
            cost[steps].append(ms)
            top_pl = ", ".join(f"{c} {k / n:.0%}" for c, k in share.most_common(4))
            true = f" | {error[steps][-1][0]:.0f} km from the true place" if "lat" in item else ""
            print(f"  PLONK {steps:>3} steps  rank {rank(order, truth):>2} | {top_pl:<34} | mode {mode[0]:.2f},"
                  f" {mode[1]:.2f} ({gap:.0f} km from the mode at {STEPS[0]} steps) | spread {spread:.0f} km{true}"
                  f" | {ms:.0f} ms")
        small.append(timed(plonk, cls, 128, 50)[1])

    print(f"\nOver {len(labels)} captures ({n} points):")
    for key in keys:
        t1, t3 = totals[key]
        extra = ""
        if key != "StreetCLIP":
            s = int(key.split()[1])
            extra = f" | mean drift of the mode {np.mean(drift[s]):.0f} km | {np.mean(cost[s]):.0f} ms"
            if error[s]:
                right = [km for km, ok in error[s] if ok]
                extra += (f" | true place: median {np.median([km for km, _ in error[s]]):.0f} km over {len(error[s])},"
                          f" {np.median(right) if right else float('nan'):.0f} km when the country is right"
                          f" ({len(right)}), within the spread {held[s]}/{len(error[s])}")
        print(f"  {key:<15} top-1 {t1}/{len(labels)}  top-3 {t3}/{len(labels)}{extra}")
    print(f"128 points at 50 steps: {np.mean(small):.0f} ms (against {np.mean(cost[50]):.0f} ms for {n})")
    print(f"Peak VRAM: {torch.cuda.max_memory_allocated() / 2**20:.0f} MiB")


if __name__ == "__main__":
    if not BORDERS.exists():
        sys.exit(__doc__)
    main(BORDERS, int(sys.argv[1]) if len(sys.argv) > 1 else 512)
