"""Country › region › city locks: who locks, rejection lasting the whole capture, human lock never replaced."""

import io
import zipfile

import pytest

from geonesclick import places
from geonesclick.locks import Lock, Locks
from geonesclick.places import Places, build

FR = Lock("country", "FR")
BE = Lock("country", "BE")
NA = Lock("region", "FR", region="FR.75", name="Nouvelle-Aquitaine")
OC = Lock("region", "FR", region="FR.76", name="Occitanie")
ORTHEZ = Lock("city", "FR", region="FR.75", name="Orthez", lat=43.48834, lon=-0.77266)


def coach(locks, country=None, region=None, proposal=None):
    locks.coach(country, region, proposal)
    return locks


# --- the coach locks what is certain; its locks follow the proofs ------------------------------------
def test_coach_locks_and_follows_the_evidence():
    locks = coach(Locks(), FR, NA, ORTHEZ)
    assert (locks.held["country"].by, locks.held["region"].region) == ("coach", "FR.75")
    assert "city" not in locks.held and locks.proposal.name == "Orthez"  # a city is only suggested
    coach(locks)  # mark removed: nothing certain any more
    assert locks.held == {} and locks.proposal is None


def test_coach_region_needs_the_same_country():
    locks = coach(Locks(), BE, NA)
    assert "region" not in locks.held


# --- rejection: lasts the whole capture, it takes away the levels below -------------------------------
def test_rejected_lock_is_not_locked_again():
    locks = coach(Locks(), FR, NA, ORTHEZ)
    locks.reject("country")
    assert locks.held == {} and locks.proposal is None  # region and suggestion depended on the country
    coach(locks, FR, NA, ORTHEZ)  # next mark: still France
    assert "country" not in locks.held
    coach(locks, BE)
    assert locks.held["country"].country == "BE"  # another country is still possible


def test_rejected_region_keeps_the_country():
    locks = coach(Locks(), FR, NA)
    locks.reject("region")
    coach(locks, FR, NA)
    assert list(locks.held) == ["country"]
    coach(locks, FR, OC)
    assert locks.held["region"].region == "FR.76"


def test_rejected_proposal_is_not_proposed_again():
    locks = coach(Locks(), FR, None, ORTHEZ)
    locks.reject("proposal")
    assert coach(locks, FR, None, ORTHEZ).proposal is None


def test_rejecting_nothing_is_an_error():
    with pytest.raises(KeyError):
        Locks().reject("region")


# --- human lock: never replaced, it brings along the levels above -------------------------------------
def test_user_lock_is_never_replaced_by_the_coach():
    locks = Locks()
    locks.lock(BE)
    coach(locks, FR, NA)
    assert locks.held["country"].country == "BE" and locks.held["country"].by == "user"
    assert "region" not in locks.held  # the coach's region is in France


def test_user_city_locks_its_region_and_country():
    locks = coach(Locks(), BE)
    locks.lock(ORTHEZ)
    assert {lv: (lk.by, lk.country) for lv, lk in locks.held.items()} == {
        "country": ("user", "FR"), "region": ("user", "FR"), "city": ("user", "FR")}
    assert locks.held["region"].region == "FR.75"


def test_user_lock_drops_children_of_another_country():
    locks = Locks()
    locks.lock(ORTHEZ)
    locks.lock(BE)
    assert list(locks.held) == ["country"]


def test_user_can_lock_what_was_rejected():
    locks = coach(Locks(), FR)
    locks.reject("country")
    locks.lock(FR)
    assert locks.held["country"].by == "user" and not locks.rejected


def test_accepting_the_proposal_locks_the_city():
    locks = coach(Locks(), FR, NA, ORTHEZ)
    locks.lock(locks.proposal)
    assert locks.held["city"].by == "user" and locks.proposal is None


