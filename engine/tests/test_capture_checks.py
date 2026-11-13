"""A plain view, or the same pixels as the previous capture, is analysed anyway but comes with a note."""

import asyncio

import numpy as np
from PIL import Image

from geonesclick.capture import is_flat
from geonesclick.config import load_config
from geonesclick.server import create_app
from geonesclick.streetclip import CountryScore


def view(seed: int) -> Image.Image:
    return Image.fromarray(np.random.default_rng(seed).integers(0, 256, (300, 400, 3), dtype=np.uint8))


class FakeClip:
    device = "cpu"

    def analyse(self, img):
        return [CountryScore("Hungary", "HU", 0.7)], 5.0, None, None


def notes(tmp_path, frames) -> list[list[str]]:
    """The warnings sent with each capture of these frames, in order."""
    user = tmp_path / "config.toml"
    user.write_text('[capture]\nnotify = false\nsave_to_disk = false\ncrop = [0.0, 0.0, 1.0, 1.0]\n')
    engine = create_app(load_config(user), user).state.engine
    queue = iter(frames)
    engine.capture.grab = lambda: next(queue)
    engine.streetclip, engine.vision = FakeClip(), None
    engine.cfg.vision.enabled = False
    sent = []

    async def broadcast(message):
        sent.append(message)

    engine.broadcast = broadcast

    async def run():
        for _ in frames:
            assert (await engine.analyse())["ok"]  # never blocked
            await asyncio.gather(*engine.background)

    asyncio.run(run())
    return [m["warnings"] for m in sent if m.get("type") == "capture"]


def test_views_that_change_have_no_note(tmp_path):
    assert notes(tmp_path, [view(1), view(2), view(3)]) == [[], [], []]


def test_the_same_pixels_twice_point_to_a_frozen_sharing(tmp_path):
    assert notes(tmp_path, [view(1), view(1), view(2)]) == [[], ["same"], []]


def test_a_black_or_loading_view_is_plain(tmp_path):
    black, grey = Image.new("RGB", (400, 300)), Image.new("RGB", (400, 300), (40, 20, 60))
    assert notes(tmp_path, [black, grey]) == [["flat"], ["flat"]]


def test_a_snowfield_under_a_white_sky_is_not_plain():
    sky = np.full((150, 400), 225.0)
    snow = 200 + np.random.default_rng(0).normal(0, 20, (150, 400))  # tracks and drifts
    assert not is_flat(Image.fromarray(np.vstack([sky, snow]).clip(0, 255).astype(np.uint8)).convert("RGB"))
