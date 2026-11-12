"""Conversion of the files written by 0.1 (French ids), at the first start of the new version."""

import sqlite3
import tomllib

from geonesclick import migrate
from geonesclick.config import load_config
from geonesclick.metas import load_metas

OLD_METAS = """# mes notes, gardées
[[meta]]
category = "poteaux"
countries = ["FR"]
hint = "Poteaux en béton à trous"

[[meta]]
category = "marquage"
countries = ["NO", "FI", "US", "CA"]
hint = "Ligne centrale jaune"
look = "la couleur de la ligne centrale"
verified = true

[[rejected]]
category = "langue"
hint = "Suédois : å, ä, ö ; « väg », « gatan »"

[[rejected]]
category = "langue"
hint = "un indice qui n'existe plus"
"""

OLD_CONFIG = """# mes réglages
[coach]
help_level = 3

[metas]
category_weights = { domaine = 1.0, poteaux = 0.5 }
category_looks = { voiture = "l'antenne" }

[plonkit]
keywords = { panneaux = ["chevron"] }
"""


def _plonkit_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE tip(id INTEGER PRIMARY KEY, text TEXT, category TEXT NOT NULL, category_source TEXT NOT NULL);
        CREATE TABLE ai_category(hash TEXT PRIMARY KEY, category TEXT NOT NULL);
        INSERT INTO tip(text, category, category_source) VALUES ('Poles.', 'poteaux', 'etiquette'),
            ('White lines.', 'marquage', 'ia'), ('Nothing.', 'autre', 'aucune'), ('Bollards.', 'bornes', 'mots-cles');
        INSERT INTO ai_category VALUES ('h1', 'marquage');
    """)
    con.commit()
    con.close()


def test_old_files_are_converted_once_with_backups(tmp_path):
    config_dir, plonkit_dir = tmp_path / "config", tmp_path / "plonkit"
    config_dir.mkdir()
    plonkit_dir.mkdir()
    (config_dir / "mes-metas.toml").write_text(OLD_METAS)
    (config_dir / "config.toml").write_text(OLD_CONFIG)
    _plonkit_db(plonkit_dir / "plonkit.sqlite")

    done = migrate.run(config_dir, plonkit_dir)
    assert len(done) == 3, done
    assert migrate.run(config_dir, plonkit_dir) == []  # nothing left to do: never twice

    # my-metas.toml: categories renamed, the seed clue linked by its id, the old dismissal kept, comments kept.
    text = (config_dir / "my-metas.toml").read_text()
    assert text.startswith("# mes notes, gardées\n")
    metas = tomllib.loads(text)
    assert [m["category"] for m in metas["meta"]] == ["poles", "road_lines"]
    assert metas["meta"][0]["hint"] == "Poteaux en béton à trous"  # the player's own words stay theirs
    assert metas["meta"][1] | {"countries": []} == {
        "category": "road_lines", "countries": [], "hint": "Yellow centre line", "look": "the colour of the centre line",
        "verified": True, "seed": "road_lines_yellow"}
    assert metas["rejected"] == [{"seed": "language_se"}]  # the dismissal of a clue that no longer exists goes
    assert (config_dir / "mes-metas.toml.before-0.2").read_text() == OLD_METAS
    assert not (config_dir / "mes-metas.toml").exists()

    # config.toml: the category names of the per-category settings, the rest and the comments untouched.
    config = (config_dir / "config.toml").read_text()
    assert config.startswith("# mes réglages\n") and "help_level = 3" in config
    values = tomllib.loads(config)
    assert values["metas"]["category_weights"] == {"domains": 1.0, "poles": 0.5}
    assert values["metas"]["category_looks"] == {"car": "l'antenne"}
    assert values["plonkit"]["keywords"] == {"signs": ["chevron"]}
    assert (config_dir / "config.toml.before-0.2").read_text() == OLD_CONFIG

    # plonkit.sqlite: converted in place (the AI's classifications are kept).
    con = sqlite3.connect(plonkit_dir / "plonkit.sqlite")
    assert con.execute("SELECT text, category, category_source FROM tip ORDER BY id").fetchall() == [
        ("Poles.", "poles", "tag"), ("White lines.", "road_lines", "ai"), ("Nothing.", "other", "none"),
        ("Bollards.", "bollards", "keywords")]
    assert con.execute("SELECT category FROM ai_category").fetchall() == [("road_lines",)]
    con.close()


def test_converted_files_load_and_settle_the_seed(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "mes-metas.toml").write_text(OLD_METAS)
    (config_dir / "config.toml").write_text(OLD_CONFIG)
    migrate.run(config_dir, tmp_path / "no-plonkit")
    cfg = load_config(config_dir / "config.toml")  # valid with the new names
    metas = load_metas(config_dir / "my-metas.toml", True, cfg.streetclip.countries.values())
    seeds = [m.seed for m in metas if m.seed]
    assert "language_se" not in seeds  # dismissed
    assert seeds.count("road_lines_yellow") == 1  # the verified copy replaces the seed clue
    assert next(m for m in metas if m.seed == "road_lines_yellow").source == "mine"


def test_a_metas_file_chosen_by_the_player_is_converted_in_place(tmp_path):
    config_dir, mine = tmp_path / "config", tmp_path / "elsewhere" / "metas.toml"
    config_dir.mkdir()
    mine.parent.mkdir()
    mine.write_text(OLD_METAS)
    (config_dir / "config.toml").write_text(f'[metas]\nuser_file = "{mine}"\n')
    assert migrate.run(config_dir, tmp_path / "no-plonkit")
    assert tomllib.loads(mine.read_text())["meta"][0]["category"] == "poles"
    assert (mine.parent / "metas.toml.before-0.2").read_text() == OLD_METAS
    assert migrate.run(config_dir, tmp_path / "no-plonkit") == []


def test_nothing_to_convert_on_a_fresh_install(tmp_path):
    assert migrate.run(tmp_path / "config", tmp_path / "plonkit") == []
    assert not (tmp_path / "config").exists()


def test_an_unreadable_config_is_left_to_the_settings(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("[metas\n")
    assert migrate.run(config_dir, tmp_path / "plonkit") == []
    assert (config_dir / "config.toml").read_text() == "[metas\n"


def test_a_damaged_file_never_stops_the_engine(tmp_path):
    config_dir, plonkit_dir = tmp_path / "config", tmp_path / "plonkit"
    config_dir.mkdir()
    plonkit_dir.mkdir()
    (config_dir / "mes-metas.toml").write_text("[[meta\n")  # unreadable TOML
    (plonkit_dir / "plonkit.sqlite").write_bytes(b"not a database at all" * 100)
    done = migrate.run(config_dir, plonkit_dir)
    assert len(done) == 2 and all("left as it is" in d for d in done)
    assert (config_dir / "mes-metas.toml").read_text() == "[[meta\n"  # untouched: the Settings report it
    assert not (config_dir / "my-metas.toml").exists()
