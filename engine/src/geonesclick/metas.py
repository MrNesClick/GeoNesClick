"""Metas database and tie-break between the candidate countries (level 1 "where to look").

A meta is a visual clue attached to one or more countries, filed in a category (poles,
road markings, alphabet…). Sources, from highest to lowest priority:
  "mes metas"  ~/.config/geonesclick/mes-metas.toml, entered or corrected by the player
  "amorce"     metas_amorce.toml (in the package): a seed of a few well-established facts, to be checked
The player settles each seed clue from the coach ("Right" / "Wrong"): the verdict is appended
to mes-metas.toml, as a verified copy ([[meta]]) or a dismissal ([[rejected]]).
The format does not depend on the source: a future import (Plonk It or other) will produce the same entries.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from importlib import resources
from itertools import combinations
from pathlib import Path
from typing import Any, Literal

import tomlkit

CATEGORIES: dict[str, str] = {
    "langue": "Langue et alphabet",
    "conduite": "Sens de circulation",
    "marquage": "Marquage au sol",
    "poteaux": "Poteaux",
    "bornes": "Bornes et délinéateurs",
    "plaques": "Plaques d'immatriculation",
    "panneaux": "Panneaux",
    "domaine": "Noms de domaine",
    "voiture": "Voiture et caméra Google",
    "vegetation": "Végétation et sol",
    "architecture": "Architecture",
    "autre": "Autres indices",
}


# Default instruction of each category, without naming a country: what to observe in the view.
# A meta can specify its own (field "look"), which then replaces this one.
CATEGORY_LOOK: dict[str, str] = {
    "langue": "les lettres et les mots des panneaux et des enseignes",
    "conduite": "le côté de la route où roulent et se garent les voitures",
    "marquage": "les lignes peintes sur la chaussée",
    "poteaux": "la forme et la matière des poteaux électriques",
    "bornes": "les bornes et les délinéateurs au bord de la route",
    "plaques": "la couleur et la forme des plaques d'immatriculation",
    "panneaux": "la forme et les couleurs des panneaux routiers",
    "domaine": "les adresses web sur les enseignes, les camions et les publicités",
    "voiture": "la voiture Google visible en bas de l'image",
    "vegetation": "les arbres, l'herbe et la couleur de la terre",
    "architecture": "les toits, les murs et les clôtures",
    "autre": "les détails inhabituels de la vue",
}
MAX_LOOKS = 2

# Weight of a category in the tie-break: how often the clue is visible in a view.
# A domain name separates as much as the language, but rarely appears: it counts for half.
CATEGORY_WEIGHT: dict[str, float] = {"domaine": 0.5}


class MetaError(ValueError):
    pass


class UserMetasError(MetaError):
    """mes-metas.toml is invalid: to be fixed by hand before any new verdict."""


@dataclass(frozen=True)
class Meta:
    category: str
    countries: frozenset[str]
    hint: str
    source: str
    verified: bool = False
    look: str = ""  # what to observe, without naming a country; empty = the category's instruction


@dataclass
class Hint:
    hint: str
    countries: list[str]
    source: str
    verified: bool


@dataclass
class LookFor:
    """A category to look at to tell the candidates apart, with each one's clues."""

    category: str
    label: str
    score: float
    looks: list[str]  # spoiler-free instructions: what to observe to decide
    hints: list[Hint] = field(default_factory=list)


def parse_metas(text: str, source: str, known_countries: Iterable[str] | None = None) -> list[Meta]:
    """Reads a TOML metas file ([[meta]] category, countries, hint, look, verified). Raises MetaError if invalid."""
    known = set(known_countries) if known_countries is not None else None
    metas = []
    for i, entry in enumerate(tomllib.loads(text).get("meta", [])):
        where = f"{source}, meta n°{i + 1}"
        category = entry.get("category")
        if category not in CATEGORIES:
            raise MetaError(f"{where} : catégorie inconnue {category!r} (attendu : {', '.join(CATEGORIES)})")
        countries = entry.get("countries")
        if not countries or not all(isinstance(c, str) and len(c) == 2 for c in countries):
            raise MetaError(f"{where} : « countries » doit lister des codes pays à 2 lettres")
        codes = frozenset(c.upper() for c in countries)
        if known is not None and (unknown := codes - known):
            raise MetaError(f"{where} : pays absents de la configuration : {', '.join(sorted(unknown))}")
        hint = str(entry.get("hint", "")).strip()
        if not hint:
            raise MetaError(f"{where} : « hint » vide")
        look = entry.get("look", "")
        if not isinstance(look, str):
            raise MetaError(f"{where} : « look » doit être un texte")
        metas.append(Meta(category, codes, hint, source, bool(entry.get("verified", False)), look.strip()))
    return metas


def parse_rejected(text: str, source: str) -> set[tuple[str, str]]:
    """Seed clues dismissed by the player: [[rejected]] category, hint."""
    rejected = set()
    for i, entry in enumerate(tomllib.loads(text).get("rejected", [])):
        category, hint = entry.get("category"), entry.get("hint")
        if category not in CATEGORIES or not isinstance(hint, str) or not hint.strip():
            raise MetaError(f"{source}, mise à l'écart n°{i + 1} : « category » et « hint » requis")
        rejected.add((category, hint.strip()))
    return rejected


