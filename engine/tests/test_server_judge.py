"""End-to-end analysis (simulated capture and models) and "Right" / "Wrong" verdicts on the seed."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from geonesclick.config import load_config
from geonesclick.metas import MetaError, judge_seed, load_metas, seed_metas
from geonesclick.server import create_app
from geonesclick.streetclip import CountryScore

ORIGIN = {"Origin": "http://localhost:1420"}
JAUNE = "Ligne centrale jaune"


@pytest.fixture
def cfg(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text(
        "[capture]\nnotify = false\nsave_to_disk = false\n\n"
        f'[metas]\nuser_file = "{tmp_path / "mes-metas.toml"}"\n'
    )
    return load_config(user)


@pytest.fixture
def setup(cfg):
    app = create_app(cfg)
    return TestClient(app, base_url="http://127.0.0.1:47615"), app.state.engine


class FakeClip:
    def analyse(self, _img):
        return [CountryScore("Norway", "NO", 0.6), CountryScore("Sweden", "SE", 0.4)], 5.0, None, None


class FakeVision:
    ready = True
    client = None  # no OpenAI client: neither translation nor classification

    async def describe(self, _img):
        return {"confiance": "faible"}, 0.1


def test_analyse_runs_both_levels(setup):
    """Regression: the level 2 task must be tracked from the first capture."""
    _, engine = setup
    engine.capture.grab = lambda: Image.new("RGB", (64, 40))
    engine.streetclip, engine.vision = FakeClip(), FakeVision()
    sent = []

    async def broadcast(message):
        sent.append(message)

    engine.broadcast = broadcast

    async def run():
        result = await engine.analyse()
        await asyncio.gather(*engine.background)
        return result

    assert asyncio.run(run())["ok"]
    types = [m["type"] for m in sent]
    assert {"capture", "streetclip", "vision"} <= set(types)
    lookfor = next(m for m in sent if m["type"] == "streetclip")["lookfor"]
    assert any(lf["looks"] == ["la couleur de la ligne centrale"] for lf in lookfor)


def test_right_copies_the_hint_as_verified_and_keeps_comments(cfg):
    path = cfg.metas.user_path
    path.write_text("# mes notes\n")
    known = cfg.streetclip.countries.values()
    judge_seed(path, "marquage", JAUNE, "right", known)
    judge_seed(path, "marquage", JAUNE, "right", known)  # twice: a single addition
    text = path.read_text()
    assert text.startswith("# mes notes\n") and text.count("[[meta]]") == 1
    mine = [m for m in load_metas(path, True, known) if m.hint == JAUNE and m.source == "mes metas"]
    assert len(mine) == 1 and mine[0].verified and mine[0].look == "la couleur de la ligne centrale"


def test_wrong_removes_the_hint_from_the_seed(cfg):
    known = cfg.streetclip.countries.values()
    judge_seed(cfg.metas.user_path, "marquage", JAUNE, "wrong", known)
    assert JAUNE not in [m.hint for m in load_metas(cfg.metas.user_path, True, known)]
    assert JAUNE in [m.hint for m in seed_metas(known)]  # the seed itself is intact


def test_unknown_hint_is_refused_and_nothing_written(cfg):
    with pytest.raises(MetaError, match="inconnu"):
        judge_seed(cfg.metas.user_path, "marquage", "invention", "right", cfg.streetclip.countries.values())
    assert not cfg.metas.user_path.exists()


def test_invalid_user_file_is_left_untouched(cfg):
    cfg.metas.user_path.write_text('[[meta]]\ncategory = "inconnue"\n')
    with pytest.raises(MetaError):
        judge_seed(cfg.metas.user_path, "marquage", JAUNE, "wrong", cfg.streetclip.countries.values())
    assert cfg.metas.user_path.read_text() == '[[meta]]\ncategory = "inconnue"\n'


def test_judge_route_reloads_metas_and_refreshes_the_capture(setup):
    client, engine = setup
    engine.recent["20261107-080023-137"] = {"frame": None, "predicted": "NO", "scores": [("NO", 0.6), ("SE", 0.4)]}
    before = len(engine.metas)
    with client.websocket_connect("ws://127.0.0.1:47615/ws", headers=ORIGIN) as ws:
        ws.receive_json()  # initial state
        body = {"category": "marquage", "hint": JAUNE, "verdict": "wrong", "id": "20261107-080023-137"}
        assert client.post("/metas/judge", json=body, headers=ORIGIN).status_code == 200
        assert ws.receive_json()["type"] == "state"
        update = ws.receive_json()
    assert update["type"] == "lookfor"
    assert len(engine.metas) == before - 1


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"category": "marquage", "hint": "invention", "verdict": "right"}, 422),
        ({"category": "marquage", "hint": JAUNE, "verdict": "peut-être"}, 422),
    ],
)
def test_judge_route_validates_input(setup, body, status):
    client, _ = setup
    assert client.post("/metas/judge", json=body, headers=ORIGIN).status_code == status


def test_foreign_origin_cannot_judge(setup):
    client, _ = setup
    body = {"category": "marquage", "hint": JAUNE, "verdict": "wrong"}
    assert client.post("/metas/judge", json=body, headers={"Origin": "https://x.example"}).status_code == 403


def _app_with(tmp_path, extra):
    user = tmp_path / "config.toml"
    user.write_text(
        f'[capture]\nnotify = false\n\n[metas]\nuser_file = "{tmp_path / "mes-metas.toml"}"\n{extra}'
    )
    app = create_app(load_config(user))
    return TestClient(app, base_url="http://127.0.0.1:47615"), app.state.engine


def test_judge_buttons_can_be_disabled(tmp_path):
    client, engine = _app_with(tmp_path, "judge_buttons = false\n")
    assert engine.state()["metas"]["judge"] is False
    body = {"category": "marquage", "hint": JAUNE, "verdict": "wrong"}
    assert client.post("/metas/judge", json=body, headers=ORIGIN).status_code == 409
    assert not (tmp_path / "mes-metas.toml").exists()


def test_looks_can_be_hidden(tmp_path):
    _, engine = _app_with(tmp_path, "show_looks = false\n")
    assert all(not lf.looks for lf in engine.look_for([("NO", 0.6), ("SE", 0.4)]))


def test_unknown_category_in_config_is_rejected(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text('[metas]\ncategory_weights = { inconnue = 1.0 }\n')
    with pytest.raises(ValueError, match="catégories inconnues"):
        load_config(user)


def test_seed_survives_a_shorter_country_list():
    metas = seed_metas(["NO", "SE"])
    assert metas and all(m.countries and m.countries <= {"NO", "SE"} for m in metas)
    assert {m.hint for m in metas} >= {"Ligne centrale jaune", "Ligne centrale blanche"}


def test_unreadable_user_file_is_a_conflict(setup, cfg):
    client, _ = setup
    cfg.metas.user_path.write_text("[[meta\n")  # unreadable TOML
    body = {"category": "marquage", "hint": JAUNE, "verdict": "wrong"}
    assert client.post("/metas/judge", json=body, headers=ORIGIN).status_code == 409


def test_negative_weight_is_rejected(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text("[metas]\ncategory_weights = { domaine = -1.0 }\n")
    with pytest.raises(ValueError, match="positif"):
        load_config(user)
