import pytest

from geonesclick.config import load_config
from geonesclick.metas import (
    CATEGORIES,
    CATEGORY_LOOK,
    MetaError,
    load_metas,
    parse_metas,
    select_candidates,
    tiebreak,
)

TOML = """
[[meta]]
category = "marquage"
countries = ["NO", "FI"]
hint = "Ligne centrale jaune"

[[meta]]
category = "marquage"
countries = ["SE"]
hint = "Ligne centrale blanche"

[[meta]]
category = "conduite"
countries = ["NO", "SE", "FI"]
hint = "Circulation à droite"

[[meta]]
category = "langue"
countries = ["SE"]
hint = "å ä ö"

[[meta]]
category = "langue"
countries = ["FI"]
hint = "lettres doublées"
"""


@pytest.fixture
def metas():
    return parse_metas(TOML, "test")


def test_category_that_shares_one_hint_does_not_discriminate(metas):
    cats = [r.category for r in tiebreak([("NO", 0.5), ("SE", 0.3), ("FI", 0.2)], metas)]
    assert "conduite" not in cats  # tous à droite : aucun départage


def test_categories_ranked_by_probability_weighted_separation(metas):
    res = tiebreak([("NO", 0.5), ("SE", 0.3), ("FI", 0.2)], metas)
    # marquage sépare NO|SE et SE|FI : 0.5*0.3 + 0.3*0.2 = 0.21
    # langue ne connaît pas NO : seule la paire SE|FI compte : 0.06
    assert [r.category for r in res] == ["marquage", "langue"]
    assert res[0].score == pytest.approx(0.21)


def test_hints_only_list_candidate_countries_in_probability_order(metas):
    res = tiebreak([("FI", 0.6), ("SE", 0.4)], metas)
    marquage = next(r for r in res if r.category == "marquage")
    jaune = next(h for h in marquage.hints if h.hint == "Ligne centrale jaune")
    assert jaune.countries == ["FI"]  # NO n'est pas candidat
    assert marquage.hints[0].hint == "Ligne centrale jaune"  # indice du favori en premier


def test_user_metas_come_first():
    user = parse_metas('[[meta]]\ncategory = "marquage"\ncountries = ["SE"]\nhint = "perso"\n', "mes metas")
    seed = parse_metas(TOML, "amorce")
    res = tiebreak([("NO", 0.9), ("SE", 0.1)], user + seed)
    assert res[0].hints[0].source == "mes metas"


def test_max_categories(metas):
    assert len(tiebreak([("NO", 0.5), ("SE", 0.3), ("FI", 0.2)], metas, max_categories=1)) == 1


@pytest.mark.parametrize(
    ("toml", "message"),
    [
        ('[[meta]]\ncategory = "inconnue"\ncountries = ["SE"]\nhint = "x"\n', "catégorie inconnue"),
        ('[[meta]]\ncategory = "langue"\ncountries = ["SWE"]\nhint = "x"\n', "2 lettres"),
        ('[[meta]]\ncategory = "langue"\ncountries = []\nhint = "x"\n', "2 lettres"),
        ('[[meta]]\ncategory = "langue"\ncountries = ["SE"]\nhint = "  "\n', "vide"),
        ('[[meta]]\ncategory = "langue"\ncountries = ["ZZ"]\nhint = "x"\n', "absents de la configuration"),
    ],
)
def test_invalid_metas_are_rejected_with_their_position(toml, message):
    with pytest.raises(MetaError, match=message):
        parse_metas(toml, "mes metas", known_countries=["SE"])


def test_select_candidates_keeps_at_least_two():
    assert select_candidates([("NO", 0.98), ("SE", 0.02)], 0.05, 5) == [("NO", 0.98), ("SE", 0.02)]
    assert select_candidates([("A", 0.4), ("B", 0.3), ("C", 0.2), ("D", 0.04)], 0.05, 5) == [
        ("A", 0.4), ("B", 0.3), ("C", 0.2)]
    assert len(select_candidates([(c, 0.2) for c in "ABCDEF"], 0.05, 3)) == 3


def test_seed_loads_and_only_uses_configured_countries(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    seed = load_metas(None, True, cfg.streetclip.countries.values())
    assert len(seed) > 40
    assert all(not m.verified and m.source == "amorce" for m in seed)


def test_seed_separates_serbia_from_croatia(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    seed = load_metas(None, True, cfg.streetclip.countries.values())
    res = tiebreak([("HR", 0.35), ("SI", 0.30), ("RS", 0.03)], seed)
    langue = next(r for r in res if r.category == "langue")
    assert any("cyrillique" in h.hint and h.countries == ["RS"] for h in langue.hints)


def test_looks_come_from_metas_without_naming_countries():
    toml = TOML.replace('hint = "Ligne centrale jaune"', 'hint = "Ligne centrale jaune"\nlook = "la couleur de la ligne"')
    res = tiebreak([("NO", 0.5), ("SE", 0.5)], parse_metas(toml, "test"))
    marquage = next(r for r in res if r.category == "marquage")
    assert marquage.looks == ["la couleur de la ligne"]


def test_category_look_is_the_fallback(metas):
    res = tiebreak([("SE", 0.5), ("FI", 0.5)], metas)
    langue = next(r for r in res if r.category == "langue")
    assert langue.looks == [CATEGORY_LOOK["langue"]]


def test_look_must_be_text():
    with pytest.raises(MetaError, match="look"):
        parse_metas('[[meta]]\ncategory = "langue"\ncountries = ["SE"]\nhint = "x"\nlook = 3\n', "mes metas")


def test_every_category_has_a_default_look():
    assert CATEGORY_LOOK.keys() == CATEGORIES.keys()


def test_category_looks_and_weights_can_be_overridden(metas):
    probs = [("NO", 0.5), ("SE", 0.3), ("FI", 0.2)]
    res = tiebreak(probs, metas, looks={"langue": "les panneaux"}, weights={"marquage": 0})
    assert [r.category for r in res] == ["langue"]  # poids 0 : catégorie ignorée
    assert res[0].looks == ["les panneaux"]
    assert all(not r.looks for r in tiebreak(probs, metas, max_looks=0))
