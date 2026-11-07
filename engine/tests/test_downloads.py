"""Transparence : chaque adresse écrite dans le code figure dans downloads.toml, contactée ou seulement affichée."""

import re
import tomllib
from importlib import resources
from pathlib import Path
from urllib.parse import urlsplit

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
    assert not missing, f"adresses absentes de downloads.toml : {missing}"


def test_every_entry_says_what_where_how_much_license_why_when():
    for d in manifest()["download"]:
        assert d["what"] and d["hosts"] and d["license"] and d["why"], d["id"]
        assert d["when"] in ("installation", "option", "demande", "continu"), d["id"]
        assert isinstance(d["size_mb"], int) and isinstance(d["required"], bool), d["id"]
        if d["when"] == "continu":
            assert d.get("sends"), f"{d['id']} : dire ce qui part de ta machine"
        if not d["required"]:
            assert d.get("option"), f"{d['id']} : quel réglage l'active ou le coupe"


def test_option_keys_exist_in_the_config():
    from geonesclick.config import load_config

    cfg = load_config(Path("/nonexistent.toml"))
    for d in manifest()["download"]:
        if d.get("option"):
            section, key = d["option"].split(".")
            assert hasattr(getattr(cfg, section), key), d["option"]


def test_readme_lists_every_contacted_host():
    readme = (ROOT / "README.md").read_text()
    section = readme.split("## Ce que GeoNesClick télécharge", 1)[1].split("\n## ", 1)[0]
    for d in manifest()["download"]:
        for host in d["hosts"]:
            assert f"`{host}`" in section, f"{host} ({d['id']}) absent du README"
