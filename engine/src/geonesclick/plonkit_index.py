"""Base locale des astuces Plonk It : SQLite (table + recherche plein texte FTS5) et vecteurs CLIP en cache.

Le banc d'essai (spikes/search_bench.py) a tranché : à ce volume (~4 000 astuces, < 1 Mo de texte), aucun
moteur de recherche dédié n'apporte de gain ; ce qui compte est de comparer l'image aux astuces (vecteurs
CLIP, un produit de matrices). La base se reconstruit à partir des pages collectées (plonkit.py), en
quelques dixièmes de seconde ; les vecteurs sont mis en cache par empreinte du texte, pour ne recalculer
que ceux des astuces nouvelles ou modifiées.

Chaque astuce est rangée dans une catégorie de metas : d'abord par ses étiquettes Plonk It, puis par
mots-clés (réglables) ; « autre » si rien ne tranche (category_source = "aucune").
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

# Étiquettes Plonk It → catégories de metas (les autres étiquettes, « important », « moving info », ne classent pas).
TAG_CATEGORY = {
    "pole": "poteaux", "bollard": "bornes", "guardrail": "bornes", "chevron/sign": "panneaux",
    "roadline": "marquage", "license plates": "plaques", "language": "langue", "coverage": "voiture",
    "architecture": "architecture", "vegetation": "vegetation", "landscape": "vegetation",
}

# Mots-clés (anglais, comme les guides), par catégorie ; remplaçables par [plonkit.keywords] dans config.toml.
DEFAULT_KEYWORDS: dict[str, list[str]] = {
    "langue": ["language", "languages", "alphabet", "alphabets", "script", "scripts", "cyrillic", "latin", "letter",
               "letters", "diacritic", "diacritics", "spelling", "word", "words", "spoken", "dialect", "dialects"],
    "conduite": ["drive on the left", "drive on the right", "driving side", "left-hand traffic", "right-hand traffic"],
    "marquage": ["road line", "road lines", "roadline", "roadlines", "centre line", "center line", "middle line",
                 "edge line", "dashed", "markings"],
    "poteaux": ["pole", "poles", "utility pole", "electricity pole", "pylon", "pylons"],
    "bornes": ["bollard", "bollards", "delineator", "delineators", "guardrail", "guardrails", "reflector"],
    "plaques": ["license plate", "licence plate", "number plate", "plates"],
    "panneaux": ["sign", "signs", "signage", "chevron", "chevrons", "speed limit", "stop sign"],
    "domaine": ["domain", "website"],
    "voiture": ["google car", "camera", "generation", "gen 2", "gen 3", "gen 4", "antenna", "snorkel", "roof rack",
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
    """(catégorie, source) : « etiquette », « mots-cles », ou « aucune » (alors catégorie « autre »)."""
    for tag in tags:
        if tag in TAG_CATEGORY:
            return TAG_CATEGORY[tag], "etiquette"
    plain = re.sub(r"[*_`]", "", text)
    counts = {cat: len(p.findall(plain)) for cat, p in patterns.items()}
    if DOMAIN.search(plain):
        counts["domaine"] = counts.get("domaine", 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked or ranked[0][1] == 0 or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
        return "autre", "aucune"  # rien, ou égalité : à départager plus tard (IA, ou le joueur)
    return ranked[0][0], "mots-cles"


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
# Catégories déjà attribuées par l'IA, réappliquées à chaque reconstruction (une seule fois par texte).
APPLY_AI = """UPDATE tip SET category = (SELECT category FROM ai_category a WHERE a.hash = tip.hash),
    category_source = 'ia' WHERE category_source = 'aucune' AND hash IN (SELECT hash FROM ai_category)"""


def _locked(method):
    """Exécute la méthode sous le verrou de l'index (connexion SQLite partagée entre threads)."""

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
        # Une connexion partagée entre la mise à jour de fond et les traductions : un accès à la fois.
        self.lock = threading.Lock()

    def close(self) -> None:
        self.con.close()

    # --- construction ----------------------------------------------------------------------------
    @_locked
    def rebuild(self, tips: Iterable[Tip], keywords: dict[str, list[str]] | None = None) -> int:
        """Remplace toutes les astuces (le cache des vecteurs est conservé) ; renvoie leur nombre."""
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
        """(empreinte, texte) des astuces que ni les étiquettes ni les mots-clés ni l'IA n'ont classées."""
        return list(self.con.execute(
            "SELECT DISTINCT hash, text FROM tip WHERE category_source = 'aucune'"
            " AND hash NOT IN (SELECT hash FROM ai_category)"))

    @_locked
    def store_ai_categories(self, categories: dict[str, str]) -> None:
        with self.con:
            self.con.executemany("INSERT OR REPLACE INTO ai_category(hash, category) VALUES (?, ?)",
                                 list(categories.items()))
            self.con.execute(APPLY_AI)

    @_locked
    def missing_embeddings(self, model: str) -> list[tuple[str, str]]:
        """(empreinte, texte) des astuces sans vecteur pour ce modèle."""
        return list(self.con.execute(
            "SELECT DISTINCT t.hash, t.text FROM tip t LEFT JOIN embedding e ON e.hash = t.hash AND e.model = ?"
            " WHERE e.hash IS NULL", (model,)))

    @_locked
    def store_embeddings(self, model: str, items: Iterable[tuple[str, np.ndarray]]) -> None:
        with self.con:
            self.con.executemany(
                "INSERT OR REPLACE INTO embedding(hash, model, vector) VALUES (?, ?, ?)",
                [(h, model, np.asarray(v, dtype=np.float16).tobytes()) for h, v in items])

    # --- lecture ---------------------------------------------------------------------------------
    @_locked
    def translations(self, hashes: list[str], lang: str) -> dict[str, str]:
        """Traductions déjà en cache, {empreinte: texte traduit}."""
        if not hashes:
            return {}
        rows = self.con.execute(
            f"SELECT hash, text FROM translation WHERE lang = ? AND hash IN ({','.join('?' * len(hashes))})",
            [lang, *hashes])
        return dict(rows)

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
        """Toutes les astuces qui ont un vecteur, et la matrice (n, d) de leurs vecteurs normalisés."""
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
        """Recherche plein texte (BM25) ; chaque mot est cité, donc aucune syntaxe FTS5 ne passe de la requête."""
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
    """Pour chaque pays, les astuces dont le texte ressemble le plus à la vue (similarité cosinus CLIP)."""
    if not len(tips):
        return {}
    sims = matrix @ image_emb
    out = {}
    for code in countries:
        idx = [i for i, t in enumerate(tips) if t.country == code]
        best = sorted(idx, key=lambda i: sims[i], reverse=True)[:per_country]
        out[code] = [(tips[i], float(sims[i])) for i in best]
    return out
