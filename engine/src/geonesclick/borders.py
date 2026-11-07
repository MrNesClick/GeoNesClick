"""Frontières des pays : pays d'un point GPS (filtrage du nuage PLONK) et contours pour la carte du coach.

Données : Natural Earth 1:50m, Admin 0 – Countries, v5.1.2 (domaine public, https://www.naturalearthdata.com),
fichier data/ne_50m_admin_0_countries.geojson. Le code pays vient de ISO_A2_EH, qui corrige les « -99 »
de ISO_A2 (France, Norvège) ; les territoires sans code (-99) sont ignorés.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np

DATA_FILE = "ne_50m_admin_0_countries.geojson"


@dataclass(frozen=True)
class Polygon:
    outer: np.ndarray  # (n, 2) : lon, lat
    holes: tuple[np.ndarray, ...]  # enclaves (le Lesotho dans l'Afrique du Sud…)


@dataclass(frozen=True)
class Country:
    code: str
    bbox: tuple[float, float, float, float]  # lon min, lat min, lon max, lat max
    polygons: tuple[Polygon, ...]


def _inside(ring: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Test du rayon (règle pair-impair), vectorisé sur les points."""
    x0, y0 = ring[:-1, 0][:, None], ring[:-1, 1][:, None]
    x1, y1 = ring[1:, 0][:, None], ring[1:, 1][:, None]
    crosses = (y0 > lat) != (y1 > lat)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_at = x0 + (lat - y0) * (x1 - x0) / (y1 - y0)
    return ((crosses & (lon < x_at)).sum(0) % 2) == 1


class Borders:
    def __init__(self, path: Path | None = None) -> None:
        raw = path.read_text() if path else resources.files(__package__).joinpath("data", DATA_FILE).read_text()
        self.countries: list[Country] = []
        features = []
        for feat in json.loads(raw)["features"]:
            code = str(feat["properties"].get("ISO_A2_EH") or feat["properties"].get("ISO_A2") or "").upper()
            geom = feat.get("geometry") or {}
            if len(code) != 2 or not code.isalpha() or geom.get("type") not in ("Polygon", "MultiPolygon"):
                continue
            parts = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
            polys = tuple(
                Polygon(np.asarray(p[0], dtype=np.float64), tuple(np.asarray(h, dtype=np.float64) for h in p[1:]))
                for p in parts
            )
            pts = np.concatenate([p.outer for p in polys])
            lo, hi = pts.min(0), pts.max(0)
            self.countries.append(Country(code, (lo[0], lo[1], hi[0], hi[1]), polys))
            features.append({"type": "Feature", "properties": {"code": code}, "geometry": geom})
        # Contours allégés pour l'interface : seul le code est gardé (le fichier d'origine porte ~100 champs).
        self.geojson: dict[str, Any] = {"type": "FeatureCollection", "features": features}

    def countries_of(self, lat: np.ndarray, lon: np.ndarray) -> list[str]:
        """Code du pays de chaque point ("" en mer ou hors des pays connus)."""
        lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
        found = np.full(lat.shape, "", dtype=object)
        for country in self.countries:
            x0, y0, x1, y1 = country.bbox
            todo = (found == "") & (lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1)
            if not todo.any():
                continue
            idx = np.nonzero(todo)[0]
            hit = np.zeros(idx.shape, dtype=bool)
            for poly in country.polygons:
                inside = _inside(poly.outer, lon[idx], lat[idx])
                for hole in poly.holes:
                    inside &= ~_inside(hole, lon[idx], lat[idx])
                hit |= inside
            found[idx[hit]] = country.code
        return found.tolist()
