"""What the coach's map shows, against the true place: the PLONK zones drawn by the coach.

Same code as the engine (StreetCLIP [CLS] token, PlonkCloud.sample, local borders, summarise, configured points and
steps), on the captures of the test set whose label holds the coordinates of the true place. Two cases, as on the
map (app/src/engine.ts, visibleZones):
- no leading country: all the zones;
- the right country leads (proven or read): the zones of that country only.
For each: is the true place inside a zone, how far from the nearest zone, and how big the zones are.

    cd engine && .venv/bin/python spikes/map_bench.py
"""

from __future__ import annotations

import math
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image

from geonesclick.borders import Borders
from geonesclick.config import load_config
from geonesclick.plonk import PlonkCloud, summarise
from geonesclick.streetclip import StreetClip

DATASET = Path(__file__).resolve().parent.parent / "dataset"


def local_xy(lat: float, lon: float, points: list[list[float]]) -> np.ndarray:
    """Points as km east and north of (lat, lon): equirectangular projection, exact enough near the place."""
    p = np.array(points, dtype=float)
    dlon = (p[:, 1] - lon + 180) % 360 - 180
    return np.column_stack((dlon * 111.32 * math.cos(math.radians(lat)), (p[:, 0] - lat) * 110.57))


def inside(xy: np.ndarray) -> bool:
    """Is the origin inside the polygon (ray casting)?"""
    hit = False
    for (x1, y1), (x2, y2) in zip(xy, np.roll(xy, -1, axis=0), strict=True):
        if (y1 > 0) != (y2 > 0) and 0 < x1 + (0 - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def distance(xy: np.ndarray) -> float:
    """Distance from the origin to the polygon (0 inside), km."""
    if inside(xy):
        return 0.0
    best = math.inf
    for a, b in zip(xy, np.roll(xy, -1, axis=0), strict=True):
        ab = b - a
        t = float(np.clip(-a @ ab / max(ab @ ab, 1e-9), 0, 1))
        best = min(best, float(np.linalg.norm(a + t * ab)))
    return best


def area(xy: np.ndarray) -> float:
    x, y = xy[:, 0], xy[:, 1]
    return abs(float(x @ np.roll(y, -1) - y @ np.roll(x, -1))) / 2


def measure(zones: list[dict], lat: float, lon: float) -> tuple[float, float] | None:
    """(distance from the true place to the nearest zone, total area in km²), None without any zone."""
    if not zones:
        return None
    near = min(distance(local_xy(lat, lon, z["polygon"])) for z in zones)
    # The area in a projection centred on the zone itself: a zone far from the place lies at another latitude.
    return near, sum(area(local_xy(*z["polygon"][0], z["polygon"])) for z in zones)


def report(name: str, rows: list[tuple[float, float] | None], n: int) -> None:
    got = [r for r in rows if r is not None]
    if not got:
        print(f"  {name:<28} no zone in {n}/{n}")
        return
    km, a = np.array([r[0] for r in got]), np.array([r[1] for r in got])
    print(f"  {name:<28} inside {int((km == 0).sum())}/{n} | within 100 km {int((km <= 100).sum())}/{n}"
          f" | median distance {np.median(km):.0f} km | median area {np.median(a):,.0f} km²"
          f" (side of the same square {math.sqrt(np.median(a)):.0f} km) | no zone {n - len(got)}/{n}")


def main() -> None:
    cfg = load_config()
    clip, borders = StreetClip(cfg.streetclip), Borders()
    plonk = PlonkCloud(cfg.plonk, clip.device)
    labels = [c for c in tomllib.loads((DATASET / "labels.toml").read_text())["capture"] if "lat" in c]
    every, right = [], []
    for item in labels:
        img = Image.open(DATASET / "images" / item["file"]).convert("RGB")
        _, _, _, cls = clip.analyse(img)
        cloud = plonk.sample(cls)
        message = summarise(cloud, borders.countries_of(cloud.lat, cloud.lon), cfg.plonk)
        lat, lon, truth = item["lat"], item["lon"], item["country"]
        every.append(measure(message["zones"], lat, lon))
        right.append(measure(message["zones_by_country"].get(truth, []), lat, lon))
        show = [f"{r[0]:.0f} km, {r[1]:,.0f} km²" if r else "no zone" for r in (every[-1], right[-1])]
        print(f"{item['file']}  {truth}  all zones: {show[0]:<24} {truth} zones: {show[1]}")
    n = len(labels)
    print(f"\nOver {n} captures with the true place ({cfg.plonk.points} points, {cfg.plonk.steps} steps):")
    report("all zones (no country)", every, n)
    report("zones of the right country", right, n)


if __name__ == "__main__":
    main()
