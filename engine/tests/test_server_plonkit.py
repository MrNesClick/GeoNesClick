"""Cycle de vie de la base Plonk It dans le moteur : guides inventés, faux StreetCLIP, aucun réseau."""

import asyncio
import json
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from geonesclick import server
from geonesclick.config import load_config
from geonesclick.plonkit import CHECKED_FILE, PlonkitError
from geonesclick.server import create_app

ORIGIN = {"Origin": "http://localhost:1420"}
YELLOW, OTHER = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])


def guide(slug, code, texts):
    items = [{"kind": "tip", "id": str(i), "data": {"text": [t]}} for i, t in enumerate(texts)]
    return {"slug": slug, "code": code, "title": slug, "steps": [{"kind": "steps", "title": "Identifying", "items": items}]}


class FakeClip:
    def __init__(self):
        self.encoded = 0

    def encode_texts(self, texts):
        self.encoded += len(texts)
        return np.stack([YELLOW if "yellow" in t else OTHER for t in texts])


@pytest.fixture
def engine(tmp_path):
    data = tmp_path / "plonkit"
    (data / "raw").mkdir(parents=True)
    (data / "raw" / "norway.json").write_text(json.dumps(guide("norway", "NO", ["Poles.", "A yellow centre line."])))
    (data / "raw" / "sweden.json").write_text(json.dumps(guide("sweden", "SE", ["White lines."])))
    user = tmp_path / "config.toml"
    user.write_text(f'[capture]\nnotify = false\n\n[plonkit]\ndata_dir = "{data}"\n')
    app = create_app(load_config(user))
    eng = app.state.engine
    eng.streetclip = FakeClip()
    eng.client = TestClient(app, base_url="http://127.0.0.1:47615")
    return eng


def test_local_guides_are_indexed_and_matched_to_the_view(engine):
    asyncio.run(engine.refresh_plonkit(check=False))
    assert engine.plonkit_status == "ready" and len(engine.plonkit_tips) == 3
    similar = engine.similar(YELLOW, [("NO", 0.6), ("SE", 0.4)])
    assert similar["NO"][0]["text"] == "A yellow centre line."
    assert similar["NO"][0]["url"] == "https://www.plonkit.net/norway"
    assert set(similar) == {"NO", "SE"}


def test_vectors_are_cached_between_refreshes(engine):
    asyncio.run(engine.refresh_plonkit(check=False))
    asyncio.run(engine.refresh_plonkit(check=False))
    assert engine.streetclip.encoded == 3  # pas de recalcul pour les textes inchangés


def test_failed_check_keeps_the_previous_base(engine, monkeypatch):
    asyncio.run(engine.refresh_plonkit(check=False))

    def offline(*_args, **_kwargs):
        raise PlonkitError("injoignable")

    monkeypatch.setattr(server, "collect", offline)
    asyncio.run(engine.refresh_plonkit(check=True))
    assert engine.plonkit_status == "ready" and len(engine.plonkit_tips) == 3
    assert "injoignable" in engine.plonkit_message


def test_check_is_due_only_after_refresh_days(engine):
    checked = engine.cfg.plonkit.path / CHECKED_FILE
    assert engine.plonkit_due()  # jamais contrôlé
    checked.write_text(str(time.time()))
    assert not engine.plonkit_due()
    checked.write_text(str(time.time() - 31 * 86400))
    assert engine.plonkit_due()


def test_similar_tips_can_be_disabled(engine):
    asyncio.run(engine.refresh_plonkit(check=False))
    engine.cfg.plonkit.similar_tips = False
    assert engine.similar(YELLOW, [("NO", 0.6), ("SE", 0.4)]) == {}


def test_refresh_route_is_refused_when_disabled(engine):
    engine.cfg.plonkit.enabled = False
    assert engine.client.post("/plonkit/refresh", headers=ORIGIN).status_code == 409


def test_foreign_origin_cannot_trigger_a_refresh(engine):
    assert engine.client.post("/plonkit/refresh", headers={"Origin": "https://x.example"}).status_code == 403


def test_successful_check_reports_updated_guides(engine, monkeypatch):
    monkeypatch.setattr(server, "collect", lambda *_a, **_k: {"guides": 2, "fetched": 1, "unchanged": 1, "failed": 0})
    asyncio.run(engine.refresh_plonkit(check=True))
    assert engine.plonkit_status == "ready" and "1 guides mis à jour" in engine.plonkit_message


def test_corrupt_raw_file_is_skipped(engine):
    (engine.cfg.plonkit.path / "raw" / "broken.json").write_text('{"slug": "x"}')
    asyncio.run(engine.refresh_plonkit(check=False))
    assert engine.plonkit_status == "ready" and len(engine.plonkit_tips) == 3


