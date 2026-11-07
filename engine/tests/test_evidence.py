"""Règles locales des marques : alphabet, lettres et mots propres, noms de lieux, conclusion prudente."""

import io
import zipfile

import pytest

from geonesclick import places
from geonesclick.evidence import text_evidence, verdict
from geonesclick.locate import haversine, keep_nearby, locate
from geonesclick.places import Places, PlacesError, build

# Lignes au format GeoNames (19 colonnes) : id, nom, ascii, variantes, …, pays (8), …, population (14).
ROWS = [  # coordonnées réelles (GeoNames)
    ("1", "Blagoevgrad", "Blagoevgrad", "Благоевград,Blagoevgrad", "BG", "67810", "42.01457", "23.09804"),
    ("2", "Sofia", "Sofia", "София,Sofija", "BG", "1152556", "42.69751", "23.32415"),
    ("3", "Garmen", "Garmen", "Гърмен", "BG", "1838", "41.6", "23.81667"),
    ("4", "Gotse Delchev", "Gotse Delchev", "Гоце Делчев", "BG", "20522", "41.56667", "23.73333"),
    ("5", "Kazan", "Kazan", "Казань", "RU", "1243500", "55.78874", "49.12214"),
    ("6", "Gare", "Gare", "", "FR", "75580", "48.83", "2.37"),
    ("7", "Gare", "Gare", "", "LU", "11360", "49.6", "6.13"),
    ("8", "Palermo", "Palermo", "Palerme", "IT", "668405", "38.13205", "13.33561"),
    ("9", "Palermo", "Palermo", "", "US", "1000", "40.0", "-78.0"),
    ("13", "Catania", "Catania", "Catane", "IT", "290927", "37.49223", "15.07041"),
    ("14", "Manto", "Manto", "", "HN", "4000", "14.9", "-86.4"),
    ("15", "Roma", "Roma", "Rome", "IT", "2318895", "41.89193", "12.51133"),
]


def archive() -> bytes:
    lines = []
    for gid, name, ascii_name, alternates, country, population, lat, lon in ROWS:
        cols = [gid, name, ascii_name, alternates, lat, lon, "P", "PPL", country, "", "", "", "", "", population,
                "", "0", "Europe/Sofia", "2026-01-01"]
        lines.append("\t".join(cols))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cities1000.txt", "\n".join(lines))
    return buf.getvalue()


@pytest.fixture
def gazetteer(tmp_path, monkeypatch):
    monkeypatch.setattr(places, "_fetch", lambda _url: archive())
    return Places(build("https://example.org/cities1000.zip", tmp_path))


MARK_1 = ["Гърмен 3", "197", "Гоце Делчев 10", "Благоевград 109", "1", "София 219"]  # manche bulgare
MARK_2 = ["Домой 6", "Город 3", "Казань"]  # inventée par le modèle sur une découpe floue


def evidence(lines, gazetteer):
    return text_evidence(lines) + gazetteer.match(lines)


# --- alphabet, lettres, mots ------------------------------------------------------------------------
def test_cyrillic_rules_out_france():
    [script] = [e for e in text_evidence(MARK_2) if e.kind == "alphabet"]
    assert script.value == "cyrillique" and "FR" not in script.countries and "BG" in script.countries


def test_latin_rules_out_nobody():
    assert not [e for e in text_evidence(["Gare", "Centre-ville"]) if e.kind == "alphabet"]


def test_bulgarian_hard_sign_before_a_consonant():
    found = {e.value: e.countries for e in text_evidence(["Гърмен"])}
    assert found["ъ devant une consonne"] == ["BG"]
    assert "ъ devant une consonne" not in {e.value for e in text_evidence(["подъезд"])}  # russe : ъ avant е


