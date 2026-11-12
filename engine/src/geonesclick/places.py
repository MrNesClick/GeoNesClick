"""Place names: GeoNames directory (cities1000, CC BY 4.0), to recognise a city read on a mark.

Downloaded once (~11 MB) then indexed locally (SQLite): each name and its variants (other languages, other
alphabets) → country. Measured on 2026-11-07 on the Bulgarian round: Благоевград, София, Гърмен, Гоце Делчев → BG
only; Казань (invented by the model) → RU; "Gare" → FR, LU (districts): a common word can pass
for a place, hence evidence.py's cautious certainty rule.

Small villages (Laas, L'Hôpital-d'Orion, ~150 inhabitants) are not in it: as soon as a country leads, the FULL
directory of that country (GeoNames <CC>.zip, inhabited places only) is downloaded once and added (decided with the
user, 2026-11-07). Distant namesakes ("Laas" = Lasa, Italy) are ruled out by proximity (locate.py).

Data: GeoNames, https://www.geonames.org (CC BY 4.0), attribution shown in the app and the README.
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

from .i18n import t
from .evidence import STREET_AFTER, STREET_BEFORE, Evidence
from .locate import haversine

# v3: comparison without Latin accents or hyphens ("Sauveterre de Bearn"); v4: region of each place
# (GeoNames admin1 code) and latitude index, for the country › region › city locks (2026-11-07).
VERSION = "v4"
DB_NAME = f"places-{VERSION}.sqlite"
OLD_DBS = ("places.sqlite", "places-v2.sqlite", "places-v3.sqlite")
ARCHIVE = "source.zip"  # archive kept: a format change rebuilds without downloading again
REGIONS = "admin1.txt"  # region names (GeoNames admin1CodesASCII.txt, ~140 KB), kept likewise
MAX_RESULTS = 20  # results of a place search ("+" field of the locks banner)
PER_NAME = 3  # namesakes kept per name and per country (the most populous), decided between by the distances
SOURCE = "https://www.geonames.org"
USER_AGENT = "GeoNesClick/0.1 (personal training app, one-time download)"
MAX_WORDS = 4  # place names of at most 4 words ("Gotse Delchev", "San Carlos de Bariloche")
MAX_BYTES = 64 * 1024 * 1024  # safeguard: the archive is ~11 MB
MAX_UNZIPPED = 600 * 1024 * 1024  # safeguard against a booby-trapped archive (cities1000: ~31 MB; FR: ~50 MB)
COUNTRY = re.compile(r"[A-Z]{2}")  # country code: used in an address and a file name
REGION = re.compile(r"[A-Z]{2}\.[0-9A-Z]{1,20}")  # GeoNames region code: "FR.75"
NUMBER_LINE = re.compile(r"\s*(\d{1,4}(?:[.,]\d)?)\s*(?:km)?\.?\s*", re.IGNORECASE)  # "162", "11 km"
LEADING_NUMBER = re.compile(r"\s*(\d{1,4}(?:[.,]\d)?)(\s*(?:km)?\s+)", re.IGNORECASE)  # "10 Aarup"


class PlacesError(RuntimeError):
    pass


ARTICLES = ("l ", "le ", "la ", "les ")  # "L'Hôpital-d'Orion" is written "HOPITAL D'ORION" on the sign


def _fold(ch: str) -> str:
    """Latin letter without its accent (é → e); the other alphabets keep their marks (й ≠ и)."""
    if unicodedata.name(ch, "").startswith("LATIN"):
        return "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
    return ch


def normalise(name: str) -> str:
    """Comparison form: lower case, Latin accents removed, hyphens and apostrophes as spaces.

    The AI copies a sign in capitals, often without accents or hyphens ("SAUVETERRE DE BEARN");
    GeoNames writes "Sauveterre-de-Béarn".
    """
    name = unicodedata.normalize("NFC", name).casefold()
    name = "".join(_fold(ch) for ch in name)
    name = re.sub(r"[-'’‐‑]", " ", name)
    return " ".join(name.split()).strip(" .,;:!?()[]\"«»")


def variants(key: str) -> list[str]:
    """The normalised form, without a leading article ("l hopital d orion" → "hopital d orion")."""
    out = [key]
    for article in ARTICLES:
        if key.startswith(article) and len(key) > len(article) + 3:
            out.append(key[len(article):])
    return out


def _fetch(url: str) -> bytes:
    """Download of the archive (replaced in the tests: no network access)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (https checked by build)
            data = resp.read(MAX_BYTES + 1)
    except OSError as exc:
        raise PlacesError(t("places.download_failed", error=exc)) from exc
    if len(data) > MAX_BYTES:
        raise PlacesError(t("places.archive_too_big"))
    return data


