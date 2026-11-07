"""Nuage de positions probables d'une vue, pour la carte du coach : PLONK sur le jeton [CLS] de StreetCLIP.

PLONK (Dufour, Picard, Kalogeiton, Landrieu, « Around the World in 80 Timesteps », CVPR 2025) tire des
points sur la sphère par un flot riemannien conditionné sur l'image. Modèle « nicolas-dufour/PLONK_OSV_5M »
(safetensors), entraîné sur OSV-5M avec StreetCLIP comme encodeur. Il ne sert qu'à la CARTE : mesuré sur le
jeu de test, il ne classe pas mieux les pays que StreetCLIP (même vecteur) ; voir README, spikes/plonk_bench.py.

Le réseau et l'échantillonneur sont repris de https://github.com/nicolas-dufour/plonk (commit 76d4641),
réduits à ce que demande ce modèle : GeoAdaLNMLP, échelle sigmoïde, flot sans guidage. La projection sur la
sphère de geoopt (Sphere.projx) se réduit ici à une normalisation : ni geoopt ni scipy ne sont nécessaires.

    MIT License — Copyright (c) 2024 Nicolas Dufour

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
    associated documentation files (the "Software"), to deal in the Software without restriction, including
    without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the
    following conditions: The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
    LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO
    EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
    IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
    USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn

from .config import PlonkConfig

EARTH_KM = 6371.0
SCHEDULE = (-7.0, 3.0, 1.0, 1e-9)  # échelle sigmoïde par défaut de PLONK : début, fin, tau, plancher


# --- Réseau (repris de plonk/models/networks/mlp.py ; noms des couches inchangés pour les poids) ----------
class PositionalEmbedding(nn.Module):
    def __init__(self, num_channels: int, max_positions: int = 10000, endpoint: bool = False) -> None:
        super().__init__()
        freqs = torch.arange(start=0, end=num_channels // 2, dtype=torch.float32)
        freqs = 2 * freqs / num_channels
        self.register_buffer("freqs", (1 / max_positions) ** freqs)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = torch.outer(x, self.freqs)
        return torch.cat([x.cos(), x.sin()], dim=1).to(x.dtype)


class TimeEmbedder(nn.Module):
    def __init__(self, dim: int, time_scaling: float, expansion: int = 4) -> None:
        super().__init__()
        self.encode_time = PositionalEmbedding(num_channels=dim, endpoint=True)
        self.time_scaling = time_scaling
        self.map_time = nn.Sequential(nn.Linear(dim, dim * expansion), nn.SiLU(),
                                      nn.Linear(dim * expansion, dim * expansion))

    def forward(self, t: torch.Tensor) -> torch.Tensor:
        time = self.encode_time(t * self.time_scaling)
        time = (time - time.mean(dim=-1, keepdim=True)) / time.std(dim=-1, keepdim=True)
        return self.map_time(time)


class FusedMLP(nn.Sequential):
    def __init__(self, dim: int, hidden_layer_multiplier: int) -> None:
        super().__init__(nn.Linear(dim, dim * hidden_layer_multiplier), nn.GELU(), nn.Dropout(0.0),
                         nn.Linear(dim * hidden_layer_multiplier, dim))


class AdaLNMLPBlock(nn.Module):
    def __init__(self, dim: int, expansion: int) -> None:
        super().__init__()
        self.mlp = FusedMLP(dim, expansion)
        self.ada_map = nn.Sequential(nn.SiLU(), nn.Linear(dim, dim * 3))
        self.ln = nn.LayerNorm(dim, elementwise_affine=False)

    def forward(self, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        gamma, mu, sigma = self.ada_map(y).chunk(3, dim=-1)
        return x + self.mlp((1 + gamma) * self.ln(x) + mu) * sigma


class GeoAdaLNMLP(nn.Module):
    def __init__(self, input_dim: int, dim: int, depth: int, expansion: int, cond_dim: int) -> None:
        super().__init__()
        self.time_embedder = TimeEmbedder(dim // 4, 1000, expansion=4)
        self.cond_mapper = nn.Linear(cond_dim, dim)
        self.initial_mapper = nn.Linear(input_dim, dim)
        self.blocks = nn.ModuleList([AdaLNMLPBlock(dim, expansion) for _ in range(depth)])
        self.final_adaln = nn.Sequential(nn.SiLU(), nn.Linear(dim, dim * 2))
        self.final_ln = nn.LayerNorm(dim, elementwise_affine=False)
        self.final_linear = nn.Linear(dim, input_dim)

    def forward(self, y: torch.Tensor, gamma: torch.Tensor, emb: torch.Tensor) -> torch.Tensor:
        x = self.initial_mapper(y)
        cond = self.cond_mapper(emb) + self.time_embedder(gamma)
        for block in self.blocks:
            x = block(x, cond)
        g, mu = self.final_adaln(cond).chunk(2, dim=-1)
        return self.final_linear((1 + g) * self.final_ln(x) + mu)


def sigmoid_schedule(t: torch.Tensor) -> torch.Tensor:
    """SigmoidScheduler(-7, 3, tau=1) de PLONK : 1 → 0 quand t va de 0 à 1."""
    start, end, tau, clip_min = SCHEDULE
    v_start, v_end = torch.sigmoid(torch.tensor(start / tau)), torch.sigmoid(torch.tensor(end / tau))
    out = (-torch.sigmoid((t * (end - start) + start) / tau) + v_end) / (v_end - v_start)
    return out.clamp(min=clip_min, max=1.0)


# --- Nuage ------------------------------------------------------------------------------------------------
@dataclass
class Cloud:
    lat: np.ndarray  # degrés
    lon: np.ndarray
    ms: float


def haversine(lat1, lon1, lat2, lon2) -> np.ndarray:
    p1, p2, dl = np.radians(lat1), np.radians(lat2), np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


class PlonkCloud:
    def __init__(self, cfg: PlonkConfig, device: str, net: GeoAdaLNMLP | None = None) -> None:
        self.cfg, self.device = cfg, device
        self.net = (net or self._load(cfg.model, cfg.revision)).to(device).requires_grad_(False).eval()

    @staticmethod
    def _load(model_id: str, revision: str) -> GeoAdaLNMLP:
        # Import tardif : les tests fournissent leur réseau et n'ont jamais besoin de Hugging Face.
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file

        # Révision figée : un changement du dépôt ne modifie pas le modèle sans qu'on l'ait mesuré.
        # Poids en safetensors : aucun code exécuté au chargement (contrairement à pickle).
        params = json.loads(Path(hf_hub_download(model_id, "config.json", revision=revision)).read_text())
        net = GeoAdaLNMLP(**{k: int(params[k]) for k in ("input_dim", "dim", "depth", "expansion", "cond_dim")})
        net.load_state_dict(load_file(hf_hub_download(model_id, "model.safetensors", revision=revision)), strict=True)
        return net

    def sample(self, cls: torch.Tensor, points: int | None = None, steps: int | None = None, seed: int = 0) -> Cloud:
        """Tire `points` positions pour la vue dont `cls` est le jeton [CLS] StreetCLIP (même graine = même nuage)."""
        n, steps = points or self.cfg.points, steps or self.cfg.steps
        t0 = time.perf_counter()
        with torch.inference_mode():
            gen = torch.Generator(device=self.device).manual_seed(seed)
            x = torch.randn(n, 3, device=self.device, generator=gen)
            emb = cls.to(self.device, torch.float32).reshape(1, -1).expand(n, -1)
            gammas = sigmoid_schedule(1 - torch.arange(steps + 1, dtype=torch.float32) / steps).to(self.device)
            for g_now, g_next in zip(gammas[:-1], gammas[1:], strict=True):
                x = x + (g_next - g_now) * self.net(x, g_now.expand(n), emb)
                x = x / x.norm(dim=-1, keepdim=True)  # retour sur la sphère (geoopt Sphere.projx)
            lat = torch.rad2deg(torch.asin(x[:, 2].clamp(-1, 1)))
            lon = torch.rad2deg(torch.atan2(x[:, 1], x[:, 0]))
        if self.device.startswith("cuda"):
            torch.cuda.synchronize()
        return Cloud(lat.cpu().numpy(), lon.cpu().numpy(), (time.perf_counter() - t0) * 1000)


def _turn(o: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Produit vectoriel 2D de OA et OB : > 0 si O → A → B tourne à gauche."""
    return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))