@pytest.mark.parametrize("text, country", [
    ("Repkény utca", "HU"), ("Brīvības iela", "LV"), ("Mannerheimintie", "FI"), ("Storgatan", "SE"),
    ("вулиця Шевченка", "UA"), ("Kőbánya", "HU"), ("Strada Ștefan", "RO"),
])
def test_language_markers(text, country):
    assert any(country in e.countries for e in text_evidence([text]))


def test_tie_alone_is_english_not_finnish():
    assert not text_evidence(["tie"])


# --- noms de lieux ------------------------------------------------------------------------------------
def test_places_are_found_in_any_alphabet(gazetteer):
    found = {e.value: e.countries for e in gazetteer.match(MARK_1)}
    assert found == {"Гърмен": ["BG"], "Гоце Делчев": ["BG"], "Благоевград": ["BG"], "София": ["BG"]}


def test_common_word_can_name_places_in_several_countries(gazetteer):
    assert [e.countries for e in gazetteer.match(["Gare"])] == [["FR", "LU"]]


def test_short_names_are_ignored(gazetteer):
    assert gazetteer.match(["Gare"], min_len=5) == []


def test_download_is_https_only(tmp_path):
    with pytest.raises(PlacesError, match="https"):
        build("http://example.org/cities1000.zip", tmp_path)


def test_broken_archive_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(places, "_fetch", lambda _url: b"not a zip")
    with pytest.raises(PlacesError):
        build("https://example.org/x.zip", tmp_path)
    assert not (tmp_path / places.DB_NAME).exists()


# --- conclusion -----------------------------------------------------------------------------------
def test_places_and_letters_that_agree_are_certain(gazetteer):
    v = verdict([(1, evidence(MARK_1, gazetteer))])
    assert (v.country, v.level, v.against) == ("BG", "certain", [])
    assert "Благоевград" in v.cites[0]["items"]


def test_a_contradicting_mark_prevents_certainty(gazetteer):
    v = verdict([(1, evidence(MARK_1, gazetteer)), (2, evidence(MARK_2, gazetteer))])
    assert (v.country, v.level) == ("BG", "probable")
    assert v.against == [{"n": 2, "country": "RU", "items": ["Казань"]}]


def test_letters_alone_are_never_certain():
    v = verdict([(1, text_evidence(["Repkény utca"]))])
    assert (v.country, v.level) == ("HU", "probable")


def test_common_word_alone_concludes_nothing(gazetteer):
    v = verdict([(1, evidence(["Gare", "Centre-ville", "Mairie"], gazetteer))])
    assert v.country == "" and v.allowed is None


def test_alphabet_restricts_the_countries(gazetteer):
    v = verdict([(2, evidence(["Город"], gazetteer))])
    assert v.country == "" and "FR" not in v.allowed and "BG" in v.allowed and v.scripts == ["cyrillique"]


def test_incompatible_alphabets_exclude_nothing():
    v = verdict([(1, text_evidence(["Αθήνα"])), (2, text_evidence(["Москва"]))])
    assert v.allowed is None and "incompatibles" in v.conflict


# --- position estimée -------------------------------------------------------------------------------
def test_sign_distances_are_read_next_to_the_names(gazetteer):
    assert {e.value: e.km for e in gazetteer.match(MARK_1)} == {
        "Гърмен": 3, "Гоце Делчев": 10, "Благоевград": 109, "София": 219}  # « 197 » seul : numéro de route
    assert gazetteer.match(["Sofia 219 km"])[0].km == 219
    assert gazetteer.match(["Sofia centre"])[0].km is None


def test_sign_distances_pin_the_position(gazetteer):
    where = locate([(1, e) for e in gazetteer.match(MARK_1)], "BG")
    assert where["kind"] == "point" and 2 <= where["radius_km"] <= 5
    # Mesuré : 41,58° N, 23,82–23,85° E, à 2-3 km de Гърмен (3 km par la route).
    assert haversine((where["lat"], where["lon"]), (41.6, 23.81667)) < 4


