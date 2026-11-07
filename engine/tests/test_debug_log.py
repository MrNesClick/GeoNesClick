"""Mode débogage : journal JSON de chaque analyse, seulement s'il est activé."""

import asyncio
import json

from PIL import Image

from geonesclick.capture import prune_captures
from geonesclick.config import load_config
from geonesclick.server import create_app
from geonesclick.streetclip import CountryScore


class FakeClip:
    def analyse(self, _img):
        return [CountryScore("Hungary", "HU", 0.7), CountryScore("Slovakia", "SK", 0.3)], 5.0, None, None


class FakeVision:
    ready, client = True, None

    async def describe(self, _img):
        return {"panneaux_et_texte": "plaque « Repkény utca »"}, 0.1


def analyse(tmp_path, debug: bool) -> tuple[str, list]:
    user = tmp_path / "config.toml"
    user.write_text(
        f'[capture]\nnotify = false\ndirectory = "{tmp_path / "captures"}"\n\n[debug]\nenabled = {str(debug).lower()}\n'
    )
    engine = create_app(load_config(user), user).state.engine
    engine.capture.grab = lambda: Image.new("RGB", (64, 40))
    engine.streetclip, engine.vision = FakeClip(), FakeVision()

    async def broadcast(_message):
        pass

    engine.broadcast = broadcast

    async def run():
        result = await engine.analyse()
        await asyncio.gather(*engine.background)
        return result["id"]

    return asyncio.run(run()), sorted((tmp_path / "captures").glob("capture-*"))


def test_no_log_without_debug(tmp_path):
    _, files = analyse(tmp_path, debug=False)
    assert [f.suffix for f in files] == [".png"]


def test_debug_log_collects_every_result(tmp_path):
    capture_id, files = analyse(tmp_path, debug=True)
    log = json.loads((tmp_path / "captures" / f"capture-{capture_id}.json").read_text())
    assert log["capture"] == f"capture-{capture_id}.png"
    assert log["streetclip"]["scores"][0]["code"] == "HU"
    assert "Repkény utca" in log["vision"]["fiche"]["panneaux_et_texte"]
    assert not list((tmp_path / "captures").glob("*.tmp"))  # écriture atomique terminée


def test_old_logs_are_pruned_with_their_capture(tmp_path):
    folder = tmp_path / "c"
    folder.mkdir()
    for i in range(3):
        (folder / f"capture-2026110{i}.png").write_bytes(b"")
        (folder / f"capture-2026110{i}.json").write_text("{}")
    prune_captures(folder, keep=1)
    assert sorted(f.name for f in folder.iterdir()) == ["capture-20261102.json", "capture-20261102.png"]


def test_logs_are_pruned_even_without_capture_copies(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text(f'[capture]\nnotify = false\nsave_to_disk = false\nkeep_last = 2\n'
                    f'directory = "{tmp_path / "captures"}"\n\n[debug]\nenabled = true\n')
    engine = create_app(load_config(user), user).state.engine
    engine.capture.grab = lambda: Image.new("RGB", (64, 40))
    engine.streetclip, engine.vision = FakeClip(), FakeVision()

    async def broadcast(_message):
        pass

    engine.broadcast = broadcast

    async def run():
        for _ in range(4):
            await engine.analyse()
            await asyncio.gather(*engine.background)
            await asyncio.sleep(0.002)  # identifiants horodatés distincts

    asyncio.run(run())
    files = list((tmp_path / "captures").glob("capture-*"))
    assert len(files) <= 3 and all(f.suffix == ".json" for f in files)  # 2 gardés (+ celui en cours d'écriture)