# --- what narrows down the search; log -----------------------------------------------------------
def test_search_scope_uses_user_locks_and_rejections_only():
    locks = coach(Locks(), FR, NA)
    assert locks.scope() == (None, None, set(), set())  # the coach's lock already follows from the proofs
    locks.reject("region")
    locks.lock(Lock("country", "FR"))
    assert locks.scope() == ("FR", None, set(), {"FR.75"})
    locks.reject("country")
    assert locks.scope() == (None, None, {"FR"}, {"FR.75"})


def test_events_are_logged_for_debugging():
    locks = coach(Locks(), FR)
    locks.reject("country")
    locks.lock(BE)
    assert [(e["event"], e["by"], e["country"]) for e in locks.events] == [
        ("lock", "coach", "FR"), ("reject", "coach", "FR"), ("lock", "user", "BE")]
    shown = locks.as_dict()
    assert shown["held"]["country"]["country"] == "BE" and shown["rejected"][0]["country"] == "FR"
    assert "events" not in shown


# --- index v4: regions, search, places around a point -----------------------------------------------
ROWS = [  # id, name, ascii, variants, country, region (admin1), population, latitude, longitude
    ("10", "Orthez", "Orthez", "", "FR", "75", "11857", "43.48834", "-0.77266"),
    ("11", "Sauveterre-de-Béarn", "Sauveterre-de-Bearn", "", "FR", "75", "1547", "43.3993", "-0.94011"),
    ("20", "Laàs", "Laas", "", "FR", "75", "108", "43.38166", "-0.85106"),
    ("21", "Laas", "Laas", "", "FR", "76", "290", "43.46885", "0.31087"),
    ("30", "Ortenberg", "Ortenberg", "", "DE", "01", "3200", "48.45", "7.97"),
    ("40", "Toulouse", "Toulouse", "", "FR", "76", "471941", "43.60444", "1.44194"),
]
REGIONS = "FR.75\tNouvelle-Aquitaine\tNouvelle-Aquitaine\t11071620\nFR.76\tOccitanie\tOccitanie\t11071623\n"


def archive() -> bytes:
    lines = ["\t".join([gid, name, ascii_name, alt, lat, lon, "P", "PPL", country, "", admin1, "", "", "", pop, "",
                        "0", "Europe/Paris", "2026-01-01"])
             for gid, name, ascii_name, alt, country, admin1, pop, lat, lon in ROWS]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cities1000.txt", "\n".join(lines))
    return buf.getvalue()


@pytest.fixture
def index(tmp_path, monkeypatch):
    monkeypatch.setattr(places, "_fetch", lambda url: REGIONS.encode() if url.endswith(".txt") else archive())
    return Places(build("https://example.org/cities1000.zip", tmp_path,
                        regions_url="https://example.org/admin1CodesASCII.txt"))


def test_places_know_their_region(index):
    [laas_64, laas_32] = [e for e in index.match(["LAAS"]) if e.kind == "place"][0].points
    assert {laas_64[4], laas_32[4]} == {"FR.75", "FR.76"}
    assert index.region_name("FR.75") == "Nouvelle-Aquitaine"
    assert index.region_name("FR.99") == "FR.99"  # unknown: its code


def test_regions_and_cities_can_be_searched(index):
    assert [r["name"] for r in index.regions("FR", "occ")] == ["Occitanie"]
    assert [r["code"] for r in index.regions("FR")] == ["FR.75", "FR.76"]
    assert [c["name"] for c in index.search("ort", "FR")] == ["Orthez"]  # Ortenberg is in Germany
    assert [c["name"] for c in index.search("laas", "FR", "FR.76")] == ["Laas"]
    assert index.search("o", "FR") == []  # one letter: too vague


def test_places_around_a_point(index):
    near = index.around(43.45, -0.80, 10, "FR")
    assert [n for _, n, *_ in near] == ["Orthez", "Laàs"] and {r for _, _, r, *_ in near} == {"FR.75"}


def test_index_builds_without_region_names(tmp_path, monkeypatch):
    def fetch(url):
        if url.endswith(".txt"):
            raise places.PlacesError("hors ligne")
        return archive()

    monkeypatch.setattr(places, "_fetch", fetch)
    index = Places(build("https://example.org/cities1000.zip", tmp_path, regions_url="https://example.org/a.txt"))
    assert index.region_name("FR.75") == "FR.75" and index.lookup("Orthez")
    assert not (tmp_path / places.REGIONS).exists()  # retried at the next build


