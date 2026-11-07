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
import math
import re
import sqlite3
import threading
import unicodedata
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from .evidence import STREET_AFTER, STREET_BEFORE, Evidence
from .locate import haversine

# v3 : comparaison sans accents latins ni traits d'union (« Sauveterre de Bearn ») ; v4 : région de chaque lieu
# (code admin1 GeoNames) et index des latitudes, pour les verrous pays › région › ville (2026-11-07).
VERSION = "v4"
DB_NAME = f"places-{VERSION}.sqlite"
OLD_DBS = ("places.sqlite", "places-v2.sqlite", "places-v3.sqlite")
ARCHIVE = "source.zip"  # archive gardée : un changement de format reconstruit sans retélécharger
REGIONS = "admin1.txt"  # noms des régions (admin1CodesASCII.txt de GeoNames, ~140 Ko), gardé de même
MAX_RESULTS = 20  # résultats d'une recherche de lieu (champ « + » du bandeau des verrous)
PER_NAME = 3  # homonymes gardés par nom et par pays (les plus peuplés), départagés par les distances
SOURCE = "https://www.geonames.org"
USER_AGENT = "GeoNesClick/0.1 (personal training app, one-time download)"
MAX_WORDS = 4  # noms de lieux d'au plus 4 mots (« Gotse Delchev », « San Carlos de Bariloche »)
MAX_BYTES = 64 * 1024 * 1024  # garde-fou : l'archive fait ~11 Mo
MAX_UNZIPPED = 600 * 1024 * 1024  # garde-fou contre une archive piégée (cities1000 : ~31 Mo ; FR : ~50 Mo)
COUNTRY = re.compile(r"[A-Z]{2}")  # code pays : sert à une adresse et à un nom de fichier
REGION = re.compile(r"[A-Z]{2}\.[0-9A-Z]{1,20}")  # code de région GeoNames : « FR.75 »
NUMBER_LINE = re.compile(r"\s*(\d{1,4}(?:[.,]\d)?)\s*(?:km)?\.?\s*", re.IGNORECASE)  # « 162 », « 11 km »
LEADING_NUMBER = re.compile(r"\s*(\d{1,4}(?:[.,]\d)?)(\s*(?:km)?\s+)", re.IGNORECASE)  # « 10 Aarup »


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


def _regions(url: str | None, directory: Path) -> dict[str, str]:
    """Noms des régions (« FR.75 » → « Nouvelle-Aquitaine »), gardés à côté de l'archive.

    Facultatif : sans réseau, l'index se construit quand même et une région s'affiche par son code.
    """
    if not url:
        return {}
    cached = directory / REGIONS
    fresh = not cached.exists()
    if fresh:
        if not url.startswith("https://"):
            raise PlacesError("adresse des régions refusée : https attendu")
        try:
            text = _fetch(url).decode("utf-8")
        except (PlacesError, UnicodeDecodeError):
            return {}
    else:
        text = cached.read_text(encoding="utf-8", errors="replace")
    out = {}
    for line in text.splitlines():
        cols = line.split("\t")
        if len(cols) >= 2 and REGION.fullmatch(cols[0]):
            out[cols[0]] = cols[1][:200]
    if fresh and out:  # une page d'erreur à la place du fichier n'est pas gardée : retentée la prochaine fois
        cached.write_text(text, encoding="utf-8")
    return out


