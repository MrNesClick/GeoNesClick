import json
import re
from pathlib import Path
from typing import get_args

import pytest

from geonesclick import i18n
from geonesclick.config import CoachConfig
from geonesclick.i18n import PLACEHOLDER, UI_LANGUAGES, catalog, t, tn

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ROOT / "engine/src/geonesclick/locales"
# Literal keys passed to t() / tn(): t("a.b"), tn("a.b", n), and in Rust t(lang, "a.b", ...) / tr("a.b", ...).
USED = re.compile(r"\b(t|tn|tr)\((?:[\w&.]+,\s*)?[\"']([a-z][\w]*(?:\.[\w]+)+)[\"']")
SOURCES = [*ROOT.glob("app/src/**/*.vue"), *ROOT.glob("app/src/**/*.ts"), *ROOT.glob("app/src-tauri/src/**/*.rs"),
           *ROOT.glob("engine/src/geonesclick/**/*.py")]


def test_every_catalog_is_a_language_the_setting_accepts():
    accepted = set(get_args(CoachConfig.model_fields["language"].annotation))
    assert {"en", "fr"} <= set(UI_LANGUAGES) <= accepted, "add the new language to [coach] language (config.py)"
    assert sorted(p.stem for p in LOCALES.glob("*.json")) == sorted(UI_LANGUAGES)


@pytest.mark.parametrize("lang", UI_LANGUAGES)
def test_catalogs_are_flat_objects_of_non_empty_texts(lang):
    data = json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    assert all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in data.items())


@pytest.mark.parametrize("lang", [x for x in UI_LANGUAGES if x != "en"])
def test_every_key_exists_in_every_language_with_the_same_placeholders(lang):
    en, other = catalog("en"), catalog(lang)
    assert sorted(set(en) ^ set(other)) == [], "keys present in one catalog only"
    for key, text in en.items():
        assert set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(other[key])), key


def test_plurals_have_both_forms():
    for key in catalog("en"):
        if key.endswith((".one", ".other")):
            base = key.rsplit(".", 1)[0]
            assert f"{base}.one" in catalog("en") and f"{base}.other" in catalog("en"), base


# Keys written as plain strings, translated elsewhere: Rust's system checks (label: "setup.check.…", shown by the
# UI) and sites (Some("setup.site.…"), passed to t()).
LITERAL_KEYS = re.compile(r"[\"']((?:setup\.check|setup\.site)\.\w+)[\"']")


def test_every_key_used_in_the_code_exists():
    known = set(catalog("en"))
    missing = []
    for path in SOURCES:
        if "__pycache__" in path.parts or path.stem == "i18n":  # the i18n modules hold examples, not real keys
            continue
        text = path.read_text(errors="ignore")
        for fn, key in USED.findall(text):
            needed = [f"{key}.one", f"{key}.other"] if fn == "tn" else [key]
            missing += [(k, str(path.relative_to(ROOT))) for k in needed if k not in known]
        missing += [(k, str(path.relative_to(ROOT))) for k in LITERAL_KEYS.findall(text) if k not in known]
    assert not missing, missing


def test_text_in_the_language_asked_english_when_missing():
    assert t("language.name", "fr") == "Français"
    assert t("language.name", "en") == "English"
    assert t("language.name", "de") == "English"  # no German catalog: the UI stays in English
    with pytest.raises(KeyError):
        t("no.such.key")


def test_current_language_follows_the_setting():
    try:
        i18n.set_language("fr")
        assert (i18n.language(), t("language.name")) == ("fr", "Français")
        i18n.set_language("es")
        assert i18n.language() == "en"
    finally:
        i18n.set_language("en")


def test_plural_forms_follow_each_language():
    assert [i18n.plural_one("fr", n) for n in (0, 1, 2)] == [True, True, False]
    assert [i18n.plural_one("en", n) for n in (0, 1, 2)] == [False, True, False]


def test_placeholders_are_filled_and_unknown_ones_left_visible(monkeypatch):
    monkeypatch.setitem(catalog("en"), "x.test", "{n} marks, {missing}")
    assert t("x.test", "en", n=3) == "3 marks, {missing}"
    monkeypatch.setitem(catalog("en"), "x.count.one", "{n} mark")
    monkeypatch.setitem(catalog("en"), "x.count.other", "{n} marks")
    assert (tn("x.count", 1, "en"), tn("x.count", 2, "en")) == ("1 mark", "2 marks")


def test_every_id_translated_at_run_time_has_its_key():
    """Keys built from tables (a missing one would raise KeyError while a mark is read, or in Settings)."""
    from geonesclick import evidence, settings

    needed = {f"script.{name}" for name, _, _ in evidence.SCRIPTS.values()}
    needed |= {f"lang.{lang}" for _, _, lang, _, _ in evidence.LETTERS} | {f"lang.{lang}" for _, lang, _ in evidence.WORDS}
    needed |= {f"evidence.letters.{shown}" for _, shown, *_ in evidence.LETTERS if shown.isascii()}
    needed |= {f"settings.why.{why}" for keys in settings.FILE_ONLY.values() for why in keys.values()}
    needed |= {f"storage.group.{g}" for g in ("account", "captures", "dataset", "plonkit", "places", "models")}
    for lang in UI_LANGUAGES:
        assert sorted(needed - set(catalog(lang))) == [], lang


def test_settings_tool_refuses_a_coach_section_that_is_not_an_object(monkeypatch, capsys):
    import io

    from geonesclick import settings

    monkeypatch.setattr("sys.stdin", io.StringIO('{"coach": 3}'))
    try:
        assert settings.main() == 1  # refused with a message, no traceback
    finally:
        i18n.set_language("en")
    assert "settings refused" in capsys.readouterr().err