# --- the marks' proofs under a lock --------------------------------------------------------------
def test_evidence_outside_the_lock_stays_visible_but_does_not_count(index):
    from geonesclick.evidence import text_evidence
    from geonesclick.locks import restrict

    found = restrict(index.match(["LAAS"]) + text_evidence(["Гърмен"]), ("FR", "FR.76", set(), set()))
    laas = next(e for e in found if e.kind == "place")
    assert laas.countries == ["FR"] and [p[3] for p in laas.points] == ["Laas"]  # the one in Gers (Occitanie)
    hard_sign = next(e for e in found if e.kind == "letters")
    assert hard_sign.countries == [] and "locked" in hard_sign.note
    alphabet = next(e for e in found if e.kind == "alphabet")
    assert "BG" in alphabet.countries  # visible contradiction, not an empty alphabet


def test_rejected_country_and_region_are_removed(index):
    from geonesclick.locks import restrict

    [laas] = [e for e in restrict(index.match(["LAAS"]), (None, None, set(), {"FR.75"})) if e.kind == "place"]
    assert [p[4] for p in laas.points] == ["FR.76"]
    [orthez] = [e for e in restrict(index.match(["ORTHEZ"]), (None, None, {"FR"}, set())) if e.kind == "place"]
    assert orthez.countries == [] and "rejected" in orthez.note


# --- in the engine: a round in Béarn ------------------------------------------------------------------
from test_marks import ORIGIN, ReaderVision, run, setup  # noqa: E402,F401  (shared fixture)

SIGN_KM = ["ORTHEZ 17", "SAUVETERRE DE BEARN 9", "LAAS 2"]  # direction sign near Laàs (km by road)


@pytest.fixture
def bearn(setup, index):
    engine, sent, _ = setup
    engine.places = index
    engine.cfg.marks.parallel = 1
    return engine, sent


def mark(engine, *readings):
    from geonesclick.marks import MarksRequest

    engine.vision = ReaderVision(list(readings))
    frozen = run(engine, engine.freeze())
    rects = [[0, 0, 0.5, 0.5], [0.5, 0.5, 1, 1]][:len(readings)]
    run(engine, engine.add_marks(MarksRequest(id=frozen["id"], rects=rects)))


def last_locks(sent):
    return [m for m in sent if m["type"] == "locks"][-1]


def test_coach_locks_country_and_region_and_proposes_the_nearest_village(bearn):
    engine, sent = bearn
    run(engine, engine.analyse())
    mark(engine, SIGN_KM)
    locks = last_locks(sent)
    assert locks["held"]["country"]["country"] == "FR" and locks["held"]["country"]["by"] == "coach"
    assert locks["held"]["region"]["name"] == "Nouvelle-Aquitaine"  # sharp point, all around in Nouvelle-Aquitaine
    assert "city" not in locks["held"] and locks["proposal"]["name"] == "Laàs"  # suggested, never locked


def test_a_place_read_without_distance_is_the_proposal(bearn):
    engine, sent = bearn
    run(engine, engine.analyse())
    mark(engine, ["ORTHEZ"], ["SAUVETERRE DE BEARN 12"])
    locks = last_locks(sent)
    assert locks["proposal"]["name"] == "Orthez"
    assert locks["held"]["region"]["region"] == "FR.75"  # no sharp point, but two nearby places agree


def test_rejected_country_stays_rejected_for_the_capture(bearn):
    from geonesclick.locks_engine import RejectRequest

    engine, sent = bearn
    capture_id = run(engine, engine.analyse())["id"]
    mark(engine, SIGN_KM)
    run(engine, engine.reject_lock(RejectRequest(id=capture_id, level="country")))
    assert last_locks(sent)["held"] == {} and last_locks(sent)["proposal"] is None
    verdict = [m for m in sent if m["type"] == "verdict"][-1]
    assert verdict["country"] == "FR"  # the conclusion stays independent: it contradicts your rejection
    mark(engine, ["ORTHEZ"])  # next mark: still nothing locked
    assert "country" not in last_locks(sent)["held"]
    new_id = run(engine, engine.analyse())["id"]  # a new capture starts from scratch
    assert engine.lock_scope(new_id) == (None, None, set(), set())


