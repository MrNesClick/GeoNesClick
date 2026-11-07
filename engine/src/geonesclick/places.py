"""Noms de lieux : répertoire GeoNames (cities1000, CC BY 4.0), pour reconnaître une ville lue sur une marque.

Téléchargé une fois (~11 Mo) puis indexé en local (SQLite) : chaque nom et ses variantes (autres langues, autres
alphabets) → pays. Mesuré le 2026-11-07 sur la manche bulgare : Благоевград, София, Гърмен, Гоце Делчев → BG
seulement ; Казань (inventé par le modèle) → RU ; « Gare » → FR, LU (des quartiers) : un mot courant peut passer
pour un lieu, d'où la règle de certitude prudente d'evidence.py.

Les petits villages (Laas, L'Hôpital-d'Orion, ~150 habitants) n'y sont pas : dès qu'un pays mène, le répertoire
COMPLET de ce pays (GeoNames <CC>.zip, lieux habités seulement) est téléchargé une fois et ajouté (decided with the
user, 2026-11-07). Les homonymes lointains (« Laas » = Lasa, Italie) sont écartés par la proximité (locate.py).

Données : GeoNames, https://www.geonames.org (CC BY 4.0), attribution affichée dans l'application et le README.
"""

from __future__ import annotations

import io
import re
import sqlite3
import threading
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

from .evidence import STREET_AFTER, STREET_BEFORE, Evidence

DB_NAME = "places-v3.sqlite"  # v3 : comparaison sans accents latins ni traits d'union (« Sauveterre de Bearn »)
OLD_DBS = ("places.sqlite", "places-v2.sqlite")
ARCHIVE = "source.zip"  # archive gardée : un changement de format reconstruit sans retélécharger
PER_NAME = 3  # homonymes gardés par nom et par pays (les plus peuplés), départagés par les distances
SOURCE = "https://www.geonames.org"
USER_AGENT = "GeoNesClick/0.1 (personal training app, one-time download)"
MAX_WORDS = 4  # noms de lieux d'au plus 4 mots (« Gotse Delchev », « San Carlos de Bariloche »)
MAX_BYTES = 64 * 1024 * 1024  # garde-fou : l'archive fait ~11 Mo
MAX_UNZIPPED = 600 * 1024 * 1024  # garde-fou contre une archive piégée (cities1000 : ~31 Mo ; FR : ~50 Mo)
COUNTRY = re.compile(r"[A-Z]{2}")  # code pays : sert à une adresse et à un nom de fichier


class PlacesError(RuntimeError):
    pass


ARTICLES = ("l ", "le ", "la ", "les ")  # « L'Hôpital-d'Orion » est écrit « HOPITAL D'ORION » sur le panneau


def _fold(ch: str) -> str:
    """Lettre latine sans son accent (é → e) ; les autres alphabets gardent leurs signes (й ≠ и)."""
    if unicodedata.name(ch, "").startswith("LATIN"):
        return "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
    return ch


def normalise(name: str) -> str:
    """Forme de comparaison : minuscules, accents latins retirés, traits d'union et apostrophes en espaces.

    L'IA recopie un panneau en capitales, souvent sans accents ni traits d'union (« SAUVETERRE DE BEARN ») ;
    GeoNames écrit « Sauveterre-de-Béarn ».
    """
    name = unicodedata.normalize("NFC", name).casefold()
    name = "".join(_fold(ch) for ch in name)
    name = re.sub(r"[-'’‐‑]", " ", name)
    return " ".join(name.split()).strip(" .,;:!?()[]\"«»")


def variants(key: str) -> list[str]:
    """La forme normalisée, et sans article en tête (« l hopital d orion » → « hopital d orion »)."""
    out = [key]
    for article in ARTICLES:
        if key.startswith(article) and len(key) > len(article) + 3:
            out.append(key[len(article):])
    return out