def seed_metas(known_countries: Iterable[str]) -> list[Meta]:
    """The seed, reduced to the configured countries: removing a country from the list must not break everything."""
    known = frozenset(known_countries)
    seed = parse_metas(resources.files(__package__).joinpath("metas_amorce.toml").read_text(), "amorce")
    return [replace(m, countries=m.countries & known) for m in seed if m.countries & known]


def load_metas(user_file: Path | None, include_seed: bool, known_countries: Iterable[str]) -> list[Meta]:
    known = list(known_countries)
    metas: list[Meta] = []
    rejected: set[tuple[str, str]] = set()
    if user_file and user_file.exists():
        text = user_file.read_text()
        metas += parse_metas(text, "mes metas", known)
        rejected = parse_rejected(text, "mes metas")
    if include_seed:
        metas += [m for m in seed_metas(known) if (m.category, m.hint) not in rejected]
    return metas


def judge_seed(
    user_file: Path, category: str, hint: str, verdict: Literal["right", "wrong"], known_countries: Iterable[str]
) -> None:
    """Saves the player's verdict on a seed clue, at the end of mes-metas.toml.

    "right": verified copy of the clue, which then becomes "your meta". "wrong": dismissal.
    The file is never rewritten (its comments are kept); if it is invalid, nothing is written.
    """
    known = list(known_countries)
    meta = next((m for m in seed_metas(known) if m.category == category and m.hint == hint), None)
    if meta is None:
        raise MetaError("indice inconnu dans l'amorce")
    text = user_file.read_text() if user_file.exists() else ""
    try:
        mine, rejected = parse_metas(text, "mes metas", known), parse_rejected(text, "mes metas")
    except ValueError as exc:  # MetaError, or unreadable TOML
        raise UserMetasError(f"mes-metas.toml invalide, corrige-le d'abord : {exc}") from exc
    if verdict == "right":
        entry = {"category": meta.category, "countries": sorted(meta.countries), "hint": meta.hint}
        if meta.look:
            entry["look"] = meta.look
        block = _array_of_tables("meta", entry | {"verified": True})
        done = any(m.category == category and m.hint == hint for m in mine)
    else:
        block = _array_of_tables("rejected", {"category": meta.category, "hint": meta.hint})
        done = (category, hint) in rejected
    if done:  # verdict already saved: nothing to add
        return
    new = text + ("\n" if text and not text.endswith("\n") else "") + "\n" + block
    user_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = user_file.with_suffix(".tmp")
    tmp.write_text(new)
    tmp.replace(user_file)  # atomic write


def tiebreak(
    candidates: list[tuple[str, float]],
    metas: list[Meta],
    max_categories: int = 3,
    *,
    looks: dict[str, str] | None = None,
    weights: dict[str, float] | None = None,
    max_looks: int = MAX_LOOKS,
) -> list[LookFor]:
    """Categories that best tell the candidates apart [(country code, probability)].

    For each category, each candidate has a "profile": the set of clues that concern it.
    Score = sum, over the pairs of candidates whose two profiles are known and different, of the product
    of their probabilities. A category that separates the two favourites therefore weighs more than one that
    separates two outsiders; a candidate without a known clue brings nothing.
    looks and weights replace, category by category, CATEGORY_LOOK and CATEGORY_WEIGHT; max_looks = 0
    removes the instructions.
    """
    looks = CATEGORY_LOOK | (looks or {})
    weights = CATEGORY_WEIGHT | (weights or {})
    probs = dict(candidates)
    results = []
    for category, label in CATEGORIES.items():
        in_cat = [m for m in metas if m.category == category and m.countries & probs.keys()]
        if not in_cat:
            continue
        profile = {c: frozenset(m.hint for m in in_cat if c in m.countries) for c in probs}
        score = weights.get(category, 1.0) * sum(
            probs[a] * probs[b]
            for a, b in combinations(probs, 2)
            if profile[a] and profile[b] and profile[a] != profile[b]
        )
        if score <= 0:
            continue
        hints = [
            Hint(
                m.hint,
                [c for c in probs if c in m.countries],  # in order of probability
                m.source,
                m.verified,
            )
            for m in in_cat
        ]
        # "mes metas" first, then the clues of the most likely candidates.
        hints.sort(key=lambda h: (h.source != "mes metas", -max(probs[c] for c in h.countries)))
        hints = _dedupe(hints)
        by_hint = {m.hint: m.look for m in in_cat}
        own = list(dict.fromkeys(by_hint[h.hint] for h in hints if by_hint[h.hint]))
        shown = (own or [looks[category]])[:max_looks]
        results.append(LookFor(category, label, round(score, 4), shown, hints))
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:max_categories]


def _array_of_tables(name: str, entry: dict[str, Any]) -> str:
    """A TOML block [[name]] (strings correctly escaped)."""
    table = tomlkit.table()
    table.update(entry)
    doc = tomlkit.document()
    doc[name] = tomlkit.aot()
    doc[name].append(table)
    return tomlkit.dumps(doc)


def _dedupe(hints: list[Hint]) -> list[Hint]:
    seen, out = set(), []
    for h in hints:
        if h.hint not in seen:
            seen.add(h.hint)
            out.append(h)
    return out


def select_candidates(
    scores: list[tuple[str, float]], min_probability: float, max_candidates: int
) -> list[tuple[str, float]]:
    """Keeps the plausible candidates: at least 2, at most max_candidates, above the threshold otherwise."""
    kept = [s for s in scores if s[1] >= min_probability][:max_candidates]
    return kept if len(kept) >= 2 else scores[:2]
