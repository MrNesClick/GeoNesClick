"""The copy of a capture on disk never delays the models: it is written while they work."""

import asyncio
import threading

from PIL import Image

from geonesclick import server
from geonesclick.capture import save_png as real_save_png
from geonesclick.config import load_config
from geonesclick.server import create_app
from geonesclick.streetclip import CountryScore


class FakeClip:
    device = "cpu"

    def __init__(self, analysed: threading.Event):
        self.analysed = analysed

    def analyse(self, img):
        self.analysed.set()
        return [CountryScore("Hungary", "HU", 0.7)], 5.0, None, None


def engine_with(tmp_path, monkeypatch, save_png):
    user = tmp_path / "config.toml"
    user.write_text(f'[capture]\nnotify = false\nsave_to_disk = true\npath = "{tmp_path / "captures"}"\n')
    engine = create_app(load_config(user), user).state.engine
    engine.capture.grab = lambda: Image.new("RGB", (400, 300), (90, 120, 60))
    engine.vision = None
    engine.cfg.vision.enabled = False
    analysed = threading.Event()
    engine.streetclip = FakeClip(analysed)
    notified = []
    engine.notifier.send = lambda summary, body="", image=None, error=False: notified.append(image)

    async def broadcast(message):
        pass

    engine.broadcast = broadcast
    monkeypatch.setattr(server, "save_png", lambda *args: save_png(analysed, *args))

    async def run():
        result = await engine.analyse()
        await asyncio.gather(*engine.background)
        return result

    return asyncio.run(run()), notified


def test_streetclip_does_not_wait_for_the_png(tmp_path, monkeypatch):
    order = []

    def slow_save(analysed, img, directory, stem):
        order.append("streetclip first" if analysed.wait(2) else "png first")
        return real_save_png(img, directory, stem)

    result, notified = engine_with(tmp_path, monkeypatch, slow_save)
    assert result["ok"]
    assert order == ["streetclip first"]
    assert notified and notified[0].exists()  # the notification shows the copy, once written


def test_a_copy_that_cannot_be_written_does_not_stop_the_analysis(tmp_path, monkeypatch):
    def full_disk(analysed, img, directory, stem):
        raise OSError("No space left on device")

    result, notified = engine_with(tmp_path, monkeypatch, full_disk)
    assert result["ok"]
    assert notified == [None]
