"""Route /label ("Where was it?"): input validation and addition to the test set."""

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from geonesclick.config import load_config
from geonesclick.server import create_app

ORIGIN = {"Origin": "http://localhost:1420"}
CAPTURE_ID = "20261107-080023-137"


@pytest.fixture
def setup(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text(
        f'[capture]\nnotify = false\n\n[vision]\nenabled = false\n\n[dataset]\ndirectory = "{tmp_path / "ds"}"\n'
        f'\n[metas]\nuser_file = "{tmp_path / "mes-metas.toml"}"\n'
    )
    app = create_app(load_config(user))
    engine = app.state.engine
    engine.recent[CAPTURE_ID] = {"frame": Image.new("RGB", (32, 20)), "predicted": "HR"}
    return TestClient(app, base_url="http://127.0.0.1:47615"), engine, tmp_path / "ds"


def test_label_adds_capture_and_returns_progress(setup):
    client, _, ds = setup
    res = client.post("/label", json={"id": CAPTURE_ID, "country": "rs", "found": False}, headers=ORIGIN)
    assert res.status_code == 200
    assert res.json()["progress"]["rounds"] == 1
    assert (ds / "images" / f"capture-{CAPTURE_ID}.png").exists()
    assert 'predicted = "HR"' in (ds / "labels.toml").read_text()


def test_unknown_country_is_rejected(setup):
    client, *_ = setup
    assert client.post("/label", json={"id": CAPTURE_ID, "country": "ZZ"}, headers=ORIGIN).status_code == 422


def test_unknown_capture_is_404(setup):
    client, *_ = setup
    res = client.post("/label", json={"id": "20261107-000000-000", "country": "SE"}, headers=ORIGIN)
    assert res.status_code == 404


def test_path_traversal_id_never_reaches_disk(setup):
    client, engine, ds = setup
    evil = "../../../../tmp/x"
    engine.recent[evil] = {"frame": Image.new("RGB", (8, 8)), "predicted": ""}
    res = client.post("/label", json={"id": evil, "country": "SE"}, headers=ORIGIN)
    assert res.status_code == 422
    assert not (ds / "images").exists()


def test_foreign_origin_cannot_label(setup):
    client, *_ = setup
    res = client.post("/label", json={"id": CAPTURE_ID, "country": "SE"}, headers={"Origin": "https://x.example"})
    assert res.status_code == 403


def test_guessed_country_is_validated(setup):
    client, *_ = setup
    res = client.post("/label", json={"id": CAPTURE_ID, "country": "RS", "guessed": "ZZ"}, headers=ORIGIN)
    assert res.status_code == 422


def test_confusions_come_with_the_metas_that_separate_them(setup):
    client, engine, _ = setup
    res = client.post("/label", json={"id": CAPTURE_ID, "country": "RS", "guessed": "HR"}, headers=ORIGIN)
    [confusion] = res.json()["progress"]["confusions"]
    assert (confusion["country"], confusion["guessed"], confusion["count"]) == ("RS", "HR", 1)
    langue = next(lf for lf in confusion["lookfor"] if lf["category"] == "langue")
    assert any("cyrillique" in h["hint"] for h in langue["hints"])


def test_confusions_can_be_hidden(setup):
    client, engine, _ = setup
    engine.cfg.dataset.max_confusions = 0
    res = client.post("/label", json={"id": CAPTURE_ID, "country": "RS", "guessed": "HR"}, headers=ORIGIN)
    assert res.json()["progress"]["confusions"] == []


# --- true place: Google Maps link from the end screen (never opened, only read) ---------------------
from geonesclick.dataset import coords_of  # noqa: E402


@pytest.mark.parametrize("text, expected", [
    ("https://www.google.com/maps/@54.6512,43.2276,3a,75y,90t/data=!3m6", (54.6512, 43.2276)),
    ("https://www.google.com/maps?q&layer=c&cbll=55.2724,10.1048&cbp=11,0,0,0,0", (55.2724, 10.1048)),
    ("https://www.google.com/maps/place/X/@55.0,10.0,15z/data=!3d55.27!4d10.10", (55.27, 10.10)),
    ("https://www.google.com/maps/search/?api=1&query=-33.86%2C151.21", (-33.86, 151.21)),
    ("  43.4883, -0.7727 ", (43.4883, -0.7727)),
    ("https://maps.app.goo.gl/AbCdEf", None),  # short link: it would have to be opened, we do not do it
    ("@95.0,10.0", None),
])
def test_coordinates_are_read_from_the_link(text, expected):
    assert coords_of(text) == expected


def test_label_with_a_link_stores_the_true_place_and_the_round(setup):
    import json

    client, engine, ds = setup
    engine.recent[CAPTURE_ID].update(scores=[("RS", 0.6)], marks=[{"n": 1, "status": "done", "text": ["Ниш 12"]}])
    link = "https://www.google.com/maps/@43.3209,21.8958,3a"  # Niš, Serbia
    assert client.post("/label/preview", json={"link": link}, headers=ORIGIN).json()["country"] == "RS"
    res = client.post("/label", json={"id": CAPTURE_ID, "link": link, "guessed": "HR"}, headers=ORIGIN)
    assert res.status_code == 200
    text = (ds / "labels.toml").read_text()
    assert 'country = "RS"' in text and "lat = 43.3209" in text
    round_ = json.loads((ds / "rounds" / f"{CAPTURE_ID}.json").read_text())
    assert round_["marks"] == [{"n": 1, "text": ["Ниш 12"], "object": None, "unreadable": None}]


def test_link_and_chosen_country_must_agree(setup):
    client, *_ = setup
    res = client.post("/label", json={"id": CAPTURE_ID, "country": "HR", "link": "43.3209, 21.8958"}, headers=ORIGIN)
    assert res.status_code == 422 and "RS" in res.json()["detail"]
    res = client.post("/label/preview", json={"link": "https://maps.app.goo.gl/x"}, headers=ORIGIN)
    assert res.status_code == 422
