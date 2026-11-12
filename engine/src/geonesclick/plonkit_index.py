"""Local database of the Plonk It tips: SQLite (table + FTS5 full-text search) and cached CLIP vectors.

The benchmark (spikes/search_bench.py) settled it: at this volume (~4,000 tips, < 1 MB of text), no
dedicated search engine brings any gain; what matters is comparing the image with the tips (CLIP
vectors, a matrix product). The database is rebuilt from the collected pages (plonkit.py), in
a few tenths of a second; the vectors are cached by text hash, so that only those of new or
modified tips are recomputed.

Each tip is filed in a metas category: first by its Plonk It tags, then by
keywords (configurable); "other" if nothing settles it (category_source = "none").
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import sqlite3
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .plonkit import Tip

# Plonk It tags → metas categories (the other tags, "important", "moving info", do not classify).
TAG_CATEGORY = {
    "pole": "poles", "bollard": "bollards", "guardrail": "bollards", "chevron/sign": "signs",
    "roadline": "road_lines", "license plates": "plates", "language": "language", "coverage": "car",
    "architecture": "architecture", "vegetation": "vegetation", "landscape": "vegetation",
}

# Keywords (English, like the guides), per category; replaceable by [plonkit.keywords] in config.toml.
DEFAULT_KEYWORDS: dict[str, list[str]] = {
    "language": ["language", "languages", "alphabet", "alphabets", "script", "scripts", "cyrillic", "latin", "letter",
                 "letters", "diacritic", "diacritics", "spelling", "word", "words", "spoken", "dialect", "dialects"],
    "driving": ["drive on the left", "drive on the right", "driving side", "left-hand traffic", "right-hand traffic"],
    "road_lines": ["road line", "road lines", "roadline", "roadlines", "centre line", "center line", "middle line",
                   "edge line", "dashed", "markings"],
    "poles": ["pole", "poles", "utility pole", "electricity pole", "pylon", "pylons"],
    "bollards": ["bollard", "bollards", "delineator", "delineators", "guardrail", "guardrails", "reflector"],
    "plates": ["license plate", "licence plate", "number plate", "plates"],
    "signs": ["sign", "signs", "signage", "chevron", "chevrons", "speed limit", "stop sign"],
    "domains": ["domain", "website"],
    "car": ["google car", "camera", "generation", "gen 2", "gen 3", "gen 4", "antenna", "snorkel", "roof rack",
            "coverage", "follow car", "blur"],
    "vegetation": ["tree", "trees", "vegetation", "forest", "soil", "dirt", "grass", "palm", "birch", "pine", "crops",
                   "landscape", "mountains", "hills"],
    "architecture": ["house", "houses", "building", "buildings", "roof", "roofs", "architecture", "wall", "walls",
                     "fence", "fences", "church"],
}
DOMAIN = re.compile(r"(?:^|\s)\.[a-z]{2}\b")


@dataclass
class IndexedTip:
    hash: str
    rowid: int
    country: str
    slug: str
    section: str
    text: str
    category: str
    image_url: str
    street_view: str

    @property
    def url(self) -> str:
        return f"https://www.plonkit.net/{self.slug}"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _keyword_patterns(keywords: dict[str, list[str]]) -> dict[str, re.Pattern]:
    return {
        cat: re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\b", re.I)
        for cat, words in keywords.items() if words
    }


def classify(text: str, tags: Iterable[str], patterns: dict[str, re.Pattern]) -> tuple[str, str]:
    """(category, source): "tag", "keywords", or "none" (then category "other")."""
    for tag in tags:
        if tag in TAG_CATEGORY:
            return TAG_CATEGORY[tag], "tag"
    plain = re.sub(r"[*_`]", "", text)
    counts = {cat: len(p.findall(plain)) for cat, p in patterns.items()}
    if DOMAIN.search(plain):
        counts["domains"] = counts.get("domains", 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked or ranked[0][1] == 0 or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
        return "other", "none"  # nothing, or a tie: to be decided later (AI, or the player)
    return ranked[0][0], "keywords"


SCHEMA = """
CREATE TABLE IF NOT EXISTS tip(
    id INTEGER PRIMARY KEY, country TEXT NOT NULL, slug TEXT NOT NULL, section TEXT NOT NULL,
    tip_id TEXT NOT NULL, text TEXT NOT NULL, tags TEXT NOT NULL, image_url TEXT NOT NULL,
    street_view TEXT NOT NULL, category TEXT NOT NULL, category_source TEXT NOT NULL, hash TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS tip_country ON tip(country);
CREATE VIRTUAL TABLE IF NOT EXISTS tip_fts USING fts5(text, content='tip', content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS embedding(hash TEXT NOT NULL, model TEXT NOT NULL, vector BLOB NOT NULL,
    PRIMARY KEY(hash, model));
CREATE TABLE IF NOT EXISTS ai_category(hash TEXT PRIMARY KEY, category TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS translation(hash TEXT NOT NULL, lang TEXT NOT NULL, text TEXT NOT NULL,
    PRIMARY KEY(hash, lang));
"""
# Categories already assigned by the AI, reapplied on each rebuild (only once per text).
APPLY_AI = """UPDATE tip SET category = (SELECT category FROM ai_category a WHERE a.hash = tip.hash),
    category_source = 'ai' WHERE category_source = 'none' AND hash IN (SELECT hash FROM ai_category)"""


def _locked(method):
    """Runs the method under the index lock (SQLite connection shared between threads)."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)

    return wrapper


class TipIndex:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.executescript(SCHEMA)
        # A connection shared between the background update and the translations: one access at a time.
        self.lock = threading.Lock()

    def close(self) -> None:
        self.con.close()

    # --- build -----------------------------------------------------------------------------------
    @_locked
    def rebuild(self, tips: Iterable[Tip], keywords: dict[str, list[str]] | None = None) -> int:
        """Replaces all the tips (the vector cache is kept); returns their number."""
        patterns = _keyword_patterns(DEFAULT_KEYWORDS | (keywords or {}))
        rows = []
        for t in tips:
            if not t.text:
                continue
            category, source = classify(t.text, t.tags, patterns)
            rows.append((t.country, t.slug, t.section, t.tip_id, t.text, json.dumps(t.tags), t.image_url,
                         t.street_view, category, source, text_hash(t.text)))
        with self.con:
            self.con.execute("DELETE FROM tip")
            self.con.executemany(
                "INSERT INTO tip(country, slug, section, tip_id, text, tags, image_url, street_view, category,"
                " category_source, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            self.con.execute(APPLY_AI)
            self.con.execute("INSERT INTO tip_fts(tip_fts) VALUES ('rebuild')")
        return len(rows)

    @_locked
    def unclassified(self) -> list[tuple[str, str]]:
        """(hash, text) of the tips that neither the tags nor the keywords nor the AI have classified."""
        return list(self.con.execute(
            "SELECT DISTINCT hash, text FROM tip WHERE category_source = 'none'"
            " AND hash NOT IN (SELECT hash FROM ai_category)"))

    @_locked
    def store_ai_categories(self, categories: dict[str, str]) -> None:
        with self.con:
            self.con.executemany("INSERT OR REPLACE INTO ai_category(hash, category) VALUES (?, ?)",
                                 list(categories.items()))
            self.con.execute(APPLY_AI)

    @_locked
    def missing_embeddings(self, model: str) -> list[tuple[str, str]]:
        """(hash, text) of the tips without a vector for this model."""
        return list(self.con.execute(
            "SELECT DISTINCT t.hash, t.text FROM tip t LEFT JOIN embedding e ON e.hash = t.hash AND e.model = ?"
            " WHERE e.hash IS NULL", (model,)))

    @_locked
    def store_embeddings(self, model: str, items: Iterable[tuple[str, np.ndarray]]) -> None:
        with self.con:
            self.con.executemany(
                "INSERT OR REPLACE INTO embedding(hash, model, vector) VALUES (?, ?, ?)",
                [(h, model, np.asarray(v, dtype=np.float16).tobytes()) for h, v in items])

    # --- reading ---------------------------------------------------------------------------------
    @_locked
    def translations(self, hashes: list[str], lang: str) -> dict[str, str]:
        """Translations already cached, {hash: translated text}."""
        if not hashes:
            return {}
        rows = self.con.execute(
            f"SELECT hash, text FROM translation WHERE lang = ? AND hash IN ({','.join('?' * len(hashes))})",
            [lang, *hashes])
        return dict(rows)

    @_locked
    def untranslated(self, lang: str) -> list[tuple[str, str]]:
        """(hash, text) of the tips without a translation in this language."""
        return list(self.con.execute(
            "SELECT DISTINCT hash, text FROM tip WHERE hash NOT IN (SELECT hash FROM translation WHERE lang = ?)"
            " ORDER BY hash", (lang,)))

    @_locked
    def store_translations(self, lang: str, texts: dict[str, str]) -> None:
        with self.con:
            self.con.executemany("INSERT OR REPLACE INTO translation(hash, lang, text) VALUES (?, ?, ?)",
                                 [(h, lang, t) for h, t in texts.items()])

    @_locked
    def count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM tip").fetchone()[0]

    @_locked
    def load(self, model: str) -> tuple[list[IndexedTip], np.ndarray]:
        """All the tips that have a vector, and the (n, d) matrix of their normalised vectors."""
        rows = self.con.execute(
            "SELECT t.hash, t.id, t.country, t.slug, t.section, t.text, t.category, t.image_url, t.street_view,"
            " e.vector"
            " FROM tip t JOIN embedding e ON e.hash = t.hash AND e.model = ? ORDER BY t.id", (model,)).fetchall()
        tips = [IndexedTip(*r[:9]) for r in rows]
        if not rows:
            return tips, np.zeros((0, 0), dtype=np.float32)
        return tips, np.stack([np.frombuffer(r[9], dtype=np.float16) for r in rows]).astype(np.float32)

    @_locked
    def search(self, query: str, limit: int = 20, countries: Iterable[str] | None = None) -> list[IndexedTip]:
        """Full-text search (BM25); each word is quoted, so no FTS5 syntax gets through from the query."""
        words = re.findall(r"\w{2,}", query.lower())[:20]
        if not words:
            return []
        sql = ("SELECT t.hash, t.id, t.country, t.slug, t.section, t.text, t.category, t.image_url, t.street_view"
               " FROM tip_fts f JOIN tip t ON t.id = f.rowid WHERE tip_fts MATCH ?")
        params: list = [" OR ".join(f'"{w}"' for w in words)]
        if countries:
            codes = list(countries)
            sql += f" AND t.country IN ({','.join('?' * len(codes))})"
            params += codes
        sql += " ORDER BY bm25(tip_fts) LIMIT ?"
        return [IndexedTip(*r) for r in self.con.execute(sql, [*params, limit])]


def similar_tips(
    image_emb: np.ndarray, tips: list[IndexedTip], matrix: np.ndarray, countries: Iterable[str], per_country: int
) -> dict[str, list[tuple[IndexedTip, float]]]:
    """For each country, the tips whose text most resembles the view (CLIP cosine similarity)."""
    if not len(tips):
        return {}
    sims = matrix @ image_emb
    out = {}
    for code in countries:
        idx = [i for i, t in enumerate(tips) if t.country == code]
        best = sorted(idx, key=lambda i: sims[i], reverse=True)[:per_country]
        out[code] = [(tips[i], float(sims[i])) for i in best]
    return out