def test_user_lock_is_kept_and_the_marks_still_conclude_on_their_own(bearn):
    from fastapi.testclient import TestClient

    engine, sent = bearn
    c = TestClient(engine.app, base_url="http://127.0.0.1:47615")
    capture_id = c.post("/capture", headers=ORIGIN).json()["id"]
    assert c.post("/locks", json={"id": capture_id, "level": "country", "country": "BE"}, headers=ORIGIN).json()["ok"]
    mark(engine, SIGN_KM)
    locks = last_locks(sent)
    assert locks["held"]["country"] == {**locks["held"]["country"], "country": "BE", "by": "user"}
    verdict = [m for m in sent if m["type"] == "verdict"][-1]
    assert (verdict["country"], verdict["level"]) == ("FR", "certain")  # contradicts your choice: visible
    assert verdict["location"] is None  # nothing read in Belgium: no position under your choice


def test_user_country_picks_its_homonyms_for_the_position(bearn):
    from geonesclick.locks_engine import LockRequest

    engine, sent = bearn
    capture_id = run(engine, engine.analyse())["id"]
    run(engine, engine.set_lock(LockRequest(id=capture_id, level="region", country="FR", region="FR.76")))
    mark(engine, ["LAAS"], ["ORTHEZ 40"])  # Laàs (Béarn) near Orthez, but you said Occitanie
    where = [m for m in sent if m["type"] == "verdict"][-1]["location"]
    assert [p["label"] for p in where["places"] if p["name"] == "LAAS"] == ["Laas"]  # the one in Gers


def test_user_city_must_exist_in_the_index(bearn):
    from fastapi.testclient import TestClient

    engine, sent = bearn
    c = TestClient(engine.app, base_url="http://127.0.0.1:47615")
    capture_id = c.post("/capture", headers=ORIGIN).json()["id"]
    [orthez] = c.post("/locks/search", json={"level": "city", "q": "orth", "country": "FR"}, headers=ORIGIN).json()["results"]
    ok = c.post("/locks", json={"id": capture_id, "level": "city", **{k: orthez[k] for k in ("country", "region", "name", "lat", "lon")}},
                headers=ORIGIN)
    assert ok.status_code == 200
    held = last_locks(sent)["held"]
    assert [held[lv]["by"] for lv in held] == ["user"] * 3 and held["region"]["name"] == "Nouvelle-Aquitaine"
    fake = {"id": capture_id, "level": "city", "country": "FR", "name": "Orthez", "lat": 10.0, "lon": 10.0}
    assert c.post("/locks", json=fake, headers=ORIGIN).status_code == 422
    assert c.post("/locks", json={**fake, "country": "../"}, headers=ORIGIN).status_code == 422
    assert c.post("/locks/search", json={"level": "city", "q": "orth", "country": "FR"},
                  headers={"Origin": "https://x.example"}).status_code == 403


def test_locks_can_be_disabled(bearn):
    from geonesclick.locks_engine import LockRequest

    engine, sent = bearn
    engine.cfg.locks.enabled = False
    capture_id = run(engine, engine.analyse())["id"]
    mark(engine, SIGN_KM)
    assert not [m for m in sent if m["type"] == "locks"]
    with pytest.raises(Exception) as exc:
        run(engine, engine.set_lock(LockRequest(id=capture_id, level="country", country="FR")))
    assert getattr(exc.value, "status_code", None) == 409


