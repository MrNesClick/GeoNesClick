"""Banc de relecture : rejoue chaque manche du jeu de test dans les règles ACTUELLES du coach, et compte ce qui est
juste et surtout les FAUSSES CERTITUDES (décidé avec l'utilisateur le 2026-11-07 : on ne change une règle ou un
seuil que si ce banc s'améliore sur l'ensemble, sans casser une manche qui marchait ; cible : zéro fausse
certitude, quitte à dire « je ne sais pas » plus souvent).

Corpus : dataset/rounds/<id>.json (le texte de tes marques, enregistré par « C'était où ? ») et la vérité de
labels.toml (pays, et position + région si tu as collé le lien Google Maps). Aucun réseau : l'index des lieux local
(avec les villages déjà téléchargés) et le même code que le moteur (marks_engine.conclude, LocksMixin._candidates).

    cd engine && .venv/bin/python -m geonesclick.bench          # tableau + résumé
    cd engine && .venv/bin/python -m geonesclick.bench --json   # pour comparer deux versions
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .config import Config, load_config
from .dataset import Dataset, Label
from .evidence import as_dict
from .locate import haversine
from .locks_engine import LocksMixin
from .marks_engine import MarksMixin, conclude
from .places import DB_NAME, VERSION, Places


@dataclass
class Round:
    id: str
    truth: str  # pays réel
    marks: int
    country: str  # pays conclu par les marques
    level: str  # certain, probable ou ""
    verdict: str  # juste, FAUX, aucun
    region: str  # région fixée par le coach : juste, FAUSSE, aucune, ? (vérité inconnue)
    position: str  # point, rough, ring, places ou ""
    error_km: float | None  # distance du centre de la position estimée au vrai lieu
    promise: str  # le vrai lieu est-il dans le rayon annoncé ? tenue, ROMPUE, ?
    missing: str  # villages du pays réel absents de l'index (les télécharger améliore la relecture)


def rules_of(cfg: Config, places: Places | None) -> SimpleNamespace:
    """Juste ce dont les règles du moteur ont besoin (configuration et index), sans serveur."""
    return SimpleNamespace(cfg=cfg, places=places)


def open_places(cfg: Config) -> Places | None:
    folder = cfg.rules.places_path
    if not (folder / DB_NAME).exists():
        return None
    places = Places(folder / DB_NAME)
    for detail in sorted(folder.glob(f"detail-*-{VERSION}.sqlite")):
        places.add_detail(detail.name.split("-")[1], detail)
    return places


def replay(label: Label, data: dict[str, Any], cfg: Config, places: Places | None) -> Round:
    rules = rules_of(cfg, places)
    done = [(m["n"], as_dict(MarksMixin.evidence_of(rules, m.get("text") or []))) for m in data.get("marks", [])]
    c = conclude(done, [tuple(s) for s in data.get("scores", [])], cfg.rules)
    v, loc = c.verdict, c.result["location"]
    _, region, _, _ = LocksMixin._candidates(rules, v, c.cited, loc, c.target)
    verdict = "aucun" if not v.country else "juste" if v.country == label.country else "FAUX"
    region_ok = "aucune" if region is None else "?" if not label.region else (
        "juste" if region.region == label.region else "FAUSSE")
    error, promise = None, "?"
    if loc and label.lat is not None and label.lon is not None:
        truth = (label.lat, label.lon)
        if "lat" in loc:
            error = haversine(truth, (loc["lat"], loc["lon"]))
            if loc["kind"] in ("point", "rough"):
                promise = "tenue" if error <= loc["radius_km"] else "ROMPUE"
            elif loc["kind"] == "ring":  # sur le cercle, à l'écart annoncé près
                promise = "tenue" if abs(error - loc["radius_km"]) <= loc["spread_km"] / 2 + 2 else "ROMPUE"
        elif loc["places"]:
            error = min(haversine(truth, (p["lat"], p["lon"])) for p in loc["places"])
    missing = "" if places is None or label.country in places.details else label.country
    return Round(label.file.removeprefix("capture-").removesuffix(".png"), label.country, len(done), v.country,
                 v.level, verdict, region_ok, loc["kind"] if loc else "", round(error, 1) if error is not None else None,
                 promise, missing)


def run(cfg: Config) -> list[Round]:
    dataset, places = Dataset(cfg.dataset.path), open_places(cfg)
    out = []
    for label in dataset.labels():
        path = dataset.rounds / f"{label.file.removeprefix('capture-').removesuffix('.png')}.json"
        if path.exists():
            out.append(replay(label, json.loads(path.read_text()), cfg, places))
    return out


def summary(rounds: list[Round]) -> dict[str, Any]:
    with_marks = [r for r in rounds if r.marks]
    count = lambda pred: sum(1 for r in with_marks if pred(r))  # noqa: E731
    return {
        "manches": len(rounds), "avec marques": len(with_marks),
        "FAUSSES CERTITUDES": count(lambda r: r.level == "certain" and r.verdict == "FAUX")
        + count(lambda r: r.region == "FAUSSE") + count(lambda r: r.promise == "ROMPUE"),
        "pays certain juste": count(lambda r: r.level == "certain" and r.verdict == "juste"),
        "pays certain FAUX": count(lambda r: r.level == "certain" and r.verdict == "FAUX"),
        "pays très probable juste/faux": f"{count(lambda r: r.level == 'probable' and r.verdict == 'juste')}"
                                         f"/{count(lambda r: r.level == 'probable' and r.verdict == 'FAUX')}",
        "sans conclusion": count(lambda r: r.verdict == "aucun"),
        "région juste/FAUSSE/aucune": f"{count(lambda r: r.region == 'juste')}/{count(lambda r: r.region == 'FAUSSE')}"
                                      f"/{count(lambda r: r.region == 'aucune')}",
        "rayon tenu/ROMPU": f"{count(lambda r: r.promise == 'tenue')}/{count(lambda r: r.promise == 'ROMPUE')}",
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    rounds = run(load_config())
    if "--json" in argv:
        print(json.dumps({"rounds": [asdict(r) for r in rounds], "summary": summary(rounds)}, ensure_ascii=False,
                         indent=1))
        return 0
    if not rounds:
        print("Corpus vide : remplis « C'était où ? » après tes manches (avec le lien Google Maps du vrai lieu).")
        return 0
    head = f"{'manche':20} {'vrai':4} {'marq':>4} {'conclu':8} {'pays':6} {'région':7} {'position':8} {'km':>7} rayon"
    print(head)
    for r in rounds:
        km = "" if r.error_km is None else f"{r.error_km:7.1f}"
        print(f"{r.id:20} {r.truth:4} {r.marks:4} {(r.country + ' ' + r.level)[:8]:8} {r.verdict:6} {r.region:7} "
              f"{r.position:8} {km:>7} {r.promise}{'  (villages ' + r.missing + ' absents)' if r.missing else ''}")
    print()
    for key, value in summary(rounds).items():
        print(f"{key:32} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