def _regions(url: str | None, directory: Path) -> dict[str, str]:
    """Region names ("FR.75" → "Nouvelle-Aquitaine"), kept next to the archive.

    Optional: offline, the index is still built and a region is shown by its code.
    """
    if not url:
        return {}
    cached = directory / REGIONS
    fresh = not cached.exists()
    if fresh:
        if not url.startswith("https://"):
            raise PlacesError(t("places.regions_url"))
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
    if fresh and out:  # an error page instead of the file is not kept: retried next time
        cached.write_text(text, encoding="utf-8")
    return out


def build(url: str, directory: Path, min_len: int = 3, db_name: str = DB_NAME, archive_name: str | None = ARCHIVE,
          populated_only: bool = False, regions_url: str | None = None) -> Path:
    """Downloads the directory and builds the local index; atomic write of the database.

    populated_only: full file of a country (mountains, rivers…) of which only the inhabited places (P) are kept.
    regions_url: region names (general directory only; the countries' details share these codes).
    """
    if not url.startswith("https://"):
        raise PlacesError(t("places.directory_url"))
    directory.mkdir(parents=True, exist_ok=True)
    cached = directory / archive_name if archive_name else None
    data = cached.read_bytes() if cached and cached.exists() else _fetch(url)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            # The per-country archives also contain a readme.txt: we take the data file.
            member = next((n for n in archive.namelist()
                           if n.endswith(".txt") and "/" not in n and n.lower() != "readme.txt"), None)
            if member is None:
                raise PlacesError(t("places.no_file"))
            if archive.getinfo(member).file_size > MAX_UNZIPPED:
                raise PlacesError(t("places.file_too_big"))
            text = archive.read(member).decode("utf-8")
    except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise PlacesError(t("places.unreadable")) from exc
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
            con.execute("CREATE INDEX place_lat ON place(lat)")  # places around a position (region of the point)
            con.execute("CREATE TABLE region(code TEXT PRIMARY KEY, name TEXT NOT NULL)")
            con.executemany("INSERT INTO region VALUES (?, ?)", sorted(regions.items()))
    finally:
        con.close()
    path = directory / db_name
    tmp.replace(path)
    if cached and not cached.exists():
        cached.write_bytes(data)  # kept only once the index is built (valid archive)
    return path


def _distance_after(words: list[str], end: int, line: str) -> float | None:
    """Distance written right after the name, on the same line ("Гърмен 3", "Sofia 219 km"), in km.

    Only if no word follows the name any more: "197" alone on its line is a road number, not a distance.
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
    """Distances of a direction sign that the AI copied column by column (decided on 2026-11-07).

    Measured that evening: "SARANSK" / "162" / "СТАРЫЙ ГОРОД" / "11" (each distance under its place);
    "10 Aarup" / "5 Ørsted" / "329" (distance BEFORE the name, then the road number); "329 Faaborg" /
    "Glamsbjerg" / "28" / "3" (road first, both distances at the end). Rules, from most to least certain:
    1. a distance written after the name, on its line, is never replaced;
    2. lone numbers following a block of places go to them in order if there are as many of them as
       places in the block (Faaborg 28, Glamsbjerg 3: the "329" before Faaborg was a road);
    3. otherwise, a lone number right under a place without a distance goes to it (Saransk 162);
    4. finally, a place still without a distance takes the number written before its name (Aarup 10, Ørsted 5);
    an extra number is ignored ("329" under "5 Ørsted", "197" under "Гърмен 3"): a road number.
    """
    def fits(km: float) -> bool:
        return 0 < km <= 2000

    block: list[Evidence] = []  # places since the last run of numbers
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
        raise PlacesError(t("places.bad_country", code=repr(country)))
    return f"detail-{country}-{VERSION}.sqlite"


def _unique(rows) -> dict[tuple, tuple]:
    """The same place can come from the general directory and from the country's detail: it is kept once."""
    return {(c, n, round(lat, 2), round(lon, 2)): (c, p, n, lat, lon, r) for c, p, n, lat, lon, r in rows}


def _open(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)


