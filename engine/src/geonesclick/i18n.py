"""Texts the player sees, in their language: one catalog per language (locales/<lang>.json), shared with the UI
(app/src/i18n.ts) and the installer (app/src-tauri/src/i18n.rs), decided with the user on 2026-11-12.

    t("trigger.not_running.title")      # in the current language
    t("marks.read", n=3)                # "{n}" replaced by 3
    tn("marks.count", 3)                # plural: the key ".one" or ".other", with {n}

Same rules in the three layers: flat keys, "{name}" placeholders, English when a key or a language is missing.
The values of coach.language without a catalog (es, de... until their file is added) translate the Plonk It tips
only, the rest stays in English. test_i18n.py checks that every key used exists, with the same placeholders, in every catalog.
"""

from __future__ import annotations

import json
import re
from functools import cache
from importlib import resources

DEFAULT = "en"
# Languages with a catalog: every locales/<lang>.json (adding a language is adding its file).
UI_LANGUAGES = tuple(sorted(p.name.removesuffix(".json") for p in resources.files(__package__).joinpath("locales")
                            .iterdir() if p.name.endswith(".json")))
PLACEHOLDER = re.compile(r"\{(\w+)\}")

_current = DEFAULT


@cache
def catalog(lang: str) -> dict[str, str]:
    return json.loads(resources.files(__package__).joinpath("locales", f"{lang}.json").read_text(encoding="utf-8"))


def ui_language(lang: str) -> str:
    """The catalog to use for a coach.language value."""
    return lang if lang in UI_LANGUAGES else DEFAULT


def set_language(lang: str) -> None:
    """The coach's language (coach.language), set when the configuration is loaded or changed."""
    global _current
    _current = ui_language(lang)


def language() -> str:
    return _current


def t(key: str, lang: str | None = None, **params: object) -> str:
    """The text of a key; an unknown key raises KeyError (a bug, caught by test_i18n.py)."""
    texts = catalog(ui_language(lang or _current))
    text = texts[key] if key in texts else catalog(DEFAULT)[key]
    return PLACEHOLDER.sub(lambda m: str(params[m.group(1)]) if m.group(1) in params else m.group(0), text)


def plural_one(lang: str, n: float) -> bool:
    """Singular form? French: 0 and 1 ("0 marque"); English: 1 only (Intl.PluralRules gives the same)."""
    return n in (0, 1) if ui_language(lang) == "fr" else n == 1


def tn(key: str, n: float, lang: str | None = None, **params: object) -> str:
    """Plural text: the key ".one" or ".other", with {n}."""
    lang = lang or _current
    return t(f"{key}.{'one' if plural_one(lang, n) else 'other'}", lang, n=n, **params)
