"""Local collection of the Plonk It guides (https://www.plonkit.net), for the player's personal use.

Plonk It itself shows the way: its API only serves the beginner's guide, and the other guides are
read from the <script id="__PRELOADED_DATA__"> block of each page. Politeness rules applied:
one request at a time, a delay between two requests, an explicit User-Agent, and only the modified guides
("updatedAt" date in the list) are reloaded. The data stays on the machine, outside the repository.

Usage: python -m geonesclick.plonkit collect [--delay 2] [--dest FOLDER] [--all]
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
CHECKED_FILE = "checked_at"  # date of the last check of the guides list
MAX_BYTES = 5_000_000  # a guide page is ~30 KB: beyond that, something is wrong
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")  # used as a file name: never a "/" or a ".."
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
    """A tip from a guide: text (Markdown), example image, optional tags."""

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
    with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 (URL built from BASE_URL)
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
    """The published guide, as the page embeds it."""
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
    """All the collected tips (local reading only)."""
    tips = []
    for path in sorted((dest / "raw").glob("*.json")):
        try:
            tips += tips_of(json.loads(path.read_text()))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue  # damaged file: ignored, it will be reloaded at the guide's next update
    return tips


def collect(
    countries: set[str] | None, dest: Path = DATA_DIR, delay_s: float = 2.0, force: bool = False, log=print
) -> dict[str, int]:
    """Downloads the guides (of the given countries, or all) that changed since the last collection."""
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
        time.sleep(delay_s * random.uniform(1.0, 1.5))  # random: clients do not synchronise
        try:
            guide = extract_guide(_get(f"{BASE_URL}/{ref.slug}").decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:  # the site asks to slow down: we stop there, the rest will wait
                raise PlonkitError(f"Plonk It demande de ralentir (429), réessai après {exc.headers.get('Retry-After', '?')} s") from exc
            stats["failed"] += 1
            log(f"  failed {ref.slug}: {exc}")
            continue
        except (OSError, ValueError, PlonkitError) as exc:
            stats["failed"] += 1
            log(f"  failed {ref.slug}: {exc}")
            continue
        (raw / f"{ref.slug}.json").write_text(json.dumps(guide, ensure_ascii=False))
        index[ref.slug] = ref.updated_at
        index_file.write_text(json.dumps(index, indent=1))  # after each guide: an interruption loses nothing
        stats["fetched"] += 1
        log(f"  {ref.code} {ref.title}: {len(tips_of(guide))} tips")
    # Only after a full pass: after a 429, the next start resumes where we stopped.
    (dest / CHECKED_FILE).write_text(str(time.time()))
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="download the modified guides")
    c.add_argument("--delay", type=float, default=2.0, help="seconds between two pages (default: 2)")
    c.add_argument("--dest", type=Path, default=DATA_DIR)
    c.add_argument("--all", action="store_true", help="all the guides, not only the configured countries")
    c.add_argument("--force", action="store_true", help="reload even the unchanged guides")
    args = parser.parse_args()

    from .config import load_config

    countries = None if args.all else set(load_config().streetclip.countries.values())
    stats = collect(countries, args.dest, max(args.delay, 1.0), args.force)
    print(json.dumps(stats | {"tips": len(load_tips(args.dest))}, ensure_ascii=False))


if __name__ == "__main__":
    main()

