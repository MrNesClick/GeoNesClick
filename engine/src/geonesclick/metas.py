"""Metas database and tie-break between the candidate countries (level 1 "where to look").

A meta is a visual clue attached to one or more countries, filed in a category (poles,
road markings, alphabet…). Sources, from highest to lowest priority:
  "mine"  ~/.config/geonesclick/my-metas.toml, entered or corrected by the player
  "seed"  metas_amorce.toml (in the package): a seed of a few well-established facts, to be checked
The player settles each seed clue from the coach ("Right" / "Wrong"): the verdict is appended
to my-metas.toml, as a verified copy ([[meta]] with seed = <id>) or a dismissal ([[rejected]] seed = <id>).
The seed's texts are English; they are shown in the coach's language (catalogs: seed.<id>.hint, seed.<id>.look).
The format does not depend on the source: a future import (Plonk It or other) will produce the same entries.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from importlib import resources
from itertools import combinations
from pathlib import Path
from typing import Any, Literal

import tomlkit

from .i18n import catalog, t

# Categories, in display order; label: category.<id>, default instruction: category.<id>.look (catalogs).
CATEGORIES: tuple[str, ...] = ("language", "driving", "road_lines", "poles", "bollards", "plates", "signs",
                               "domains", "car", "vegetation", "architecture", "other")
MAX_LOOKS = 2

# Weight of a category in the tie-break: how often the clue is visible in a view.
# A domain name separates as much as the language, but rarely appears: it counts for half.
CATEGORY_WEIGHT: dict[str, float] = {"domains": 0.5}

MINE, SEED = "mine", "seed"  # sources of a meta
SEED_ID = re.compile(r"[a-z0-9_]{1,40}")


class MetaError(ValueError):
    pass


class UserMetasError(MetaError):
    """my-metas.toml is invalid: to be fixed by hand before any new verdict."""


@dataclass(frozen=True)
class Meta:
    category: str
    countries: frozenset[str]
    hint: str
    source: str
    verified: bool = False
    look: str = ""  # what to observe, without naming a country; empty = the category's instruction
    seed: str = ""  # id of the seed meta it is (seed) or comes from (a verified copy in my-metas.toml)


@dataclass
class Hint:
    hint: str
    countries: list[str]
    source: str
    verified: bool
    seed: str = ""  # seed meta to settle with "Right" / "Wrong"


@dataclass
class LookFor:
    """A category to look at to tell the candidates apart, with each one's clues."""

    category: str
    label: str
    score: float
    looks: list[str]  # spoiler-free instructions: what to observe to decide
    hints: list[Hint] = field(default_factory=list)


def category_look(category: str) -> str:
    return t(f"category.{category}.look")


def parse_metas(text: str, source: str, known_countries: Iterable[str] | None = None) -> list[Meta]:
    """Reads a TOML metas file ([[meta]] category, countries, hint, look, verified, id or seed). Raises MetaError."""
    known = set(known_countries) if known_countries is not None else None
    metas = []
    for i, entry in enumerate(tomllib.loads(text).get("meta", [])):
        where = t("metas.err.where", source=source, n=i + 1)
        category = entry.get("category")
        if category not in CATEGORIES:
            raise MetaError(t("metas.err.category", where=where, category=repr(category), known=", ".join(CATEGORIES)))
        countries = entry.get("countries")
        if not countries or not all(isinstance(c, str) and len(c) == 2 for c in countries):
            raise MetaError(t("metas.err.countries", where=where))
        codes = frozenset(c.upper() for c in countries)
        if known is not None and (unknown := codes - known):
            raise MetaError(t("metas.err.unknown_countries", where=where, list=", ".join(sorted(unknown))))
        hint = str(entry.get("hint", "")).strip()
        if not hint:
            raise MetaError(t("metas.err.hint", where=where))
        look = entry.get("look", "")
        if not isinstance(look, str):
            raise MetaError(t("metas.err.look", where=where))
        seed = entry.get("id" if source == SEED else "seed", "")
        if not isinstance(seed, str) or (seed and not SEED_ID.fullmatch(seed)):
            raise MetaError(t("metas.err.seed", where=where))
        metas.append(Meta(category, codes, hint, source, bool(entry.get("verified", False)), look.strip(), seed))
    return metas