def test_tips_of_the_locked_country_are_sent(bearn):
    from geonesclick.locks_engine import LockRequest

    engine, sent = bearn
    capture_id = run(engine, engine.analyse())["id"]
    engine.recent[capture_id]["emb"] = object()
    engine.similar = lambda emb, pairs, codes=None: {codes[0]: [{"id": "h", "text": "t", "translated": "x"}]}
    run(engine, engine.set_lock(LockRequest(id=capture_id, level="country", country="FR")))
    run(engine, engine.set_lock(LockRequest(id=capture_id, level="country", country="FR")))
    tips = [m for m in sent if m["type"] == "similar"]
    assert len(tips) == 1 and list(tips[0]["similar"]) == ["FR"] and tips[0]["batches"] == 0


def test_an_error_page_is_not_kept_as_region_names(tmp_path, monkeypatch):
    monkeypatch.setattr(places, "_fetch", lambda url: b"<html>503</html>" if url.endswith(".txt") else archive())
    build("https://example.org/cities1000.zip", tmp_path, regions_url="https://example.org/a.txt")
    assert not (tmp_path / places.REGIONS).exists()


def test_two_nearby_places_of_one_region_fix_it_but_propose_no_city(bearn):
    engine, sent = bearn
    run(engine, engine.analyse())
    mark(engine, ["ORTHEZ"], ["SAUVETERRE DE BEARN"])  # sign without distances: 16 km from each other
    locks = last_locks(sent)
    assert locks["held"]["country"]["country"] == "FR" and locks["proposal"] is None  # which city? none
    assert locks["held"]["region"]["name"] == "Nouvelle-Aquitaine"
    assert locks["read_regions"] == [{"code": "FR.75", "name": "Nouvelle-Aquitaine", "marks": [1, 2],
                                      "places": ["Orthez", "Sauveterre-de-Béarn"]}]


def test_places_too_far_apart_or_in_two_regions_are_only_offered(bearn):
    engine, sent = bearn
    engine.cfg.locks.region_places_km = 5
    run(engine, engine.analyse())
    mark(engine, ["ORTHEZ"], ["SAUVETERRE DE BEARN"])
    assert "region" not in last_locks(sent)["held"]
    run(engine, engine.analyse())
    mark(engine, ["ORTHEZ"], ["TOULOUSE"])  # Nouvelle-Aquitaine and Occitanie: your call
    locks = last_locks(sent)
    assert "region" not in locks["held"] and {r["code"] for r in locks["read_regions"]} == {"FR.75", "FR.76"}


def test_no_region_when_the_point_is_near_a_border(bearn):
    engine, sent = bearn
    engine.cfg.locks.region_radius_km = 100  # radius that reaches Laas (Gers, Occitanie)
    run(engine, engine.analyse())
    mark(engine, SIGN_KM)
    assert "region" not in last_locks(sent)["held"] and "country" in last_locks(sent)["held"]


def test_no_lock_on_a_probable_country(bearn):
    engine, sent = bearn
    run(engine, engine.analyse())
    mark(engine, ["ORTHEZ"], ["Repkény utca"])  # lone place, confirmed by nothing French
    verdict = [m for m in sent if m["type"] == "verdict"][-1]
    assert verdict["level"] != "certain" and "country" not in last_locks(sent)["held"]


def test_user_city_with_wrong_coordinates_is_refused(bearn):
    from geonesclick.locks_engine import LockRequest

    engine, _ = bearn
    capture_id = run(engine, engine.analyse())["id"]
    for lat, lon in ((44.48834, -0.77266), (43.48834, 0.22734)):  # 1° too many in latitude, then in longitude
        with pytest.raises(Exception) as exc:
            run(engine, engine.set_lock(LockRequest(id=capture_id, level="city", country="FR", name="Orthez",
                                                    lat=lat, lon=lon)))
        assert getattr(exc.value, "status_code", None) == 422


