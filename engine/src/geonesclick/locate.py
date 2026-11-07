"""Position estimée à partir des lieux lus sur tes marques, et des distances d'un panneau directionnel.

Un panneau « Гърмен 3, Гоце Делчев 10, Благоевград 109, София 219 » donne des distances PAR LA ROUTE : la distance
à vol d'oiseau est plus courte (coefficient de détour, ~1,2 à 1,5 selon le relief). On cherche le point dont les
distances à vol d'oiseau collent le mieux aux distances lues divisées par ce coefficient, en erreur RELATIVE : les
lieux proches (3 et 10 km) fixent le point, les lointains (109, 219 km, routes de montagne) le confirment.

Mesuré le 2026-11-07 sur ce panneau : 41,58° N, 23,82–23,85° E (2 à 3 km de Гърмен) selon le coefficient (1,0 à
1,4) ; d'où le rayon annoncé, qui couvre cet écart.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import replace
from typing import Any

from .evidence import Evidence

EARTH_KM = 6371.0
DETOUR = 1.3  # route / vol d'oiseau, valeur centrale (le rayon couvre 1,15 à 1,45)
DETOUR_RANGE = (1.15, 1.45)
MAX_COMBOS = 243  # homonymes à départager : 3 candidats pour 5 lieux au plus
# Cohérence (décidée avec lui le 2026-11-07) : l'IA lit parfois mal un chiffre (« 6 » puis « 8 » sur la même marque).
# Au point trouvé, chaque distance à vol d'oiseau doit rester sous la distance par la route (+1 km d'arrondi du
# panneau) et au-dessus de route / MAX_DETOUR (−1 km). Sinon : pas de point, seulement ce qui reste toujours vrai.
MAX_DETOUR = 1.8


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(h)))


def _cost(p: tuple[float, float], anchors: list[tuple[tuple[float, float], float]], detour: float) -> float:
    return sum(((haversine(p, c) - d / detour) / (d / detour + 2)) ** 2 for c, d in anchors)


def _solve(anchors: list[tuple[tuple[float, float], float]], detour: float) -> tuple[tuple[float, float], float]:
    """Recherche par grilles successives autour du lieu le plus proche (pas de dépendance d'optimisation)."""
    (lat, lon), nearest = min(anchors, key=lambda a: a[1])
    span = max(0.05, nearest / detour / 111 * 2.5)  # degrés : la grille couvre largement le lieu le plus proche
    for _ in range(7):
        cells = ((lat + span * i / 20, lon + span * j / 20 / max(0.2, math.cos(math.radians(lat))))
                 for i in range(-20, 21) for j in range(-20, 21))
        lat, lon = min(cells, key=lambda p: _cost(p, anchors, detour))
        span /= 4
    return (lat, lon), _cost((lat, lon), anchors, detour)


def keep_nearby(marks: list[tuple[int, list[Evidence]]], max_km: float
                ) -> tuple[list[tuple[int, list[Evidence]]], list[dict[str, Any]]]:
    """Les lieux lus pendant une manche sont voisins : on garde le groupe le plus fourni, on écarte le reste.

    Mesuré le 2026-11-07 : « LAAS » (village français absent du répertoire) tombait sur Lasa, en Italie, à ~950 km
    d'Orthez lu sur la même manche, et contredisait à tort la France. On cherche l'homonyme qui a le plus de lieux
    lus à moins de max_km ; les lieux sans aucun homonyme dans ce rayon sont ignorés (renvoyés à part, pour
    l'affichage). Sans groupe d'au moins deux lieux, rien n'est écarté : la contradiction reste visible.
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
                # Homonymes du groupe, le plus proche d'abord : Laàs (64) à 13 km d'Orthez avant Laas (32) à 87 km.
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
    """Chaque distance à vol d'oiseau compatible avec la distance par la route lue (arrondi du panneau : 1 km)."""
    return all(km / MAX_DETOUR - 1 <= haversine(p, c) <= km + 1 for c, km in anchors)


def locate(places: list[tuple[int, Evidence]], country: str) -> dict[str, Any] | None:
    """Position estimée d'après les lieux cités (numéro de marque, preuve « lieu ») dans le pays retenu.

    - plusieurs distances cohérentes : un point et un rayon (« point ») ;
    - plusieurs distances incohérentes (chiffre mal lu) : la vue est au plus à d km du lieu le plus proche
      (« rough », toujours vrai : la route n'est jamais plus courte que le vol d'oiseau), et les lieux en cause ;
    - une seule distance : un cercle autour du lieu (« ring ») ;
    - aucune distance : les lieux seulement (« places »), la vue est dans leurs parages.
    """
    found = []
    for n, e in places:
        points = [(float(p[0]), float(p[1])) for p in e.points if p[2] == country]
        if points:
            found.append((n, e, points[:3]))
    if not found:
        return None
    with_km = [(n, e, pts) for n, e, pts in found if e.km]
    # Homonymes : la combinaison la plus cohérente avec les distances (sinon, le plus peuplé, rangé en premier).
    best_combo = [pts[0] for _, _, pts in with_km]
    if 1 < len(with_km) and math.prod(len(pts) for _, _, pts in with_km) <= MAX_COMBOS:
        best_combo = min(itertools.product(*(pts for _, _, pts in with_km)),
                         key=lambda combo: _solve(list(zip(combo, [e.km for _, e, _ in with_km], strict=True)),
                                                  DETOUR)[1])
    chosen = {id(e): p for (_, e, _), p in zip(with_km, best_combo, strict=True)}
    def name_at(e: Evidence, at: tuple[float, float]) -> str:  # nom GeoNames de l'homonyme retenu
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
        # Le chiffre faux tire le point vers lui et rend tout incohérent : on cherche la distance dont le retrait
        # rend les autres cohérentes. Une seule : c'est elle qu'il faut vérifier ; sinon, toutes sont en doute.
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
    radius = max(2.0, 0.3 * nearest / DETOUR, haversine(low, high) / 2 + 0.5)  # pas de vérité terrain : prudence
    return {"kind": "point", "lat": round(lat, 5), "lon": round(lon, 5), "radius_km": round(radius, 1),
            "places": listed}