def test_settings_toggle_plonkit_live(engine, tmp_path, monkeypatch):
    engine.settings_path = tmp_path / "config.toml"
    monkeypatch.setattr(server, "collect", lambda *_a, **_k: {"guides": 2, "fetched": 0, "unchanged": 2, "failed": 0})

    async def toggle():
        await engine.apply_settings({"plonkit": {"enabled": False}})
        assert engine.plonkit_status == "off"
        await engine.apply_settings({"plonkit": {"enabled": True}})
        assert engine.plonkit_task is not None
        await engine.plonkit_task

    asyncio.run(toggle())
    assert engine.plonkit_status == "ready"


class FakeLLM:
    """Faux client OpenAI : renvoie une réponse fixée et compte les appels."""

    def __init__(self, content=None, error=None):
        self.calls, self.content, self.error = 0, content, error
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        message = type("M", (), {"content": self.content})
        return type("R", (), {"choices": [type("C", (), {"message": message})]})


def test_ai_classifies_leftover_tips_once(engine):
    engine.cfg.plonkit.ai_pause_s = 0
    engine.vision.client = FakeLLM('{"0": "marquage"}')
    asyncio.run(engine.refresh_plonkit(check=False))
    by_text = {t.text: t.category for t in engine.plonkit_tips}
    assert by_text["White lines."] == "marquage"  # ni étiquette ni mot-clé : classée par l'IA
    assert "classées par l'IA" in engine.plonkit_message
    asyncio.run(engine.refresh_plonkit(check=False))
    assert engine.vision.client.calls == 1  # en cache : jamais redemandé
    by_text = {t.text: t.category for t in engine.plonkit_tips}
    assert by_text["White lines."] == "marquage"  # et réappliqué après la reconstruction de la base


def test_ai_failure_is_reported_and_retried_later(engine):
    engine.vision.client = FakeLLM(error=TimeoutError("lent"))
    asyncio.run(engine.refresh_plonkit(check=False))
    assert engine.plonkit_status == "ready" and "interrompu" in engine.plonkit_message
    engine.vision.client = FakeLLM('{"0": "marquage"}')
    asyncio.run(engine.refresh_plonkit(check=False))
    assert {t.text: t.category for t in engine.plonkit_tips}["White lines."] == "marquage"


def test_ai_classification_can_be_disabled(engine):
    engine.cfg.plonkit.ai_classify = False
    engine.vision.client = FakeLLM('{"0": "marquage"}')
    asyncio.run(engine.refresh_plonkit(check=False))
    assert engine.vision.client.calls == 0


def test_unreadable_ai_answer_is_not_cached(engine):
    engine.vision.client = FakeLLM("désolé, je ne peux pas")
    asyncio.run(engine.refresh_plonkit(check=False))
    assert len(engine.plonkit_index.unclassified()) == 1  # sera reproposée à la prochaine mise à jour


def test_displayed_tips_are_translated_once_and_cached(engine):
    asyncio.run(engine.refresh_plonkit(check=False))
    engine.cfg.plonkit.ai_classify = False
    engine.vision.client = FakeLLM('{"0": "Une ligne centrale **jaune**."}')
    sent = []

    async def broadcast(message):
        sent.append(message)

    engine.broadcast = broadcast
    similar = engine.similar(YELLOW, [("NO", 1.0)])
    yellow = next(t for t in similar["NO"] if t["text"] == "A yellow centre line.")
    assert yellow["translated"] is None
    asyncio.run(engine._translate_tips("cap", [(yellow["id"], yellow["text"])], "fr"))
    assert sent[-1]["translations"] == {yellow["id"]: "Une ligne centrale **jaune**."}
    again = next(t for t in engine.similar(YELLOW, [("NO", 1.0)])["NO"] if t["id"] == yellow["id"])
    assert again["translated"] == "Une ligne centrale **jaune**."  # servie depuis le cache


def test_translation_failure_keeps_english(engine):
    asyncio.run(engine.refresh_plonkit(check=False))
    engine.vision.client = FakeLLM(error=TimeoutError("lent"))
    sent = []

    async def broadcast(message):
        sent.append(message)

    engine.broadcast = broadcast
    asyncio.run(engine._translate_tips("cap", [("h", "Poles.")], "fr"))
    assert sent[-1]["translations"] == {} and "indisponible" in sent[-1]["error"]


def test_no_translation_in_english_or_when_disabled(engine):
    engine.vision.client = FakeLLM("{}")
    engine.cfg.coach.language = "en"
    assert engine.translation_lang is None
    engine.cfg.coach.language = "fr"
    engine.cfg.plonkit.translate = False
    assert engine.translation_lang is None
    engine.cfg.plonkit.translate = True
    assert engine.translation_lang == "fr"