def test_map_gets_the_region_extent_and_the_places_outside_your_choice(bearn):
    from geonesclick.locks_engine import LockRequest

    engine, sent = bearn
    capture_id = run(engine, engine.analyse())["id"]
    mark(engine, ["ORTHEZ"], ["TOULOUSE"])
    run(engine, engine.set_lock(LockRequest(id=capture_id, level="region", country="FR", region="FR.75")))
    south, west, north, east = last_locks(sent)["region_bounds"]
    assert (south, west, north, east) == (43.38166, -0.94011, 43.48834, -0.77266)  # Orthez, Sauveterre, Laàs
    verdict = [m for m in sent if m["type"] == "verdict"][-1]
    assert [(o["n"], o["label"]) for o in verdict["outside"]] == [(2, "Toulouse")]  # greyed out, not erased


def test_a_place_without_known_region_does_not_block_the_region(setup, tmp_path, monkeypatch):
    """Russian round: a village without a GeoNames region near Temnikov blocked Mordovia."""
    rows = ROWS + [("50", "Inconnu", "Inconnu", "", "FR", "", "50", "43.39", "-0.86")]  # without a region, near Laàs

    def archive_rows():
        lines = ["\t".join([gid, name, ascii_name, alt, lat, lon, "P", "PPL", country, "", admin1, "", "", "", pop,
                            "", "0", "Europe/Paris", "2026-01-01"])
                 for gid, name, ascii_name, alt, country, admin1, pop, lat, lon in rows]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("cities1000.txt", "\n".join(lines))
        return buf.getvalue()

    monkeypatch.setattr(places, "_fetch", lambda url: REGIONS.encode() if url.endswith(".txt") else archive_rows())
    engine, sent, _ = setup
    engine.places = Places(build("https://example.org/c.zip", tmp_path / "p", regions_url="https://example.org/a.txt"))
    engine.cfg.marks.parallel = 1
    run(engine, engine.analyse())
    mark(engine, SIGN_KM)
    assert last_locks(sent)["held"]["region"]["region"] == "FR.75"


def test_a_short_rough_radius_fixes_the_region(bearn):
    """Inconsistent distances, but "within 3 km of Laàs" stays true: the region follows (Danish sign)."""
    engine, sent = bearn
    engine.cfg.locks.region_places_km = 5  # the "two places agree" rule does not apply here
    run(engine, engine.analyse())
    mark(engine, ["SAUVETERRE DE BEARN 60", "LAAS 2"])
    verdict = [m for m in sent if m["type"] == "verdict"][-1]
    assert verdict["location"]["kind"] == "rough" and verdict["location"]["radius_km"] == 3
    assert last_locks(sent)["held"]["region"]["region"] == "FR.75"


# --- replay bench: replays the corpus under the current rules ----------------------------------------
def test_bench_replays_rounds_and_counts_false_certainties(tmp_path, monkeypatch, index):
    import json as _json

    from geonesclick import bench
    from geonesclick.config import load_config
    from geonesclick.dataset import Dataset
    from PIL import Image

    cfg = load_config(tmp_path / "absent.toml")
    cfg.dataset.directory = str(tmp_path / "ds")
    ds = Dataset(cfg.dataset.path)
    frame = Image.new("RGB", (8, 8))
    good = {"marks": [{"n": 1, "text": SIGN_KM}], "scores": [["FR", 0.6]]}
    ds.add("20261107-190000-001", frame, "FR", lat=43.39, lon=-0.86, region="FR.75", round_data=good)
    ds.add("20261107-190000-002", frame, "BE", lat=50.85, lon=4.35, round_data=good)  # actually in Belgium
    ds.add("20261107-190000-003", frame, "FR", round_data={"marks": [], "scores": []})
    monkeypatch.setattr(bench, "open_places", lambda _cfg: index)
    rounds = {r.id[-1]: r for r in bench.run(cfg)}
    assert (rounds["1"].verdict, rounds["1"].region, rounds["1"].promise) == ("right", "right", "held")
    assert rounds["2"].verdict == "WRONG" and rounds["2"].level == "certain"
    s = bench.summary(list(rounds.values()))
    assert s["FALSE CERTAINTIES"] >= 1 and s["with marks"] == 2 and s["rounds"] == 3
    assert _json.loads(_json.dumps(bench.summary(list(rounds.values()))))  # --json output possible
