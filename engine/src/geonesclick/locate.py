"""Position estimated from the places read on your marks, and from a direction sign's distances.

A sign "Гърмен 3, Гоце Делчев 10, Благоевград 109, София 219" gives distances BY ROAD: the straight-line
distance is shorter (detour coefficient, ~1.2 to 1.5 depending on the terrain). We look for the point whose
straight-line distances best match the distances read divided by that coefficient, in RELATIVE error: the
nearby places (3 and 10 km) pin the point, the distant ones (109, 219 km, mountain roads) confirm it.

Measured on 2026-11-07 on this sign: 41.58° N, 23.82–23.85° E (2 to 3 km from Гърмен) depending on the coefficient
(1.0 to 1.4); hence the announced radius, which covers this spread.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import replace
from typing import Any

from .evidence import Evidence

EARTH_KM = 6371.0
DETOUR = 1.3  # road / straight line, central value (the radius covers 1.15 to 1.45)
DETOUR_RANGE = (1.15, 1.45)
MAX_COMBOS = 243  # namesakes to decide between: 3 candidates for 5 places at most
# Consistency (decided with the user on 2026-11-07): the AI sometimes misreads a digit ("6" then "8" on the same
# mark). At the point found, each straight-line distance must stay below the road distance (+1 km for the sign's
# rounding) and above road / MAX_DETOUR (−1 km). Otherwise: no point, only what always stays true.
MAX_DETOUR = 1.8


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(h)))


def _cost(p: tuple[float, float], anchors: list[tuple[tuple[float, float], float]], detour: float) -> float:
    return sum(((haversine(p, c) - d / detour) / (d / detour + 2)) ** 2 for c, d in anchors)


def _solve(anchors: list[tuple[tuple[float, float], float]], detour: float) -> tuple[tuple[float, float], float]:
    """Search by successive grids around the closest place (no optimisation dependency)."""
    (lat, lon), nearest = min(anchors, key=lambda a: a[1])
    span = max(0.05, nearest / detour / 111 * 2.5)  # degrees: the grid widely covers the closest place
    for _ in range(7):
        cells = ((lat + span * i / 20, lon + span * j / 20 / max(0.2, math.cos(math.radians(lat))))
                 for i in range(-20, 21) for j in range(-20, 21))
        lat, lon = min(cells, key=lambda p: _cost(p, anchors, detour))
        span /= 4
    return (lat, lon), _cost((lat, lon), anchors, detour)


def keep_nearby(marks: list[tuple[int, list[Evidence]]], max_km: float
                ) -> tuple[list[tuple[int, list[Evidence]]], list[dict[str, Any]]]:
    """The places read during a round are neighbours: the largest group is kept, the rest ruled out.

    Measured on 2026-11-07: "LAAS" (a French village missing from the directory) landed on Lasa, in Italy, ~950 km
    from Orthez read in the same round, and wrongly contradicted France. We look for the namesake that has the most
    places read within max_km; the places without any namesake within this radius are ignored (returned separately,
    for display). Without a group of at least two places, nothing is ruled out: the contradiction stays visible.
    """
    places = [e for _, found in marks for e in found if e.kind == "lieu" and e.points]
    best, support = None, 1
    for e in places:
        for p in e.points:
            near = sum(1 for o in places if any(haversine(p[:2], q[:2]) <= max_km for q in o.points))
            if near > support:
                best, support = p, near
    if best is None:
        return marks, []
    kept, ignored = [], []
    for n, found in marks:
        mine = []
        for e in found:
            if e.kind == "lieu" and e.points:
                # Namesakes of the group, closest first: Laàs (64) at 13 km from Orthez before Laas (32) at 87 km.
                close = sorted((q for q in e.points if haversine(best[:2], q[:2]) <= max_km),
                               key=lambda q: haversine(best[:2], q[:2]))
                if not close:
                    ignored.append({"n": n, "value": e.value, "label": e.label, "countries": e.countries})
                    continue
                label = close[0][3] if len(close[0]) > 3 else e.label
                e = replace(e, points=close, countries=sorted({q[2] for q in close}), label=label)
            mine.append(e)
        kept.append((n, mine))
    return kept, ignored


def _coherent(p: tuple[float, float], anchors: list[tuple[tuple[float, float], float]]) -> bool:
    """Each straight-line distance compatible with the road distance read (sign rounding: 1 km)."""
    return all(km / MAX_DETOUR - 1 <= haversine(p, c) <= km + 1 for c, km in anchors)


def locate(places: list[tuple[int, Evidence]], country: str) -> dict[str, Any] | None:
    """Position estimated from the places cited (mark number, "lieu" proof) in the country kept.

    - several consistent distances: a point and a radius ("point");
    - several inconsistent distances (misread digit): the view is at most d km from the closest place
      ("rough", always true: the road is never shorter than the straight line), and the places involved;
    - a single distance: a circle around the place ("ring");
    - no distance: the places only ("places"), the view is around them.
    """
    found = []
    for n, e in places:
        points = [(float(p[0]), float(p[1])) for p in e.points if p[2] == country]
        if points:
            found.append((n, e, points[:3]))
    if not found:
        return None
    with_km = [(n, e, pts) for n, e, pts in found if e.km]
    # Namesakes: the combination most consistent with the distances (otherwise the most populous, ranked first).
    best_combo = [pts[0] for _, _, pts in with_km]
    if 1 < len(with_km) and math.prod(len(pts) for _, _, pts in with_km) <= MAX_COMBOS:
        best_combo = min(itertools.product(*(pts for _, _, pts in with_km)),
                         key=lambda combo: _solve(list(zip(combo, [e.km for _, e, _ in with_km], strict=True)),
                                                  DETOUR)[1])
    chosen = {id(e): p for (_, e, _), p in zip(with_km, best_combo, strict=True)}
    def name_at(e: Evidence, at: tuple[float, float]) -> str:  # GeoNames name of the namesake kept
        return next((str(p[3]) for p in e.points if len(p) > 3 and (float(p[0]), float(p[1])) == at), e.label)

    listed = []
    for n, e, pts in found:
        at = chosen.get(id(e), pts[0])
        listed.append({"n": n, "name": e.value, "label": name_at(e, at), "km": e.km,
                       "lat": round(at[0], 5), "lon": round(at[1], 5)})
    if not with_km:
        return {"kind": "places", "places": listed}
    anchors = [(chosen[id(e)], float(e.km)) for _, e, _ in with_km]
    if len(anchors) == 1:
        (lat, lon), km = anchors[0]
        return {"kind": "ring", "lat": lat, "lon": lon, "radius_km": round(km / DETOUR, 1),
                "spread_km": round(km / DETOUR_RANGE[0] - km / DETOUR_RANGE[1], 1), "places": listed}
    (lat, lon), _ = _solve(anchors, DETOUR)
    if not _coherent((lat, lon), anchors):
        # The wrong digit pulls the point towards it and makes everything inconsistent: we look for the distance whose
        # removal makes the others consistent. A single one: that is the one to check; otherwise, all are in doubt.
        culprits = [i for i in range(len(anchors)) if len(anchors) > 2 and _coherent(
            _solve(anchors[:i] + anchors[i + 1:], DETOUR)[0], anchors[:i] + anchors[i + 1:])]
        suspects = culprits if len(culprits) == 1 else range(len(anchors))
        doubtful = [{"n": with_km[i][0], "name": with_km[i][1].value, "km": with_km[i][1].km} for i in suspects]
        (near_lat, near_lon), near_km = min(anchors, key=lambda a: a[1])
        return {"kind": "rough", "lat": near_lat, "lon": near_lon, "radius_km": near_km + 1, "doubtful": doubtful,
                "places": listed}
    low, _ = _solve(anchors, DETOUR_RANGE[0])
    high, _ = _solve(anchors, DETOUR_RANGE[1])
    nearest = min(km for _, km in anchors)
    radius = max(2.0, 0.3 * nearest / DETOUR, haversine(low, high) / 2 + 0.5)  # no ground truth: caution
    return {"kind": "point", "lat": round(lat, 5), "lon": round(lon, 5), "radius_km": round(radius, 1),
            "places": listed}
