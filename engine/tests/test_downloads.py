"""Transparency: every address written in the code is listed in downloads.toml, whether contacted or only shown."""

import re
import tomllib
from importlib import resources
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = [ROOT / "engine" / "src", ROOT / "app" / "src", ROOT / "app" / "src-tauri" / "src",
           ROOT / "app" / "src-tauri" / "capabilities", ROOT / "app" / "src-tauri" / "tauri.conf.json", ROOT / "scripts"]
URL = re.compile(r"https://([A-Za-z0-9.-]+)")


def manifest():
    return tomllib.loads(resources.files("geonesclick").joinpath("downloads.toml").read_text())


def test_every_address_in_the_code_is_declared():
    m = manifest()
    contacted = {h for d in m["download"] for h in d["hosts"]}
    known = contacted | set(m["shown"]["hosts"])
    files = [p for base in SCANNED for p in ([base] if base.is_file() else base.rglob("*"))
             if p.is_file() and p.suffix in (".py", ".toml", ".ts", ".vue", ".rs", ".json", ".sh")]
    found = {(URL.match(u).group(1).rstrip("."), str(f.relative_to(ROOT)))
             for f in files for u in URL.findall(f.read_text(errors="ignore")) for u in [f"https://{u}"]}
    missing = sorted((host, where) for host, where in found if host not in known)
    assert not missing, f"addresses missing from downloads.toml: {missing}"


def test_every_entry_says_what_where_how_much_license_why_when():
    from geonesclick.i18n import UI_LANGUAGES, catalog

    for d in manifest()["download"]:
        assert d["hosts"] and d["license"], d["id"]
        assert d["when"] in ("installation", "option", "on_demand", "continuous"), d["id"]
        assert isinstance(d["size_mb"], int) and isinstance(d["required"], bool), d["id"]
        assert not d.keys() & {"what", "why", "sends"}, f"{d['id']}: the texts belong in the catalogs"
        fields = ["what", "why"] + (["sends"] if d["when"] == "continuous" else [])  # what leaves your machine
        for lang in UI_LANGUAGES:
            missing = [f for f in fields if f"download.{d['id']}.{f}" not in catalog(lang)]
            assert not missing, f"{lang}.json: download.{d['id']}.{missing}"
        if not d["required"]:
            assert d.get("option"), f"{d['id']}: which setting turns it on or off"


def test_option_keys_exist_in_the_config():
    from geonesclick.config import load_config

    cfg = load_config(Path("/nonexistent.toml"))
    for d in manifest()["download"]:
        if d.get("option"):
            section, key = d["option"].split(".")
            assert hasattr(getattr(cfg, section), key), d["option"]


def test_readme_lists_every_contacted_host():
    """Both READMEs (English and French) list every contacted host in their downloads section."""
    for name, title in (("README.md", "## What GeoNesClick downloads"),
                        ("README.fr.md", "## Ce que GeoNesClick télécharge")):
        readme = (ROOT / name).read_text()
        assert title in readme, f"{name}: section {title!r} missing"
        section = readme.split(title, 1)[1].split("\n## ", 1)[0]
        for d in manifest()["download"]:
            for host in d["hosts"]:
                assert f"`{host}`" in section, f"{host} ({d['id']}) missing from {name}"
