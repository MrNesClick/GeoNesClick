"""Collecte locale des guides Plonk It (https://www.plonkit.net), pour l'usage personnel du joueur.

Plonk It indique lui-même la voie à suivre : son API ne sert que le guide débutant, et les autres guides se
lisent dans le bloc <script id="__PRELOADED_DATA__"> de chaque page. Règles de politesse appliquées :
une requête à la fois, un délai entre deux requêtes, un User-Agent explicite, et seuls les guides modifiés
(date « updatedAt » de la liste) sont rechargés. Les données restent sur la machine, hors du dépôt.

Usage : python -m geonesclick.plonkit collect [--delay 2] [--dest DOSSIER] [--all]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .paths import DATA_DIR as APP_DATA
from typing import Any

BASE_URL = "https://www.plonkit.net"
USER_AGENT = "GeoNesClick/0.1 (outil d'entrainement personnel)"
DATA_DIR = APP_DATA / "plonkit"
CHECKED_FILE = "checked_at"  # date du dernier contrôle de la liste des guides
MAX_BYTES = 5_000_000  # une page de guide fait ~30 Ko : au-delà, quelque chose ne va pas
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")  # sert de nom de fichier : jamais de « / » ni de « .. »
PRELOADED = re.compile(r'<script[^>]*id="__PRELOADED_DATA__"[^>]*>(.*?)</script>', re.S)


class PlonkitError(RuntimeError):
    pass


@dataclass(frozen=True)
class GuideRef:
    slug: str
    code: str  # ISO 3166-1 alpha-2
    title: str
    updated_at: str


@dataclass
class Tip:
    """Une astuce d'un guide : texte (Markdown), image d'exemple, étiquettes éventuelles."""

    country: str
    slug: str
    section: str
    tip_id: str
    text: str
    tags: list[str] = field(default_factory=list)
    image_url: str = ""
    street_view: str = ""

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.slug}"


def _get(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 (URL construite à partir de BASE_URL)
        body = res.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise PlonkitError(f"réponse trop volumineuse : {url}")
    return body


def parse_guide_list(payload: bytes) -> list[GuideRef]:
    data = json.loads(payload)
    if not data.get("success") or not isinstance(data.get("data"), list):
        raise PlonkitError("liste des guides inattendue")
    refs = []
    for entry in data["data"]:
        slug, code = entry.get("slug", ""), entry.get("code", "")
        if SLUG.fullmatch(slug) and isinstance(code, str) and len(code) == 2:
            refs.append(GuideRef(slug, code.upper(), str(entry.get("title", "")), str(entry.get("updatedAt", ""))))
    return refs


def extract_guide(html: str) -> dict[str, Any]:
    """Le guide publié, tel que la page l'embarque."""
    m = PRELOADED.search(html)
    if not m:
        raise PlonkitError("bloc __PRELOADED_DATA__ introuvable : la page a peut-être changé de forme")
    data = json.loads(m.group(1))
    guide = (data.get("data") or {}).get("public")
    if not isinstance(guide, dict) or not isinstance(guide.get("steps"), list):
        raise PlonkitError("guide sans étapes : format inattendu")
    return guide


def tips_of(guide: dict[str, Any]) -> list[Tip]:
    code, slug = str(guide.get("code", "")).upper(), str(guide.get("slug", ""))
    tips = []
    for step in guide["steps"]:
        for item in step.get("items") or []:
            if item.get("kind") != "tip" or not isinstance(item.get("data"), dict):
                continue
            data = item["data"]
            text = data.get("text", "")
            text = "\n\n".join(map(str, text)) if isinstance(text, list) else str(text)
            image = data.get("image") if isinstance(data.get("image"), dict) else {}
            tips.append(Tip(
                country=code, slug=slug, section=str(step.get("title", "")), tip_id=str(item.get("id", "")),
                text=text.strip(), tags=[str(t) for t in item.get("tags") or []],
                image_url=str(image.get("imageUrl", "")), street_view=str(image.get("imageLink", "")),
            ))
    return tips


def load_tips(dest: Path = DATA_DIR) -> list[Tip]:
    """Toutes les astuces collectées (lecture locale uniquement)."""
    tips = []
    for path in sorted((dest / "raw").glob("*.json")):
        try:
            tips += tips_of(json.loads(path.read_text()))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue  # fichier abîmé : ignoré, il sera rechargé à la prochaine mise à jour du guide
    return tips


def collect(
    countries: set[str] | None, dest: Path = DATA_DIR, delay_s: float = 2.0, force: bool = False, log=print
) -> dict[str, int]:
    """Télécharge les guides (des pays donnés, ou tous) qui ont changé depuis la dernière collecte."""
    raw = dest / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    index_file = dest / "index.json"
    index: dict[str, str] = json.loads(index_file.read_text()) if index_file.exists() else {}
    refs = [r for r in parse_guide_list(_get(f"{BASE_URL}/api/guides")) if countries is None or r.code in countries]
    stats = {"guides": len(refs), "fetched": 0, "unchanged": 0, "failed": 0}
    for ref in refs:
        if not force and index.get(ref.slug) == ref.updated_at and (raw / f"{ref.slug}.json").exists():
            stats["unchanged"] += 1
            continue
        time.sleep(delay_s * random.uniform(1.0, 1.5))  # aléatoire : les clients ne se synchronisent pas
        try:
            guide = extract_guide(_get(f"{BASE_URL}/{ref.slug}").decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:  # le site demande de ralentir : on arrête là, la suite attendra
                raise PlonkitError(f"Plonk It demande de ralentir (429), réessai après {exc.headers.get('Retry-After', '?')} s") from exc
            stats["failed"] += 1
            log(f"  échec {ref.slug} : {exc}")
            continue
        except (OSError, ValueError, PlonkitError) as exc:
            stats["failed"] += 1
            log(f"  échec {ref.slug} : {exc}")
            continue
        (raw / f"{ref.slug}.json").write_text(json.dumps(guide, ensure_ascii=False))
        index[ref.slug] = ref.updated_at
        index_file.write_text(json.dumps(index, indent=1))  # après chaque guide : une coupure ne perd rien
        stats["fetched"] += 1
        log(f"  {ref.code} {ref.title} : {len(tips_of(guide))} astuces")
    # Seulement après un parcours complet : après un 429, le démarrage suivant reprend là où on s'est arrêté.
    (dest / CHECKED_FILE).write_text(str(time.time()))
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="télécharger les guides modifiés")
    c.add_argument("--delay", type=float, default=2.0, help="secondes entre deux pages (défaut : 2)")
    c.add_argument("--dest", type=Path, default=DATA_DIR)
    c.add_argument("--all", action="store_true", help="tous les guides, pas seulement les pays configurés")
    c.add_argument("--force", action="store_true", help="recharger même les guides inchangés")
    args = parser.parse_args()

    from .config import load_config

    countries = None if args.all else set(load_config().streetclip.countries.values())
    stats = collect(countries, args.dest, max(args.delay, 1.0), args.force)
    print(json.dumps(stats | {"tips": len(load_tips(args.dest))}, ensure_ascii=False))


if __name__ == "__main__":
    main()