class Places:
    """Local index of place names (read-only): localities with more than 1,000 inhabitants, plus the detail of
    some countries (all their inhabited places), added as rounds go by."""

    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise PlacesError(t("places.missing"))
        self.con = _open(path)
        self._lock = threading.Lock()
        self.count = self.con.execute("SELECT COUNT(*) FROM place").fetchone()[0]
        self.details: dict[str, sqlite3.Connection] = {}
        self._bounds: dict[str, list[float] | None] = {}  # extent of the regions already requested

    def add_detail(self, country: str, path: Path) -> None:
        con = _open(path)
        with self._lock:
            self.details[country] = con
            self._bounds.clear()  # villages widen the known extent of the regions

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
        """[(country, population, GeoNames name, latitude, longitude, region)] for a name (normalised form),
        general directory and country details together, without duplicates (same place in both)."""
        rows = self._rows("SELECT country, population, name, lat, lon, region FROM place WHERE norm = ?",
                          (normalise(name),))
        return sorted(_unique(rows).values(), key=lambda r: -r[1])

    def region_name(self, code: str) -> str:
        """Name of a region ("FR.75" → "Nouvelle-Aquitaine"); its code if the names are missing."""
        with self._lock:
            row = self.con.execute("SELECT name FROM region WHERE code = ?", (code,)).fetchone()
        return row[0] if row else code

    def region_bounds(self, code: str) -> list[float] | None:
        """[south, west, north, east] of the region's places (map framing, without an outline), kept in memory."""
        if code not in self._bounds:
            rows = self._rows("SELECT MIN(lat), MIN(lon), MAX(lat), MAX(lon) FROM place WHERE region = ?", (code,))
            found = [r for r in rows if r[0] is not None]
            self._bounds[code] = [min(r[0] for r in found), min(r[1] for r in found),
                                  max(r[2] for r in found), max(r[3] for r in found)] if found else None
        return self._bounds[code]

    def regions(self, country: str, query: str = "") -> list[dict[str, str]]:
        """Regions of a country whose name starts with query (ignoring accents and case), in alphabetical order."""
        with self._lock:
            rows = self.con.execute("SELECT code, name FROM region WHERE code LIKE ? ORDER BY name",
                                    (f"{country}.%",)).fetchall()
        key = normalise(query)
        return [{"code": c, "name": n} for c, n in rows
                if not key or any(w.startswith(key) for w in [normalise(n), *normalise(n).split()])][:MAX_RESULTS]

    def search(self, query: str, country: str, region: str = "") -> list[dict[str, Any]]:
        """Inhabited places with a name starting with query, in the country (and the region); most populous first."""
        key = normalise(query)
        if len(key) < 2:
            return []
        sql = ("SELECT country, population, name, lat, lon, region FROM place"
               " WHERE norm >= ? AND norm < ? AND country = ?" + (" AND region = ?" if region else "") +
               f" ORDER BY population DESC LIMIT {MAX_RESULTS * 10}")  # "sa": thousands of villages
        args = (key, key + "\U0010ffff", country, *((region,) if region else ()))
        found = sorted(_unique(self._rows(sql, args)).values(), key=lambda r: -r[1])[:MAX_RESULTS]
        return [{"name": n, "country": c, "region": r, "region_name": self.region_name(r) if r else "",
                 "lat": lat, "lon": lon, "population": p} for c, p, n, lat, lon, r in found]

    def around(self, lat: float, lon: float, km: float, country: str) -> list[tuple[float, str, str, float, float]]:
        """[(distance, name, region, latitude, longitude)] of the country's places within km of the position, closest
        first."""
        dlat = km / 111.0
        dlon = km / max(1.0, 111.0 * math.cos(math.radians(lat)))
        sql = ("SELECT country, population, name, lat, lon, region FROM place"
               " WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND country = ?")
        rows = _unique(self._rows(sql, (lat - dlat, lat + dlat, lon - dlon, lon + dlon, country))).values()
        near = [(haversine((lat, lon), (la, lo)), n, r, la, lo) for _, _, n, la, lo, r in rows]
        return sorted(x for x in near if x[0] <= km)

    def match(self, lines: list[str], min_len: int = 4) -> list[Evidence]:
        """Places named in a mark's text: groups of consecutive words, longest first.

        The words of a street name are ruled out ("Via Paolo Lo Manto": "Manto" is not a place where you are) and
        returned as a "street" proof, which does not count but is shown.
        """
        out: list[Evidence] = []
        seen: set[str] = set()
        street_next = ""  # line reduced to a street word ("VIA"): the next line is the street name
        table: list[float | list[Evidence]] = []  # the sign line by line: a lone number, or the places read
        ahead: dict[int, float] = {}  # place → number written BEFORE its name ("10 Aarup")
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
                out.append(Evidence("street", street, t("places.street"), [], ""))
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
                    out.append(Evidence("place", candidate, rows[0][2], countries, SOURCE,
                                        km=_distance_after(words, start + size, line),
                                        points=[[lat, lon, c, n, r] for c, _, n, lat, lon, r in rows]))
            placed = [e for e in out[before:] if e.kind == "place"]
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
    """python -m geonesclick.places: (re)builds the places index (called by scripts/install.sh)."""
    from .config import load_config

    cfg = load_config().rules
    try:
        path = build(cfg.places_url, cfg.places_path, regions_url=cfg.regions_url)
    except PlacesError as exc:
        print(f"GeoNames places: {exc}")
        return 1
    print(f"GeoNames places: {Places(path).count} names indexed in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