def _hull(xy: np.ndarray) -> np.ndarray:
    """Enveloppe convexe (chaîne monotone d'Andrew), sommets dans le sens trigonométrique."""
    pts = np.unique(xy, axis=0)
    if len(pts) < 3:
        return pts

    def half(points):
        chain: list[np.ndarray] = []
        for p in points:
            while len(chain) >= 2 and _turn(chain[-2], chain[-1], p) <= 0:
                chain.pop()
            chain.append(p)
        return chain[:-1]

    return np.array(half(pts) + half(pts[::-1]))


def zones(lat: np.ndarray, lon: np.ndarray, share: float, link_km: float, min_part: float,
          codes: np.ndarray | None = None, round_km: float = 40.0) -> list[dict]:
    """Zones où la vue se trouve probablement : contours arrondis autour des points les plus denses.

    On garde la part `share` des points les plus entourés (voisins à moins de link_km), on les regroupe en
    zones séparées (deux points à moins de link_km sont dans la même), et on ne garde que les zones qui
    réunissent au moins `min_part` des points. part = points de la zone / points donnés.
    codes (pays de chaque point) : ajoute les deux pays principaux de chaque zone et leur part dans la zone.
    """
    n = len(lat)
    if n < 5:
        return []
    d = haversine(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    keep = np.argsort(-(d < link_km).sum(1), kind="stable")[: math.ceil(share * n)]
    near = d[np.ix_(keep, keep)] < link_km
    label = np.full(len(keep), -1)
    for start in range(len(keep)):  # composantes connexes (parcours en largeur)
        if label[start] >= 0:
            continue
        label[start], todo = start, [start]
        while todo:
            i = todo.pop()
            for j in np.nonzero(near[i] & (label < 0))[0]:
                label[j] = start
                todo.append(j)
    out = []
    for group in np.unique(label):
        idx = keep[label == group]
        if len(idx) < min_part * n:
            continue
        lat0, lon0 = float(lat[idx].mean()), float(lon[idx[0]])
        lon_u = (lon[idx] - lon0 + 180) % 360 - 180 + lon0  # sans saut à l'antiméridien
        kx, ky = 111.32 * math.cos(math.radians(lat0)), 110.57  # km par degré, projection locale
        xy = np.column_stack(((lon_u - lon0) * kx, (lat[idx] - lat0) * ky))
        angles = np.linspace(0, 2 * np.pi, 12, endpoint=False)
        ring = np.column_stack((np.cos(angles), np.sin(angles))) * round_km
        outline = _hull((_hull(xy)[:, None, :] + ring[None]).reshape(-1, 2))  # coins arrondis
        out.append({
            "polygon": [[round(lat0 + y / ky, 3), round(lon0 + x / kx, 3)] for x, y in outline],
            "part": round(len(idx) / n, 3),
            "width_km": round(float(np.ptp(xy[:, 0]))),
            "height_km": round(float(np.ptp(xy[:, 1]))),
            "countries": [] if codes is None else [
                [str(c), round(k / len(idx), 2)]
                for c, k in Counter(codes[idx]).most_common(2) if c and k / len(idx) >= 0.1
            ],
        })
    return sorted(out, key=lambda z: -z["part"])


def summarise(cloud: Cloud, countries: list[str], cfg: PlonkConfig) -> dict:
    """Message pour l'interface : zones probables, toutes et pays par pays (pour suivre une preuve).
    Les points eux-mêmes restent dans le moteur."""
    codes = np.array(countries, dtype=object)
    by_country = {}
    for c in sorted({c for c in countries if c}):
        mask = codes == c
        if mask.sum() >= cfg.zone_min_part * len(codes):
            found = zones(cloud.lat[mask], cloud.lon[mask], cfg.zone_share, cfg.zone_link_km, cfg.zone_min_part,
                          codes[mask])
            if found:
                by_country[c] = found
    return {
        "zones": zones(cloud.lat, cloud.lon, cfg.zone_share, cfg.zone_link_km, cfg.zone_min_part, codes),
        "zones_by_country": by_country,
        "ms": round(cloud.ms),
    }
