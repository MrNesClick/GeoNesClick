"""Marks: frozen view, enlarged crop from the raw image, transcription by the vision model."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from geonesclick.config import load_config
from geonesclick.marks import MarksRequest, crop_mark, reading
from geonesclick.server import create_app
from geonesclick.streetclip import CountryScore
from geonesclick.vision import VisionError

ORIGIN = {"Origin": "http://localhost:1420"}


class FakeClip:
    def analyse(self, _img):
        return [CountryScore("Romania", "RO", 0.6), CountryScore("Bulgaria", "BG", 0.4)], 5.0, None, None


class FakeVision:
    """Records the size of the images received; answers like the model (text read word for word)."""

    ready, client = True, None

    def __init__(self, fail: bool = False):
        self.sizes, self.fail = [], fail

    async def describe(self, _img):
        return {"signs_and_text": ""}, 0.1

    async def ask(self, img, prompt, model, max_tokens):
        self.sizes.append(img.size)
        if self.fail:
            raise VisionError("RateLimitError : 429")
        return {"text": ["Monumentul Eroilor Neamului"], "unreadable": False, "object": "sign", "script": "latin"}, 0.2


def frame() -> Image.Image:
    img = Image.new("RGB", (1000, 500), (40, 40, 40))
    img.paste((255, 0, 0), (100, 100, 240, 230))  # the "sign": 140×130 px
    return img


# --- crop ------------------------------------------------------------------------------------------
def test_small_mark_is_cropped_from_the_raw_frame_and_enlarged():
    crop, scale = crop_mark(frame(), [0.1, 0.2, 0.24, 0.46], upscale_to=420, max_upscale=4)
    assert scale == pytest.approx(3.0)
    assert crop.size == (420, 390)
    assert crop.getpixel((210, 195)) == (255, 0, 0)


def test_enlargement_is_capped():
    _, scale = crop_mark(frame(), [0.1, 0.2, 0.12, 0.24], upscale_to=420, max_upscale=4)
    assert scale == 4


def test_large_mark_keeps_its_size():
    crop, scale = crop_mark(frame(), [0, 0, 0.8, 1], upscale_to=420, max_upscale=4)
    assert scale == 1 and crop.size == (800, 500)


def test_reading_has_a_fixed_shape_whatever_the_model_says():
    assert reading({"text": "Repkény utca", "unreadable": "true", "script": "Cyrillic"}) == {
        "text": ["Repkény utca"], "unreadable": True, "object": "", "script": "cyrillic"}
    assert reading({"text": [None, "", "a" * 999]})["text"] == ["a" * 300]
    assert reading({})["text"] == []


# --- engine ----------------------------------------------------------------------------------------
@pytest.fixture
def setup(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text(f'[capture]\nnotify = false\ndirectory = "{tmp_path / "captures"}"\n\n[debug]\nenabled = true\n'
                    f'\n[metas]\nuser_file = "{tmp_path / "mes-metas.toml"}"\n')
    app = create_app(load_config(user), user)
    engine = app.state.engine
    engine.capture.grab = frame
    engine.streetclip, engine.vision = FakeClip(), FakeVision()
    sent = []

    async def broadcast(message):
        sent.append(message)

    engine.broadcast = broadcast
    engine.app = app  # for the route tests
    return engine, sent, tmp_path / "captures"


def run(engine, coro):
    async def go():
        result = await coro
        await asyncio.gather(*engine.background)
        return result

    return asyncio.run(go())


def test_marks_complete_the_current_analysis(setup):
    engine, sent, folder = setup
    capture_id = run(engine, engine.analyse())["id"]
    frozen = run(engine, engine.freeze())
    freeze_msg = next(m for m in sent if m["type"] == "freeze")
    assert freeze_msg["target"] == capture_id and freeze_msg["width"] == 1000

    rects = [[0.1, 0.2, 0.24, 0.46], [0.5, 0.5, 0.9, 0.9]]
    result = run(engine, engine.add_marks(MarksRequest(id=frozen["id"], rects=rects)))
    assert result == {"ok": True, "id": capture_id, "marks": [1, 2]}
    done = [m for m in sent if m["type"] == "mark" and m["status"] == "done"]
    assert sorted(m["n"] for m in done) == [1, 2]
    assert done[0]["text"] == ["Monumentul Eroilor Neamului"]
    assert (420, 390) in engine.vision.sizes  # the small sign is sent enlarged
    # Debug mode: crops and readings kept for measuring.
    assert (folder / f"mark-{capture_id}-1.png").exists()
    log = json.loads((folder / f"capture-{capture_id}.json").read_text())
    assert [m["status"] for m in log["marks"]] == ["done", "done"]
    assert frozen["id"] not in engine.frozen  # a frozen view is only used once


def test_numbering_continues_across_frozen_views(setup):
    engine, sent, _ = setup
    run(engine, engine.analyse())
    for _ in range(2):
        frozen = run(engine, engine.freeze())
        result = run(engine, engine.add_marks(MarksRequest(id=frozen["id"], rects=[[0, 0, 0.5, 0.5]])))
    assert result["marks"] == [2]


def test_marking_needs_a_capture_first(setup):
    engine, sent, _ = setup
    result = run(engine, engine.freeze())
    assert result["ok"] is False and "capture" in result["error"]
    assert not engine.frozen and not [m for m in sent if m["type"] == "freeze"]
    assert any(m["type"] == "error" for m in sent)  # visible in the coach, not only as a notification


def test_marks_go_to_the_round_that_was_frozen(setup):
    engine, sent, _ = setup
    first = run(engine, engine.analyse())["id"]
    frozen = run(engine, engine.freeze())
    run(engine, engine.analyse())  # new capture meanwhile: the frozen view stays the one of the 1st round
    result = run(engine, engine.add_marks(MarksRequest(id=frozen["id"], rects=[[0, 0, 0.5, 0.5]])))
    assert result["id"] == first


def test_expired_round_is_refused(setup):
    engine, sent, _ = setup
    run(engine, engine.analyse())
    frozen = run(engine, engine.freeze())
    engine.recent.clear()
    with pytest.raises(Exception) as exc:
        run(engine, engine.add_marks(MarksRequest(id=frozen["id"], rects=[[0, 0, 0.5, 0.5]])))
    assert getattr(exc.value, "status_code", None) == 409


def test_model_error_is_shown_on_the_mark(setup):
    engine, sent, _ = setup
    engine.vision = FakeVision(fail=True)
    run(engine, engine.analyse())
    frozen = run(engine, engine.freeze())
    run(engine, engine.add_marks(MarksRequest(id=frozen["id"], rects=[[0, 0, 0.5, 0.5]])))
    [error] = [m for m in sent if m["type"] == "mark" and m["status"] == "error"]
    assert "429" in error["error"]


def test_marks_can_be_disabled(setup):
    engine, sent, _ = setup
    engine.cfg.marks.enabled = False
    assert run(engine, engine.freeze())["ok"] is False
    assert not [m for m in sent if m["type"] == "freeze"]


# --- routes ----------------------------------------------------------------------------------------
@pytest.fixture
def client(setup):
    engine = setup[0]
    return TestClient(engine.app, base_url="http://127.0.0.1:47615"), engine


def frozen_id(client_engine):
    client, _ = client_engine
    client.post("/capture", headers=ORIGIN)  # the marks complete a round: capture first
    return client.post("/marks/freeze", headers=ORIGIN).json()["id"]


def test_frame_route_returns_the_frozen_image(client):
    c, _ = client
    fid = frozen_id(client)
    body = c.post("/marks/frame", json={"id": fid}, headers=ORIGIN).json()
    assert body["image"].startswith("data:image/jpeg;base64,") and (body["width"], body["height"]) == (1000, 500)


def test_frame_route_refuses_foreign_origins(client):
    c, _ = client
    fid = frozen_id(client)
    assert c.post("/marks/frame", json={"id": fid}, headers={"Origin": "https://x.example"}).status_code == 403


@pytest.mark.parametrize("rects", [[], [[0.5, 0.5, 0.2, 0.9]], [[0, 0, 1.5, 1]], [[0, 0, 1]]])
def test_invalid_rects_are_refused(client, rects):
    c, _ = client
    assert c.post("/marks", json={"id": frozen_id(client), "rects": rects}, headers=ORIGIN).status_code == 422


def test_too_many_marks_are_refused(client):
    c, engine = client
    rects = [[0, 0, 0.1, 0.1]] * (engine.cfg.marks.max_marks + 1)
    assert c.post("/marks", json={"id": frozen_id(client), "rects": rects}, headers=ORIGIN).status_code == 422


def test_unknown_frozen_view_is_404(client):
    c, _ = client
    res = c.post("/marks", json={"id": "20261107-000000-000", "rects": [[0, 0, 0.5, 0.5]]}, headers=ORIGIN)
    assert res.status_code == 404


# --- local rules and removal of a mark ----------------------------------------------------------------
class ReaderVision(FakeVision):
    """Reads what it is told, mark by mark (sending order)."""

    def __init__(self, readings):
        super().__init__()
        self.readings = list(readings)

    async def ask(self, img, prompt, model, max_tokens):
        return {"text": self.readings.pop(0)}, 0.1


def test_marks_feed_a_verdict_and_removing_the_wrong_one_updates_it(setup):
    engine, sent, _ = setup
    engine.cfg.marks.parallel = 1
    engine.vision = ReaderVision([["Гърмен"], ["Домой", "Город"]])
    capture_id = run(engine, engine.analyse())["id"]
    frozen = run(engine, engine.freeze())
    run(engine, engine.add_marks(MarksRequest(id=frozen["id"], rects=[[0, 0, 0.5, 0.5], [0.5, 0.5, 1, 1]])))
    last = [m for m in sent if m["type"] == "verdict"][-1]
    assert (last["country"], last["level"]) == ("BG", "probable")  # "ъ" before a consonant
    assert "FR" not in last["allowed"]  # Cyrillic: France is ruled out

    from geonesclick.marks import DeleteRequest

    run(engine, engine.remove_mark(DeleteRequest(id=capture_id, n=1)))
    last = [m for m in sent if m["type"] == "verdict"][-1]
    assert last["country"] == "" and "FR" not in last["allowed"]
    assert any(m["type"] == "mark_removed" and m["n"] == 1 for m in sent)
    frozen = run(engine, engine.freeze())
    engine.vision = ReaderVision([["Repkény utca"]])
    result = run(engine, engine.add_marks(MarksRequest(id=frozen["id"], rects=[[0, 0, 0.5, 0.5]])))
    assert result["marks"] == [3]  # the numbers are never reused


def test_rules_can_be_disabled(setup):
    engine, sent, _ = setup
    engine.cfg.rules.scripts = engine.cfg.rules.letters = False
    assert engine.evidence_of(["Гърмен"]) == []


def test_removing_an_unknown_mark_is_404(client):
    c, engine = client
    c.post("/capture", headers=ORIGIN)
    res = c.post("/marks/remove", json={"id": engine.last_id, "n": 7}, headers=ORIGIN)
    assert res.status_code == 404


def test_country_detail_is_loaded_once_and_marks_are_reread(setup, monkeypatch, tmp_path):
    """A country leads: its full directory (villages) is loaded once, then the marks are re-read."""
    import test_evidence as te

    from geonesclick import places

    engine, sent, _ = setup
    monkeypatch.setattr(places, "_fetch", lambda url: te.archive_of(te.VILLAGES if "FR.zip" in url else te.FRANCE))
    engine.cfg.rules.places_dir = str(tmp_path / "places")
    engine.places = places.Places(places.build(engine.cfg.rules.places_url, engine.cfg.rules.places_path))
    engine.cfg.marks.parallel = 1
    engine.vision = ReaderVision([te.SIGN, te.HOTEL])
    run(engine, engine.analyse())
    frozen = run(engine, engine.freeze())

    async def go():
        await engine.add_marks(MarksRequest(id=frozen["id"], rects=[[0, 0, 0.5, 0.5], [0.5, 0.5, 1, 1]]))
        await asyncio.gather(*engine.background)
        await engine.detail_tasks["FR"]

    asyncio.run(go())
    last = [m for m in sent if m["type"] == "verdict"][-1]
    assert (last["country"], last["level"]) == ("FR", "certain") and last["ignored"] == []
    assert {c["n"] for c in last["cites"]} == {1, 2}  # "LAAS" found in France after the detail
    assert "FR" in engine.places.details and "villages: FR" in engine.places_message


def test_countries_outside_the_candidates_do_not_count(setup, monkeypatch, tmp_path):
    import test_evidence as te

    from geonesclick import places

    engine, _, _ = setup
    monkeypatch.setattr(places, "_fetch", lambda _url: te.archive())
    engine.cfg.rules.places_dir = str(tmp_path / "places")
    engine.places = places.Places(places.build(engine.cfg.rules.places_url, engine.cfg.rules.places_path))
    [manto] = [e for e in engine.evidence_of(["Manto 5"]) if e.kind == "place"]
    assert manto.countries == [] and "HN" in manto.note  # Honduras is not a candidate country


def test_a_mark_removed_while_being_read_does_not_come_back(setup):
    engine, sent, _ = setup
    capture_id = run(engine, engine.analyse())["id"]
    frozen = run(engine, engine.freeze())
    gate = asyncio.Event()

    class Slow(FakeVision):
        async def ask(self, img, prompt, model, max_tokens):
            await gate.wait()
            return {"text": ["Гърмен"]}, 0.1

    engine.vision = Slow()
    from geonesclick.marks import DeleteRequest

    async def go():
        await engine.add_marks(MarksRequest(id=frozen["id"], rects=[[0, 0, 0.5, 0.5]]))
        await engine.remove_mark(DeleteRequest(id=capture_id, n=1))
        gate.set()
        await asyncio.gather(*engine.background)

    asyncio.run(go())
    assert not [m for m in sent if m["type"] == "mark" and m.get("status") == "done"]
    assert engine.recent[capture_id]["marks"] == []