def _fetch(url: str) -> bytes:
    """Téléchargement de l'archive (remplacé dans les tests : aucun accès réseau)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (https vérifié par build)
            data = resp.read(MAX_BYTES + 1)
    except OSError as exc:
        raise PlacesError(f"téléchargement impossible ({exc})") from exc
    if len(data) > MAX_BYTES:
        raise PlacesError("archive démesurée, refusée")
    return data


def build(url: str, directory: Path, min_len: int = 3, db_name: str = DB_NAME, archive_name: str | None = ARCHIVE,
          populated_only: bool = False) -> Path:
    """Télécharge le répertoire et construit l'index local ; écriture atomique de la base.

    populated_only : fichier complet d'un pays (montagnes, rivières…) dont on ne garde que les lieux habités (P).
    """
    if not url.startswith("https://"):
        raise PlacesError("adresse du répertoire refusée : https attendu")
    directory.mkdir(parents=True, exist_ok=True)
    cached = directory / archive_name if archive_name else None
    data = cached.read_bytes() if cached and cached.exists() else _fetch(url)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            # Les archives par pays contiennent aussi un readme.txt : on prend le fichier de données.
            member = next((n for n in archive.namelist()
                           if n.endswith(".txt") and "/" not in n and n.lower() != "readme.txt"), None)
            if member is None:
                raise PlacesError("archive sans fichier de lieux")
            if archive.getinfo(member).file_size > MAX_UNZIPPED:
                raise PlacesError("fichier de lieux démesuré une fois décompressé, refusé")
            text = archive.read(member).decode("utf-8")
    except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise PlacesError("archive illisible") from exc
    best: dict[tuple[str, str], list[tuple[int, str, float, float]]] = {}
    for line in text.splitlines():
        cols = line.split("\t")
        if len(cols) < 15 or not COUNTRY.fullmatch(cols[8]) or (populated_only and cols[6] != "P"):
            continue
        name, ascii_name, alternates, country = cols[1], cols[2], cols[3], cols[8]
        try:
            population, lat, lon = int(cols[14] or 0), float(cols[4]), float(cols[5])
        except ValueError:
            continue
        keys = {k for v in {name, ascii_name, *alternates.split(",")} for k in variants(normalise(v))}
        for key in keys:
            if len(key) < min_len or not any(ch.isalpha() for ch in key) or len(key.split()) > MAX_WORDS:
                continue
            same = best.setdefault((key, country), [])
            same.append((population, name, lat, lon))
            if len(same) > PER_NAME:
                same.sort(reverse=True)
                del same[PER_NAME:]
    tmp = directory / (db_name + ".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    try:
        with con:
            con.execute("CREATE TABLE place(norm TEXT NOT NULL, country TEXT NOT NULL, population INTEGER, name TEXT,"
                        " lat REAL NOT NULL, lon REAL NOT NULL)")
            con.executemany("INSERT INTO place VALUES (?, ?, ?, ?, ?, ?)",
                            [(k, c, *row) for (k, c), rows in best.items() for row in rows])
            con.execute("CREATE INDEX place_norm ON place(norm)")
    finally:
        con.close()
    path = directory / db_name
    tmp.replace(path)
    if cached and not cached.exists():
        cached.write_bytes(data)  # gardée seulement une fois l'index construit (archive valide)
    return path


def _distance_after(words: list[str], end: int, line: str) -> float | None:
    """Distance écrite juste après le nom, sur la même ligne (« Гърмен 3 », « Sofia 219 km »), en km.

    Seulement si plus aucun mot ne suit le nom : « 197 » seul sur sa ligne est un numéro de route, pas une distance.
    """
    if end < len(words) and words[end].lower() not in ("km",):
        return None
    tail = line[line.rfind(words[end - 1]) + len(words[end - 1]):]
    found = re.fullmatch(r"\s*[:\-–]?\s*(\d{1,4}(?:[.,]\d)?)\s*(?:km)?\.?\s*", tail, re.IGNORECASE)
    if not found:
        return None
    km = float(found.group(1).replace(",", "."))
    return km if 0 < km <= 2000 else None


def detail_name(country: str) -> str:
    if not COUNTRY.fullmatch(country):
        raise PlacesError(f"code pays invalide : {country!r}")
    return f"detail-{country}-v3.sqlite"


def _open(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)


class Places:
    """Index local des noms de lieux (lecture seule) : localités de plus de 1 000 habitants, plus le détail de
    certains pays (tous leurs lieux habités), ajouté au fil des manches."""

    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise PlacesError("répertoire des lieux absent")
        self.con = _open(path)
        self._lock = threading.Lock()
        self.count = self.con.execute("SELECT COUNT(*) FROM place").fetchone()[0]
        self.details: dict[str, sqlite3.Connection] = {}

    def add_detail(self, country: str, path: Path) -> None:
        con = _open(path)
        with self._lock:
            self.details[country] = con

    def remove_detail(self, country: str) -> None:
        with self._lock:
            con = self.details.pop(country, None)
        if con is not None:
            con.close()

    def lookup(self, name: str) -> list[tuple[str, int, str, float, float]]:
        """[(pays, population, nom GeoNames, latitude, longitude)] pour un nom (forme normalisée), répertoire
        général et détails des pays réunis, sans doublon (même lieu dans les deux)."""
        key = normalise(name)
        sql = "SELECT country, population, name, lat, lon FROM place WHERE norm = ?"
        with self._lock:
            rows = [r for con in (self.con, *self.details.values()) for r in con.execute(sql, (key,))]
        unique = {(c, n, round(lat, 2), round(lon, 2)): (c, p, n, lat, lon) for c, p, n, lat, lon in rows}
        return sorted(unique.values(), key=lambda r: -r[1])

    def match(self, lines: list[str], min_len: int = 4) -> list[Evidence]:
        """Lieux nommés dans le texte d'une marque : groupes de mots consécutifs, le plus long d'abord.

        Les mots d'un nom de rue sont écartés (« Via Paolo Lo Manto » : « Manto » n'est pas un lieu où l'on est) et
        rendus comme preuve « rue », qui ne compte pas mais s'affiche.
        """
        out: list[Evidence] = []
        seen: set[str] = set()
        street_next = ""  # ligne réduite à un mot de rue (« VIA ») : la ligne suivante est le nom de la rue
        for line in lines:
            words = re.findall(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", unicodedata.normalize("NFC", line))
            norm = [normalise(w) for w in words]
            blocked = set(range(len(words))) if street_next else set()
            for i, w in enumerate(norm):
                if w in STREET_BEFORE:
                    blocked |= set(range(i, len(words)))
                if w in STREET_AFTER:
                    blocked |= set(range(i + 1))
            if blocked and len(blocked) > 1:
                street = f"{street_next} {line}".strip() if street_next else line.strip()
                out.append(Evidence("rue", street, "nom de rue : ne situe pas la vue", [], ""))
            street_next = line.strip() if len(norm) == 1 and norm[0] in STREET_BEFORE else ""
            used = [i in blocked for i in range(len(words))]
            for size in range(min(MAX_WORDS, len(words)), 0, -1):
                for start in range(len(words) - size + 1):
                    if any(used[start:start + size]):
                        continue
                    candidate = " ".join(words[start:start + size])
                    key = normalise(candidate)
                    if len(key) < min_len or key in seen:
                        continue
                    rows = self.lookup(candidate)
                    if not rows:
                        continue
                    seen.add(key)
                    used[start:start + size] = [True] * size
                    countries = sorted({r[0] for r in rows})
                    out.append(Evidence("lieu", candidate, rows[0][2], countries, SOURCE,
                                        km=_distance_after(words, start + size, line),
                                        points=[[lat, lon, c, n] for c, _, n, lat, lon in rows]))
        return out

    def close(self) -> None:
        with self._lock:
            for con in (self.con, *self.details.values()):
                con.close()


def main() -> int:
    """python -m geonesclick.places : (re)construit l'index des lieux (appelé par scripts/install.sh)."""
    from .config import load_config

    cfg = load_config().rules
    try:
        path = build(cfg.places_url, cfg.places_path)
    except PlacesError as exc:
        print(f"Lieux GeoNames : {exc}")
        return 1
    print(f"Lieux GeoNames : {Places(path).count} noms indexés dans {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
