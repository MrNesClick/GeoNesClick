import pytest

from geonesclick import i18n
from geonesclick.config import load_config
from geonesclick.metas import (
    CATEGORIES,
    MINE,
    SEED,
    MetaError,
    category_look,
    load_metas,
    parse_metas,
    select_candidates,
    tiebreak,
)

TOML = """
[[meta]]
category = "road_lines"
countries = ["NO", "FI"]
hint = "Yellow centre line"

[[meta]]
category = "road_lines"
countries = ["SE"]
hint = "White centre line"

[[meta]]
category = "driving"
countries = ["NO", "SE", "FI"]
hint = "Driving on the right"

[[meta]]
category = "language"
countries = ["SE"]
hint = "å ä ö"

[[meta]]
category = "language"
countries = ["FI"]
hint = "doubled letters"
"""


@pytest.fixture
def metas():
    return parse_metas(TOML, "test")


def test_category_that_shares_one_hint_does_not_discriminate(metas):
    cats = [r.category for r in tiebreak([("NO", 0.5), ("SE", 0.3), ("FI", 0.2)], metas)]
    assert "driving" not in cats  # all drive on the right: no tie-break


def test_categories_ranked_by_probability_weighted_separation(metas):
    res = tiebreak([("NO", 0.5), ("SE", 0.3), ("FI", 0.2)], metas)
    # road_lines separates NO|SE and SE|FI: 0.5*0.3 + 0.3*0.2 = 0.21
    # language does not know NO: only the SE|FI pair counts: 0.06
    assert [r.category for r in res] == ["road_lines", "language"]
    assert res[0].score == pytest.approx(0.21)
    assert res[0].label == "Road markings"  # in the coach's language


def test_hints_only_list_candidate_countries_in_probability_order(metas):
    res = tiebreak([("FI", 0.6), ("SE", 0.4)], metas)
    road_lines = next(r for r in res if r.category == "road_lines")
    yellow = next(h for h in road_lines.hints if h.hint == "Yellow centre line")
    assert yellow.countries == ["FI"]  # NO is not a candidate
    assert road_lines.hints[0].hint == "Yellow centre line"  # the favourite's clue first


def test_user_metas_come_first():
    user = parse_metas('[[meta]]\ncategory = "road_lines"\ncountries = ["SE"]\nhint = "mine"\n', MINE)
    seed = parse_metas(TOML, SEED)
    res = tiebreak([("NO", 0.9), ("SE", 0.1)], user + seed)
    assert res[0].hints[0].source == MINE


def test_max_categories(metas):
    assert len(tiebreak([("NO", 0.5), ("SE", 0.3), ("FI", 0.2)], metas, max_categories=1)) == 1


@pytest.mark.parametrize(
    ("toml", "message"),
    [
        ('[[meta]]\ncategory = "unknown"\ncountries = ["SE"]\nhint = "x"\n', "unknown category"),
        ('[[meta]]\ncategory = "language"\ncountries = ["SWE"]\nhint = "x"\n', "2-letter"),
        ('[[meta]]\ncategory = "language"\ncountries = []\nhint = "x"\n', "2-letter"),
        ('[[meta]]\ncategory = "language"\ncountries = ["SE"]\nhint = "  "\n', "empty"),
        ('[[meta]]\ncategory = "language"\ncountries = ["ZZ"]\nhint = "x"\n', "missing from the configuration"),
        ('[[meta]]\ncategory = "language"\ncountries = ["SE"]\nhint = "x"\nseed = "../x"\n', "seed id"),
    ],
)
def test_invalid_metas_are_rejected_with_their_position(toml, message):
    with pytest.raises(MetaError, match=message):
        parse_metas(toml, MINE, known_countries=["SE"])


def test_select_candidates_keeps_at_least_two():
    assert select_candidates([("NO", 0.98), ("SE", 0.02)], 0.05, 5) == [("NO", 0.98), ("SE", 0.02)]
    assert select_candidates([("A", 0.4), ("B", 0.3), ("C", 0.2), ("D", 0.04)], 0.05, 5) == [
        ("A", 0.4), ("B", 0.3), ("C", 0.2)]
    assert len(select_candidates([(c, 0.2) for c in "ABCDEF"], 0.05, 3)) == 3


def test_seed_loads_and_only_uses_configured_countries(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    seed = load_metas(None, True, cfg.streetclip.countries.values())
    assert len(seed) > 40
    assert all(not m.verified and m.source == SEED and m.seed for m in seed)


def test_seed_separates_serbia_from_croatia(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    seed = load_metas(None, True, cfg.streetclip.countries.values())
    res = tiebreak([("HR", 0.35), ("SI", 0.30), ("RS", 0.03)], seed)
    language = next(r for r in res if r.category == "language")
    assert any("Cyrillic" in h.hint and h.countries == ["RS"] and h.seed == "language_rs" for h in language.hints)


def test_seed_shows_in_the_coach_language_and_keeps_its_id(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    try:
        i18n.set_language("fr")
        seed = {m.seed: m for m in load_metas(None, True, cfg.streetclip.countries.values())}
    finally:
        i18n.set_language("en")
    assert seed["language_rs"].hint.startswith("Serbe : cyrillique")
    assert seed["road_lines_yellow"].look == "la couleur de la ligne centrale"
    assert seed["domains_se"].hint == ".se"  # nothing to translate: the file's text


def test_looks_come_from_metas_without_naming_countries():
    toml = TOML.replace('hint = "Yellow centre line"', 'hint = "Yellow centre line"\nlook = "the colour of the line"')
    res = tiebreak([("NO", 0.5), ("SE", 0.5)], parse_metas(toml, "test"))
    road_lines = next(r for r in res if r.category == "road_lines")
    assert road_lines.looks == ["the colour of the line"]


def test_category_look_is_the_fallback(metas):
    res = tiebreak([("SE", 0.5), ("FI", 0.5)], metas)
    language = next(r for r in res if r.category == "language")
    assert language.looks == [category_look("language")] == ["the letters and words of the signs and shop signs"]


def test_look_must_be_text():
    with pytest.raises(MetaError, match="look"):
        parse_metas('[[meta]]\ncategory = "language"\ncountries = ["SE"]\nhint = "x"\nlook = 3\n', MINE)


def test_every_category_has_a_label_and_a_default_look():
    for lang in i18n.UI_LANGUAGES:
        missing = [c for c in CATEGORIES for key in (f"category.{c}", f"category.{c}.look") if key not in i18n.catalog(lang)]
        assert missing == [], lang


def test_category_looks_and_weights_can_be_overridden(metas):
    probs = [("NO", 0.5), ("SE", 0.3), ("FI", 0.2)]
    res = tiebreak(probs, metas, looks={"language": "the signs"}, weights={"road_lines": 0})
    assert [r.category for r in res] == ["language"]  # weight 0: category ignored
    assert res[0].looks == ["the signs"]
    assert all(not r.looks for r in tiebreak(probs, metas, max_looks=0))