def test_one_distance_gives_a_ring_and_none_gives_places(gazetteer):
    assert locate([(1, e) for e in gazetteer.match(["Благоевград 12"])], "BG")["kind"] == "ring"
    assert locate([(1, e) for e in gazetteer.match(["Благоевград", "София"])], "BG")["kind"] == "places"


def test_places_of_another_country_are_not_used(gazetteer):
    assert locate([(1, e) for e in gazetteer.match(["Казань 5"])], "BG") is None


def test_rebuild_reuses_the_downloaded_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(places, "_fetch", lambda _url: archive())
    build("https://example.org/cities1000.zip", tmp_path)
    monkeypatch.setattr(places, "_fetch", lambda _url: (_ for _ in ()).throw(AssertionError("retéléchargé")))
    (tmp_path / places.DB_NAME).unlink()
    assert Places(build("https://example.org/cities1000.zip", tmp_path)).count > 0


def test_misread_distance_gives_no_false_precision(gazetteer):
    """« София 19 » au lieu de 219 : incompatible avec les autres distances, donc pas de point."""
    misread = ["Гърмен 3", "Гоце Делчев 10", "Благоевград 109", "София 19"]
    where = locate([(1, e) for e in gazetteer.match(misread)], "BG")
    assert where["kind"] == "rough" and where["radius_km"] == 4  # au plus 3 km (+1) de Гърмен : toujours vrai
    assert [d["name"] for d in where["doubtful"]] == ["София"]


# --- comparaison des noms, homonymes lointains, détail d'un pays --------------------------------------
def test_names_match_without_accents_hyphens_or_article():
    assert places.normalise("SAUVETERRE DE BEARN") == places.normalise("Sauveterre-de-Béarn")
    assert "hopital d orion" in places.variants(places.normalise("L'Hôpital-d'Orion"))
    assert places.normalise("Йовково") != places.normalise("Иовково")  # le cyrillique garde ses signes


FRANCE = [  # GeoNames : villes, et le fichier complet de la France (villages compris)
    ("10", "Orthez", "Orthez", "", "FR", "11857", "43.48834", "-0.77266"),
    ("11", "Sauveterre-de-Béarn", "Sauveterre-de-Bearn", "", "FR", "1547", "43.3993", "-0.94011"),
    ("12", "Lasa", "Lasa", "Laas", "IT", "2032", "46.61", "10.70"),
]
VILLAGES = [
    ("20", "Laàs", "Laas", "", "FR", "108", "43.38166", "-0.85106"),
    ("21", "Laas", "Laas", "", "FR", "290", "43.46885", "0.31087"),
    ("22", "L'Hôpital-d'Orion", "L'Hopital-d'Orion", "", "FR", "150", "43.43667", "-0.84874"),
    ("23", "Pic d'Orhy", "Pic d'Orhy", "", "FR", "0", "43.0", "-1.0"),  # montagne : pas un lieu habité
]


def archive_of(rows, feature=None):
    lines = []
    for gid, name, ascii_name, alternates, country, population, lat, lon in rows:
        cls = "T" if name.startswith("Pic") else "P"
        cols = [gid, name, ascii_name, alternates, lat, lon, cls, "PPL", country, "", "", "", "", "", population,
                "", "0", "Europe/Paris", "2026-01-01"]
        lines.append("\t".join(cols))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "GeoNames readme")  # comme les archives par pays
        z.writestr("FR.txt", "\n".join(lines))
    return buf.getvalue()


@pytest.fixture
def france(tmp_path, monkeypatch):
    monkeypatch.setattr(places, "_fetch", lambda url: archive_of(VILLAGES if "FR.zip" in url else FRANCE))
    found = Places(build("https://example.org/cities1000.zip", tmp_path))
    return found, tmp_path


SIGN = ["HOPITAL D' ORION", "SAUVETERRE DE BEARN", "ORTHEZ"]  # manche du 2026-11-07, 17:06
HOTEL = ["HÔTEL", "RESTAURANT", "LAAS"]