def parse_rejected(text: str, source: str) -> set[str]:
    """Seed clues dismissed by the player: [[rejected]] seed = <id>."""
    rejected = set()
    for i, entry in enumerate(tomllib.loads(text).get("rejected", [])):
        seed = entry.get("seed")
        if not isinstance(seed, str) or not SEED_ID.fullmatch(seed):
            raise MetaError(t("metas.err.rejected", source=source, n=i + 1))
        rejected.add(seed)
    return rejected


def _seed_file(known: frozenset[str]) -> list[Meta]:
    """The seed as written (English reference texts), reduced to the configured countries."""
    seed = parse_metas(resources.files(__package__).joinpath("metas_amorce.toml").read_text(), SEED)
    return [replace(m, countries=m.countries & known) for m in seed if m.countries & known]


def _in_language(m: Meta) -> Meta:
    """A seed meta (or a verified copy of one) with its texts in the coach's language, when the catalog has them."""
    texts = catalog("en")  # every language has the same keys (test_i18n.py)
    hint, look = f"seed.{m.seed}.hint", f"seed.{m.seed}.look"
    return replace(m, hint=t(hint) if hint in texts else m.hint, look=t(look) if look in texts else m.look)


def seed_metas(known_countries: Iterable[str]) -> list[Meta]:
    """The seed, reduced to the configured countries: removing a country from the list must not break everything."""
    return [_in_language(m) for m in _seed_file(frozenset(known_countries))]


def load_metas(user_file: Path | None, include_seed: bool, known_countries: Iterable[str]) -> list[Meta]:
    known = list(known_countries)
    metas: list[Meta] = []
    settled: set[str] = set()
    if user_file and user_file.exists():
        text = user_file.read_text()
        mine = parse_metas(text, MINE, known)
        metas += [_in_language(m) if m.seed else m for m in mine]
        settled = parse_rejected(text, MINE) | {m.seed for m in mine if m.seed}
    if include_seed:
        metas += [m for m in seed_metas(known) if m.seed not in settled]
    return metas


def judge_seed(user_file: Path, seed: str, verdict: Literal["right", "wrong"], known_countries: Iterable[str]) -> None:
    """Saves the player's verdict on a seed clue, at the end of my-metas.toml.

    "right": verified copy of the clue (English reference text, shown in the coach's language), which then becomes
    "your meta". "wrong": dismissal. The file is never rewritten (its comments are kept); if it is invalid, nothing
    is written.
    """
    known = list(known_countries)
    meta = next((m for m in _seed_file(frozenset(known)) if m.seed == seed), None)
    if meta is None:
        raise MetaError(t("metas.err.unknown_seed"))
    text = user_file.read_text() if user_file.exists() else ""
    try:
        mine, rejected = parse_metas(text, MINE, known), parse_rejected(text, MINE)
    except ValueError as exc:  # MetaError, or unreadable TOML
        raise UserMetasError(t("metas.err.user_file", file=user_file.name, error=exc)) from exc
    if verdict == "right":
        entry = {"seed": seed, "category": meta.category, "countries": sorted(meta.countries), "hint": meta.hint}
        if meta.look:
            entry["look"] = meta.look
        block = _array_of_tables("meta", entry | {"verified": True})
        done = any(m.seed == seed for m in mine)
    else:
        block = _array_of_tables("rejected", {"seed": seed})
        done = seed in rejected
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
    looks and weights replace, category by category, the default instruction (category_look) and CATEGORY_WEIGHT;
    max_looks = 0 removes the instructions.
    """
    looks = looks or {}
    weights = CATEGORY_WEIGHT | (weights or {})
    probs = dict(candidates)
    results = []
    for category in CATEGORIES:
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
                m.seed if m.source == SEED else "",
            )
            for m in in_cat
        ]
        # Your metas first, then the clues of the most likely candidates.
        hints.sort(key=lambda h: (h.source != MINE, -max(probs[c] for c in h.countries)))
        hints = _dedupe(hints)
        by_hint = {m.hint: m.look for m in in_cat}
        own = list(dict.fromkeys(by_hint[h.hint] for h in hints if by_hint[h.hint]))
        shown = (own or [looks.get(category) or category_look(category)])[:max_looks]
        results.append(LookFor(category, t(f"category.{category}"), round(score, 4), shown, hints))
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