def build(url: str, directory: Path, min_len: int = 3, db_name: str = DB_NAME, archive_name: str | None = ARCHIVE,
          populated_only: bool = False, regions_url: str | None = None) -> Path:
    """Télécharge le répertoire et construit l'index local ; écriture atomique de la base.

    populated_only : fichier complet d'un pays (montagnes, rivières…) dont on ne garde que les lieux habités (P).
    regions_url : noms des régions (répertoire général seulement ; les détails des pays partagent ces codes).
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
    best: dict[tuple[str, str], list[tuple[int, str, float, float, str]]] = {}
    for line in text.splitlines():
        cols = line.split("\t")
        if len(cols) < 15 or not COUNTRY.fullmatch(cols[8]) or (populated_only and cols[6] != "P"):
            continue
        name, ascii_name, alternates, country = cols[1], cols[2], cols[3], cols[8]
        region = f"{country}.{cols[10]}" if REGION.fullmatch(f"{country}.{cols[10]}") else ""
        try:
            population, lat, lon = int(cols[14] or 0), float(cols[4]), float(cols[5])
        except ValueError:
            continue
        keys = {k for v in {name, ascii_name, *alternates.split(",")} for k in variants(normalise(v))}
        for key in keys:
            if len(key) < min_len or not any(ch.isalpha() for ch in key) or len(key.split()) > MAX_WORDS:
                continue
            same = best.setdefault((key, country), [])
            same.append((population, name, lat, lon, region))
            if len(same) > PER_NAME:
                same.sort(reverse=True)
                del same[PER_NAME:]
    regions = _regions(regions_url, directory)
    tmp = directory / (db_name + ".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    try:
        with con:
            con.execute("CREATE TABLE place(norm TEXT NOT NULL, country TEXT NOT NULL, population INTEGER, name TEXT,"
                        " lat REAL NOT NULL, lon REAL NOT NULL, region TEXT NOT NULL DEFAULT '')")
            con.executemany("INSERT INTO place VALUES (?, ?, ?, ?, ?, ?, ?)",
                            [(k, c, *row) for (k, c), rows in best.items() for row in rows])
            con.execute("CREATE INDEX place_norm ON place(norm)")
            con.execute("CREATE INDEX place_lat ON place(lat)")  # lieux autour d'une position (région du point)
            con.execute("CREATE TABLE region(code TEXT PRIMARY KEY, name TEXT NOT NULL)")
            con.executemany("INSERT INTO region VALUES (?, ?)", sorted(regions.items()))
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


def _read_table(table: list[float | list[Evidence]], ahead: dict[int, float]) -> None:
    """Distances d'un panneau directionnel que l'IA a recopié colonne par colonne (décidé le 2026-11-07).

    Mesuré ce soir-là : « SARANSK » / « 162 » / « СТАРЫЙ ГОРОД » / « 11 » (chaque distance sous son lieu) ;
    « 10 Aarup » / « 5 Ørsted » / « 329 » (distance DEVANT le nom, puis le numéro de route) ; « 329 Faaborg » /
    « Glamsbjerg » / « 28 » / « 3 » (route devant, les deux distances à la fin). Règles, du plus sûr au moins sûr :
    1. une distance écrite après le nom, sur sa ligne, n'est jamais remplacée ;
    2. des nombres seuls qui suivent un bloc de lieux leur reviennent dans l'ordre s'ils sont aussi nombreux que
       les lieux du bloc (Faaborg 28, Glamsbjerg 3 : le « 329 » devant Faaborg était une route) ;
    3. sinon, un nombre seul juste sous un lieu sans distance lui revient (Saransk 162) ;
    4. enfin, un lieu encore sans distance prend le nombre écrit devant son nom (Aarup 10, Ørsted 5) ;
    un nombre en trop est ignoré (« 329 » sous « 5 Ørsted », « 197 » sous « Гърмен 3 ») : un numéro de route.
    """
    def fits(km: float) -> bool:
        return 0 < km <= 2000

    block: list[Evidence] = []  # lieux depuis la dernière suite de nombres
    i = 0
    while i < len(table):
        row = table[i]
        if not isinstance(row, float):
            block += row
            i += 1
            continue
        run = []
        while i < len(table) and isinstance(table[i], float):
            run.append(table[i])
            i += 1
        just_above = table[i - len(run) - 1] if i - len(run) - 1 >= 0 else []
        if len(run) == len(block) >= 2 and all(e.km is None for e in block) and all(map(fits, run)):
            for e, km in zip(block, run, strict=True):
                e.km = km
        elif isinstance(just_above, list) and just_above and just_above[-1].km is None \
                and id(just_above[-1]) not in ahead and fits(run[0]):
            just_above[-1].km = run[0]
        block = []
    for row in table:
        for e in row if isinstance(row, list) else []:
            if e.km is None and fits(ahead.get(id(e), 0.0)):
                e.km = ahead[id(e)]


def detail_name(country: str) -> str:
    if not COUNTRY.fullmatch(country):
        raise PlacesError(f"code pays invalide : {country!r}")
    return f"detail-{country}-{VERSION}.sqlite"


def _unique(rows) -> dict[tuple, tuple]:
    """Un même lieu peut venir du répertoire général et du détail du pays : on le garde une fois."""
    return {(c, n, round(lat, 2), round(lon, 2)): (c, p, n, lat, lon, r) for c, p, n, lat, lon, r in rows}


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
        self._bounds: dict[str, list[float] | None] = {}  # étendue des régions déjà demandées

    def add_detail(self, country: str, path: Path) -> None:
        con = _open(path)
        with self._lock:
            self.details[country] = con
            self._bounds.clear()  # les villages élargissent l'étendue connue des régions

    def remove_detail(self, country: str) -> None:
        with self._lock:
            con = self.details.pop(country, None)
            self._bounds.clear()
        if con is not None:
            con.close()

    def _rows(self, sql: str, args: tuple) -> list[tuple]:
        with self._lock:
            return [r for con in (self.con, *self.details.values()) for r in con.execute(sql, args)]

    def lookup(self, name: str) -> list[tuple[str, int, str, float, float, str]]:
        """[(pays, population, nom GeoNames, latitude, longitude, région)] pour un nom (forme normalisée),
        répertoire général et détails des pays réunis, sans doublon (même lieu dans les deux)."""
        rows = self._rows("SELECT country, population, name, lat, lon, region FROM place WHERE norm = ?",
                          (normalise(name),))
        return sorted(_unique(rows).values(), key=lambda r: -r[1])

    def region_name(self, code: str) -> str:
        """Nom d'une région (« FR.75 » → « Nouvelle-Aquitaine ») ; son code si les noms sont absents."""
        with self._lock:
            row = self.con.execute("SELECT name FROM region WHERE code = ?", (code,)).fetchone()
        return row[0] if row else code

    def region_bounds(self, code: str) -> list[float] | None:
        """[sud, ouest, nord, est] des lieux de la région (cadrage de la carte, sans contour), gardé en mémoire."""
        if code not in self._bounds:
            rows = self._rows("SELECT MIN(lat), MIN(lon), MAX(lat), MAX(lon) FROM place WHERE region = ?", (code,))
            found = [r for r in rows if r[0] is not None]
            self._bounds[code] = [min(r[0] for r in found), min(r[1] for r in found),
                                  max(r[2] for r in found), max(r[3] for r in found)] if found else None
        return self._bounds[code]

    def regions(self, country: str, query: str = "") -> list[dict[str, str]]:
        """Régions d'un pays dont le nom commence par query (sans accents ni casse), par ordre alphabétique."""
        with self._lock:
            rows = self.con.execute("SELECT code, name FROM region WHERE code LIKE ? ORDER BY name",
                                    (f"{country}.%",)).fetchall()
        key = normalise(query)
        return [{"code": c, "name": n} for c, n in rows
                if not key or any(w.startswith(key) for w in [normalise(n), *normalise(n).split()])][:MAX_RESULTS]

    def search(self, query: str, country: str, region: str = "") -> list[dict[str, Any]]:
        """Lieux habités dont un nom commence par query, dans le pays (et la région) ; les plus peuplés d'abord."""
        key = normalise(query)
        if len(key) < 2:
            return []
        sql = ("SELECT country, population, name, lat, lon, region FROM place"
               " WHERE norm >= ? AND norm < ? AND country = ?" + (" AND region = ?" if region else "") +
               f" ORDER BY population DESC LIMIT {MAX_RESULTS * 10}")  # « sa » : des milliers de villages
        args = (key, key + "\U0010ffff", country, *((region,) if region else ()))
        found = sorted(_unique(self._rows(sql, args)).values(), key=lambda r: -r[1])[:MAX_RESULTS]
        return [{"name": n, "country": c, "region": r, "region_name": self.region_name(r) if r else "",
                 "lat": lat, "lon": lon, "population": p} for c, p, n, lat, lon, r in found]

    def around(self, lat: float, lon: float, km: float, country: str) -> list[tuple[float, str, str, float, float]]:
        """[(distance, nom, région, latitude, longitude)] des lieux du pays à moins de km de la position, le plus
        proche d'abord."""
        dlat = km / 111.0
        dlon = km / max(1.0, 111.0 * math.cos(math.radians(lat)))
        sql = ("SELECT country, population, name, lat, lon, region FROM place"
               " WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND country = ?")
        rows = _unique(self._rows(sql, (lat - dlat, lat + dlat, lon - dlon, lon + dlon, country))).values()
        near = [(haversine((lat, lon), (la, lo)), n, r, la, lo) for _, _, n, la, lo, r in rows]
        return sorted(x for x in near if x[0] <= km)

    def match(self, lines: list[str], min_len: int = 4) -> list[Evidence]:
        """Lieux nommés dans le texte d'une marque : groupes de mots consécutifs, le plus long d'abord.

        Les mots d'un nom de rue sont écartés (« Via Paolo Lo Manto » : « Manto » n'est pas un lieu où l'on est) et
        rendus comme preuve « rue », qui ne compte pas mais s'affiche.
        """
        out: list[Evidence] = []
        seen: set[str] = set()
        street_next = ""  # ligne réduite à un mot de rue (« VIA ») : la ligne suivante est le nom de la rue
        table: list[float | list[Evidence]] = []  # le panneau ligne par ligne : un nombre seul, ou les lieux lus
        ahead: dict[int, float] = {}  # lieu → nombre écrit DEVANT son nom (« 10 Aarup »)
        for line in lines:
            alone = NUMBER_LINE.fullmatch(line)
            if alone:
                table.append(float(alone.group(1).replace(",", ".")))
                continue
            before = len(out)
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
                                        points=[[lat, lon, c, n, r] for c, _, n, lat, lon, r in rows]))
            placed = [e for e in out[before:] if e.kind == "lieu"]
            lead = LEADING_NUMBER.match(line)
            if lead and placed and line.find(placed[0].value) == lead.end() and placed[0].km is None:
                ahead[id(placed[0])] = float(lead.group(1).replace(",", "."))
            table.append(placed)
        _read_table(table, ahead)
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
        path = build(cfg.places_url, cfg.places_path, regions_url=cfg.regions_url)
    except PlacesError as exc:
        print(f"Lieux GeoNames : {exc}")
        return 1
    print(f"Lieux GeoNames : {Places(path).count} noms indexés dans {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