def test_far_homonym_is_ignored_not_a_contradiction(france):
    found, _ = france
    kept, ignored = keep_nearby([(1, found.match(SIGN)), (2, found.match(HOTEL))], 400)
    assert [(i["value"], i["countries"]) for i in ignored] == [("LAAS", ["IT"])]  # Lasa, ~950 km d'Orthez
    v = verdict(kept)
    assert (v.country, v.level, v.against) == ("FR", "certain", [])


def test_without_a_group_nothing_is_ignored(france):
    found, _ = france
    _, ignored = keep_nearby([(1, found.match(["ORTHEZ"])), (2, found.match(["LAAS"]))], 400)
    assert ignored == []  # deux lieux seuls et lointains : la contradiction reste visible


def test_country_detail_finds_villages_and_the_nearest_homonym(france):
    found, folder = france
    path = build("https://example.org/FR.zip", folder, db_name=places.detail_name("FR"), archive_name=None,
                 populated_only=True)
    found.add_detail("FR", path)
    assert found.lookup("Pic d'Orhy") == []  # le fichier complet n'apporte que des lieux habités
    kept, ignored = keep_nearby([(1, found.match(SIGN)), (2, found.match(HOTEL))], 400)
    v = verdict(kept)
    assert ignored == [] and v.country == "FR" and {c["n"] for c in v.cites} == {1, 2}
    where = locate([(n, e) for n, f in kept for e in f if e.kind == "lieu"], "FR")
    laas = next(p for p in where["places"] if p["name"] == "LAAS")
    assert laas["label"] == "Laàs" and laas["lon"] < 0  # celui du Béarn, pas celui du Gers
    assert any(p["label"] == "L'Hôpital-d'Orion" for p in where["places"])


# --- un lieu seul ne conclut pas ; noms de rue (manche italienne du 2026-11-07) ----------------------
def test_a_lone_place_is_only_a_hint(gazetteer):
    v = verdict([(1, gazetteer.match(["Manto"]))])
    assert v.country == "" and v.unconfirmed == [{"n": 1, "value": "Manto", "country": "HN"}]


def test_a_lone_place_is_confirmed_by_streetclip_or_a_shared_word(gazetteer):
    assert verdict([(1, gazetteer.match(["CATANIA"]))], prior={"IT": 0.96}).country == "IT"
    assert verdict([(1, gazetteer.match(["CATANIA"]))], prior={"IT": 0.05}).country == ""
    with_via = [(1, gazetteer.match(["CATANIA"])), (2, text_evidence(["VIA ROMA"]))]
    assert verdict(with_via).country == "IT"  # « via » : italien (ou Tessin), il confirme Catane


def test_street_names_are_not_places(gazetteer):
    found = gazetteer.match(["VIA", "PAOLO LO MANTO"])  # « VIA » seul sur sa ligne, comme l'a lu l'IA
    assert [e.kind for e in found] == ["rue"] and found[0].value == "VIA PAOLO LO MANTO"
    assert not [e for e in gazetteer.match(["Via Roma"]) if e.kind == "lieu"]
    assert [e.value for e in gazetteer.match(["Roma 25"]) if e.kind == "lieu"] == ["Roma"]  # panneau : un lieu


def test_two_nearby_places_pick_the_right_homonym(gazetteer):
    kept, _ = keep_nearby([(1, gazetteer.match(["PALERMO - CATANIA A19"]))], 400)
    v = verdict(kept)
    assert (v.country, v.level) == ("IT", "certain")  # Palermo (US) écartée par la proximité de Catane


def test_unzipped_size_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(places, "MAX_UNZIPPED", 100)
    monkeypatch.setattr(places, "_fetch", lambda _url: archive())
    with pytest.raises(PlacesError, match="démesuré"):
        build("https://example.org/cities1000.zip", tmp_path)


def test_country_code_cannot_escape_the_folder():
    with pytest.raises(PlacesError):
        places.detail_name("../x")
